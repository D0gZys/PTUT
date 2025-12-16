#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC-705 Spectrum Display avec Tkinter - Version 3
================================================
Version avec panneau de log des trames CI-V en hexadécimal.

Améliorations v3:
- Panneau à droite affichant les trames CI-V reçues en hex
- Timestamps locaux (millisecondes) pour chaque trame
- Textes lisibles avec meilleur contraste
- Interface redimensionnable
"""

import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import socket
import threading
import time
import numpy as np
import csv
import os
from datetime import datetime

# Forcer le backend TkAgg pour matplotlib (important sur macOS)
import matplotlib
matplotlib.use('TkAgg')

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# ============================================================
#              PARAMÈTRES DE CONFIGURATION
# ============================================================

SERVEUR_IP = "127.0.0.1"
SERVEUR_PORT = 50002
ADRESSE_RADIO = 0xA4
ADRESSE_PC = 0xE0
FREQUENCE_DEFAUT = 7.100
SPAN_KHZ = 200
LARGEUR_SPECTRE = 475
PROFONDEUR_WATERFALL = 100
MAX_LOG_LINES = 200  # Nombre max de lignes dans le log
LOG_UPDATE_INTERVAL = 200  # Mise à jour du log toutes les 200ms
MAX_TRAMES_PAR_UPDATE = 10  # Max trames à afficher par mise à jour
DOSSIER_CSV = "recep_csv"  # Dossier pour les enregistrements CSV


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
# ============================================================

def decoder_frequence_bcd(data):
    """
    Décode une fréquence en BCD (5 octets) vers MHz.
    Format: Hz(2) kHz(2) MHz(1-2) x10MHz x100MHz
    """
    if len(data) < 5:
        return FREQUENCE_DEFAUT
    
    freq_hz = 0
    for i, byte in enumerate(data[:5]):
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        factor = 10 ** (i * 2)
        freq_hz += low * factor + high * factor * 10
    
    return freq_hz / 1_000_000


def trouver_messages_civ(buffer):
    """
    Extrait tous les messages CI-V complets d'un buffer.
    Retourne la liste des messages trouvés et nettoie le buffer.
    """
    messages = []
    
    while True:
        debut = buffer.find(bytes([0xFE, 0xFE]))
        if debut == -1:
            buffer.clear()
            break
        
        if debut > 0:
            del buffer[:debut]
        
        fin = buffer.find(bytes([0xFD]))
        if fin == -1:
            break
        
        message = bytes(buffer[:fin + 1])
        messages.append(message)
        del buffer[:fin + 1]
    
    return messages


def extraire_donnees_spectre(msg):
    """
    Extrait les amplitudes d'une trame spectre (commande 0x27).
    """
    if len(msg) < 20:
        return None
    
    idx_start = 14
    idx_end = len(msg) - 1
    
    if idx_start >= idx_end:
        return None
    
    return np.array(list(msg[idx_start:idx_end]), dtype=np.float32)


def redimensionner_spectre(donnees, largeur_cible):
    """
    Redimensionne un spectre à la largeur souhaitée par interpolation.
    """
    if donnees is None or len(donnees) == 0:
        return np.zeros(largeur_cible)
    
    x_original = np.linspace(0, 1, len(donnees))
    x_nouveau = np.linspace(0, 1, largeur_cible)
    resultat = np.interp(x_nouveau, x_original, donnees)
    
    return resultat


def trame_vers_hex(msg):
    """Convertit une trame en chaîne hexadécimale lisible."""
    return ' '.join(f'{b:02X}' for b in msg)


def identifier_type_trame(msg):
    """Identifie le type de commande CI-V."""
    if len(msg) < 5:
        return "???"
    
    cmd = msg[4]
    types = {
        0x00: "TX",
        0x01: "S-Meter",
        0x03: "Freq",
        0x04: "Mode",
        0x05: "Set Freq",
        0x14: "Levels",
        0x15: "Read",
        0x16: "Functions",
        0x1A: "Config",
        0x1B: "Repeater",
        0x1C: "PTT",
        0x27: "SPECTRE",
        0xFA: "NG",
        0xFB: "OK"
    }
    return types.get(cmd, f"0x{cmd:02X}")


# ============================================================
#              CLASSE PRINCIPALE - APPLICATION TKINTER
# ============================================================

class IC705App:
    """Application principale avec interface Tkinter."""
    
    def __init__(self, root):
        """Initialise l'application."""
        self.root = root
        self.root.title("IC-705 Spectrum Display v3")
        self.root.geometry("1400x800")
        self.root.configure(bg='#1a1a2e')
        self.root.minsize(1200, 600)
        
        # Variables d'état
        self.connexion = None
        self.connecte = False
        self.affichage_actif = False
        self.freq_centrale = FREQUENCE_DEFAUT
        self.thread_reception = None
        
        # Données du spectre
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.nouvelles_donnees = False
        self.nouvelle_frequence = None  # Fréquence reçue du thread
        
        # Paramètres de gain
        self.gain_min = 20
        self.gain_max = 120
        
        # File des trames à afficher (thread-safe)
        self.trames_a_logger = []
        self.lock_trames = threading.Lock()
        self.compteur_trames_total = 0
        
        # Options de log
        self.log_spectre = tk.BooleanVar(value=False)  # Par défaut, pas les trames spectre
        self.log_autres = tk.BooleanVar(value=True)
        self.log_actif = tk.BooleanVar(value=True)  # Pause/Resume du log
        
        # Enregistrement CSV
        self.enregistrement_actif = False
        self.fichier_csv = None
        self.writer_csv = None
        self.nom_fichier_csv = None
        self.nb_lignes_csv = 0
        
        # Trigger pour enregistrement
        self.trigger_actif = tk.BooleanVar(value=False)
        self.seuil_trigger = 70  # Seuil par défaut
        self.au_dessus_seuil = False  # État actuel (au-dessus ou en-dessous du seuil)
        self.nb_fichiers_trigger = 0  # Compteur de fichiers créés avec trigger
        
        # Mode lecture CSV
        self.mode_lecture_csv = False
        self.donnees_csv = None
        self.index_lecture = 0
        self.lecture_en_cours = False
        
        # Créer l'interface
        self.creer_interface()
        self.creer_graphique()
    
    def creer_interface(self):
        """Crée les widgets de l'interface."""
        
        # === Frame du haut pour les contrôles ===
        frame_controles = tk.Frame(self.root, bg='#1a1a2e')
        frame_controles.pack(fill='x', padx=10, pady=10)
        
        # Titre
        titre = tk.Label(
            frame_controles,
            text="📡 IC-705 Spectrum Display",
            font=("Helvetica", 18, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre.pack(side='left', padx=10)
        
        # Frame connexion
        frame_conn = tk.Frame(frame_controles, bg='#1a1a2e')
        frame_conn.pack(side='left', padx=20)
        
        tk.Label(frame_conn, text="IP:", fg='white', bg='#1a1a2e', 
                 font=('Helvetica', 11)).pack(side='left')
        self.entry_ip = tk.Entry(frame_conn, width=12, font=('Helvetica', 11))
        self.entry_ip.insert(0, SERVEUR_IP)
        self.entry_ip.pack(side='left', padx=5)
        
        tk.Label(frame_conn, text="Port:", fg='white', bg='#1a1a2e',
                 font=('Helvetica', 11)).pack(side='left')
        self.entry_port = tk.Entry(frame_conn, width=6, font=('Helvetica', 11))
        self.entry_port.insert(0, str(SERVEUR_PORT))
        self.entry_port.pack(side='left', padx=5)
        
        # Boutons - Sur macOS, utiliser highlightbackground pour la couleur de fond
        self.btn_connecter = tk.Button(
            frame_controles,
            text="🔌 Connecter",
            font=("Helvetica", 12, "bold"),
            width=14,
            highlightbackground='#2a4a6e',
            command=self.toggle_connexion
        )
        self.btn_connecter.pack(side='left', padx=10)
        
        self.btn_afficher = tk.Button(
            frame_controles,
            text="▶ Démarrer",
            font=("Helvetica", 12, "bold"),
            width=14,
            highlightbackground='#4a4a4a',
            state='disabled',
            command=self.toggle_affichage
        )
        self.btn_afficher.pack(side='left', padx=10)
        
        # Bouton enregistrement CSV
        self.btn_enregistrer = tk.Button(
            frame_controles,
            text="⏺ REC",
            font=("Helvetica", 12, "bold"),
            width=8,
            highlightbackground='#4a4a4a',
            state='disabled',
            command=self.toggle_enregistrement
        )
        self.btn_enregistrer.pack(side='left', padx=5)
        
        # Frame pour le trigger
        frame_trigger = tk.Frame(frame_controles, bg='#1a1a2e')
        frame_trigger.pack(side='left', padx=5)
        
        # Checkbox Trigger
        self.cb_trigger = tk.Checkbutton(
            frame_trigger,
            text="Trigger >",
            variable=self.trigger_actif,
            font=('Helvetica', 10, 'bold')
        )
        self.cb_trigger.pack(side='left')
        
        # Entry pour le seuil
        self.entry_seuil = tk.Entry(frame_trigger, width=5, font=('Helvetica', 11),
                                     justify='center')
        self.entry_seuil.insert(0, "70")
        self.entry_seuil.pack(side='left', padx=2)
        
        # Bouton ouvrir CSV
        self.btn_ouvrir_csv = tk.Button(
            frame_controles,
            text="📂 Open CSV",
            font=("Helvetica", 12, "bold"),
            width=12,
            highlightbackground='#4a6e2a',
            command=self.ouvrir_csv
        )
        self.btn_ouvrir_csv.pack(side='left', padx=10)
        
        # Status
        self.label_status = tk.Label(
            frame_controles,
            text="⚪ Non connecté",
            font=("Helvetica", 12, "bold"),
            fg='#ff6666',
            bg='#1a1a2e'
        )
        self.label_status.pack(side='right', padx=10)
        
        # Fréquence
        self.label_freq = tk.Label(
            frame_controles,
            text="---",
            font=("Helvetica", 14, "bold"),
            fg='#ffcc00',
            bg='#1a1a2e'
        )
        self.label_freq.pack(side='right', padx=10)
        
        # Label enregistrement
        self.label_rec = tk.Label(
            frame_controles,
            text="",
            font=("Helvetica", 10),
            fg='#ff4444',
            bg='#1a1a2e'
        )
        self.label_rec.pack(side='right', padx=5)
        
        # Gestion de la fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)
        
        # === Frame pour les sliders de gain ===
        frame_sliders = tk.Frame(self.root, bg='#1a1a2e')
        frame_sliders.pack(fill='x', padx=10, pady=5)
        
        # Slider Gain Min
        tk.Label(frame_sliders, text="Gain Min:", fg='#4a90d9', bg='#1a1a2e', 
                 font=('Helvetica', 11, 'bold')).pack(side='left', padx=5)
        self.slider_min = tk.Scale(
            frame_sliders,
            from_=0, to=150,
            orient='horizontal',
            length=180,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 10),
            command=self.on_slider_change
        )
        self.slider_min.set(self.gain_min)
        self.slider_min.pack(side='left', padx=10)
        
        # Slider Gain Max
        tk.Label(frame_sliders, text="Gain Max:", fg='#d94a4a', bg='#1a1a2e',
                 font=('Helvetica', 11, 'bold')).pack(side='left', padx=5)
        self.slider_max = tk.Scale(
            frame_sliders,
            from_=50, to=255,
            orient='horizontal',
            length=180,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 10),
            command=self.on_slider_change
        )
        self.slider_max.set(self.gain_max)
        self.slider_max.pack(side='left', padx=10)
        
        # Label affichant les valeurs
        self.label_gain = tk.Label(
            frame_sliders,
            text=f"Plage: [{self.gain_min} - {self.gain_max}]",
            fg='#00ccff',
            bg='#1a1a2e',
            font=('Helvetica', 11, 'bold')
        )
        self.label_gain.pack(side='left', padx=20)
        
        # === Frame principale contenant graphique + log ===
        self.frame_principal = tk.Frame(self.root, bg='#1a1a2e')
        self.frame_principal.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Frame gauche pour le graphique
        self.frame_graph = tk.Frame(self.frame_principal, bg='#1a1a2e')
        self.frame_graph.pack(side='left', fill='both', expand=True)
        
        # Frame droite pour le log des trames
        self.creer_panneau_log()
    
    def creer_panneau_log(self):
        """Crée le panneau de log des trames CI-V."""
        frame_log = tk.Frame(self.frame_principal, bg='#1a1a2e', width=400)
        frame_log.pack(side='right', fill='y', padx=(10, 0))
        frame_log.pack_propagate(False)  # Garder la largeur fixe
        
        # Titre du panneau
        titre_log = tk.Label(
            frame_log,
            text="📋 Trames CI-V Reçues",
            font=("Helvetica", 12, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre_log.pack(pady=(0, 5))
        
        # Options de filtrage
        frame_options = tk.Frame(frame_log, bg='#1a1a2e')
        frame_options.pack(fill='x', pady=5)
        
        cb_spectre = tk.Checkbutton(
            frame_options,
            text="Spectre (0x27)",
            variable=self.log_spectre,
            fg='#aaaaaa',
            bg='#1a1a2e',
            selectcolor='#2a2a4e',
            activebackground='#1a1a2e',
            activeforeground='white',
            font=('Helvetica', 9)
        )
        cb_spectre.pack(side='left', padx=5)
        
        cb_autres = tk.Checkbutton(
            frame_options,
            text="Autres",
            variable=self.log_autres,
            fg='#aaaaaa',
            bg='#1a1a2e',
            selectcolor='#2a2a4e',
            activebackground='#1a1a2e',
            activeforeground='white',
            font=('Helvetica', 9)
        )
        cb_autres.pack(side='left', padx=5)
        
        # Bouton Pause/Resume
        self.btn_pause_log = tk.Button(
            frame_options,
            text="⏸",
            font=("Helvetica", 9),
            width=3,
            highlightbackground='#2a4a6e',
            command=self.toggle_log_pause
        )
        self.btn_pause_log.pack(side='left', padx=2)
        
        # Bouton Clear
        btn_clear = tk.Button(
            frame_options,
            text="🗑 Clear",
            font=("Helvetica", 9),
            highlightbackground='#4a2a2a',
            command=self.clear_log
        )
        btn_clear.pack(side='right', padx=5)
        
        # Zone de texte avec scrollbar
        frame_text = tk.Frame(frame_log, bg='#0a0a1a')
        frame_text.pack(fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(frame_text)
        scrollbar.pack(side='right', fill='y')
        
        self.text_log = tk.Text(
            frame_text,
            bg='#0a0a1a',
            fg='#00ff00',
            font=('Consolas', 9),
            wrap='none',
            state='disabled',
            yscrollcommand=scrollbar.set,
            width=50
        )
        self.text_log.pack(fill='both', expand=True)
        scrollbar.config(command=self.text_log.yview)
        
        # Configurer les tags pour colorer les types de trames
        self.text_log.tag_configure('timestamp', foreground='#888888')
        self.text_log.tag_configure('type_spectre', foreground='#ffcc00')
        self.text_log.tag_configure('type_freq', foreground='#00ccff')
        self.text_log.tag_configure('type_ok', foreground='#00ff88')
        self.text_log.tag_configure('type_ng', foreground='#ff6666')
        self.text_log.tag_configure('type_autre', foreground='#aaaaaa')
        self.text_log.tag_configure('hex', foreground='#00ff00')
        
        # Scrollbar horizontale
        scrollbar_h = tk.Scrollbar(frame_log, orient='horizontal')
        scrollbar_h.pack(fill='x')
        self.text_log.config(xscrollcommand=scrollbar_h.set)
        scrollbar_h.config(command=self.text_log.xview)
        
        # Compteur de trames
        self.label_compteur = tk.Label(
            frame_log,
            text="Total: 0 | Affichées: 0",
            font=("Helvetica", 10),
            fg='#888888',
            bg='#1a1a2e'
        )
        self.label_compteur.pack(pady=5)
    
    def toggle_log_pause(self):
        """Pause/Resume le log."""
        if self.log_actif.get():
            self.log_actif.set(False)
            self.btn_pause_log.config(text="▶", highlightbackground='#4a6e2a')
        else:
            self.log_actif.set(True)
            self.btn_pause_log.config(text="⏸", highlightbackground='#2a4a6e')
    
    def clear_log(self):
        """Efface le log des trames."""
        self.text_log.config(state='normal')
        self.text_log.delete('1.0', tk.END)
        self.text_log.config(state='disabled')
        self.compteur_trames_total = 0
        self.label_compteur.config(text="Total: 0 | Affichées: 0")
    
    def ajouter_trames_batch(self, trames):
        """Ajoute plusieurs trames au log en une seule opération (optimisé)."""
        if not trames or not self.log_actif.get():
            return
        
        # Filtrer les trames selon les options
        trames_filtrees = []
        for ts, type_t, hex_d in trames:
            if type_t == "SPECTRE" and not self.log_spectre.get():
                continue
            if type_t != "SPECTRE" and not self.log_autres.get():
                continue
            trames_filtrees.append((ts, type_t, hex_d))
        
        if not trames_filtrees:
            return
        
        # Limiter le nombre de trames par batch
        if len(trames_filtrees) > MAX_TRAMES_PAR_UPDATE:
            trames_filtrees = trames_filtrees[-MAX_TRAMES_PAR_UPDATE:]
        
        self.text_log.config(state='normal')
        
        # Construire tout le texte en une fois (beaucoup plus rapide)
        for ts, type_t, hex_d in trames_filtrees:
            # Format simplifié pour performance
            if type_t == "SPECTRE":
                hex_d = hex_d[:35] + "..."
            line = f"{ts} | [{type_t:8s}] {hex_d}\n"
            self.text_log.insert(tk.END, line)
        
        # Limiter le nombre de lignes (supprimer par gros blocs)
        num_lines = int(self.text_log.index('end-1c').split('.')[0])
        if num_lines > MAX_LOG_LINES:
            self.text_log.delete('1.0', f'{num_lines - MAX_LOG_LINES + 50}.0')
        
        # Auto-scroll
        self.text_log.see(tk.END)
        self.text_log.config(state='disabled')
        
        # Mettre à jour compteur
        num_lines = int(self.text_log.index('end-1c').split('.')[0]) - 1
        self.label_compteur.config(text=f"Total: {self.compteur_trames_total} | Affichées: {num_lines}")
    
    def on_slider_change(self, value):
        """Appelé quand un slider change."""
        self.gain_min = self.slider_min.get()
        self.gain_max = self.slider_max.get()
        
        # S'assurer que min < max
        if self.gain_min >= self.gain_max:
            self.gain_min = self.gain_max - 10
            self.slider_min.set(self.gain_min)
        
        # Mettre à jour le label
        self.label_gain.config(text=f"Plage: [{self.gain_min} - {self.gain_max}]")
        
        # Mettre à jour les graphiques si créés
        if hasattr(self, 'ax_spectre'):
            self.ax_spectre.set_ylim(self.gain_min, self.gain_max)
            self.image.set_clim(vmin=self.gain_min, vmax=self.gain_max)
            self.canvas.draw_idle()
    
    def creer_graphique(self):
        """Crée le graphique matplotlib intégré dans Tkinter."""
        
        # Calculer l'axe des fréquences
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Créer la figure matplotlib
        self.fig = Figure(figsize=(9, 6), facecolor='#1a1a2e')
        
        # Spectre
        self.ax_spectre = self.fig.add_subplot(211)
        self.ax_spectre.set_facecolor('#0a0a1a')
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', 
                                   color='white', fontsize=12, fontweight='bold')
        self.ax_spectre.set_xlabel('Fréquence (MHz)', color='white', fontsize=10)
        self.ax_spectre.set_ylabel('Amplitude', color='white', fontsize=10)
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_ylim(self.gain_min, self.gain_max)
        self.ax_spectre.tick_params(colors='white', labelsize=9)
        self.ax_spectre.grid(True, alpha=0.3, color='#444444')
        self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7, linewidth=2)
        self.ligne, = self.ax_spectre.plot(self.axe_freq, self.spectre_actuel, 
                                            color='#00ff00', linewidth=1.5)
        
        # Waterfall
        self.ax_waterfall = self.fig.add_subplot(212)
        self.ax_waterfall.set_facecolor('#0a0a1a')
        self.ax_waterfall.set_xlabel('Fréquence (MHz)', color='white', fontsize=10)
        self.ax_waterfall.set_ylabel('Temps', color='white', fontsize=10)
        self.ax_waterfall.tick_params(colors='white', labelsize=9)
        
        self.image = self.ax_waterfall.imshow(
            self.waterfall_data,
            aspect='auto',
            cmap='viridis',
            vmin=self.gain_min, vmax=self.gain_max,
            origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        
        self.fig.tight_layout()
        
        # Intégrer dans Tkinter (dans frame_graph, pas root)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_graph)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    
    def mettre_a_jour_axe_freq(self):
        """Met à jour l'axe des fréquences quand la fréquence centrale change."""
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Effacer et recréer la ligne centrale
        for line in self.ax_spectre.lines[1:]:
            line.remove()
        self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7, linewidth=2)
        
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', 
                                   color='white', fontsize=12, fontweight='bold')
        self.image.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
        self.ax_waterfall.set_xlim(freq_min, freq_max)
        self.canvas.draw()
    
    def toggle_connexion(self):
        """Connecte ou déconnecte du serveur."""
        if not self.connecte:
            self.connecter()
        else:
            self.deconnecter()
    
    def connecter(self):
        """Se connecte au serveur wfview."""
        ip = self.entry_ip.get()
        try:
            port = int(self.entry_port.get())
        except ValueError:
            messagebox.showerror("Erreur", "Port invalide!")
            return
        
        try:
            self.connexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connexion.settimeout(3)
            self.connexion.connect((ip, port))
            
            # Activer le streaming
            cmd = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x01, 0xFD])
            self.connexion.send(cmd)
            self.log_trame_envoyee(cmd, "Activation streaming")
            time.sleep(0.3)
            
            # Demander la fréquence
            cmd = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x03, 0xFD])
            self.connexion.send(cmd)
            self.log_trame_envoyee(cmd, "Demande fréquence")
            time.sleep(0.2)
            
            try:
                reponse = self.connexion.recv(1024)
                for i in range(len(reponse) - 10):
                    if reponse[i] == 0xFE and reponse[i+1] == 0xFE and reponse[i+4] == 0x03:
                        self.freq_centrale = decoder_frequence_bcd(reponse[i+5:i+10])
                        self.mettre_a_jour_axe_freq()
                        break
            except:
                pass
            
            # Mise à jour interface
            self.connecte = True
            self.label_status.config(text="🟢 Connecté", fg='#00ff88')
            self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            self.btn_connecter.config(text="🔌 Déconnecter", highlightbackground='#6e4a2a')
            self.btn_afficher.config(state='normal', highlightbackground='#2a6e4a')
            
        except Exception as e:
            messagebox.showerror("Erreur de connexion", f"Impossible de se connecter:\n{e}")
            if self.connexion:
                self.connexion.close()
                self.connexion = None
    
    def log_trame_envoyee(self, cmd, description):
        """Log une trame envoyée."""
        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        hex_data = trame_vers_hex(cmd)
        
        self.text_log.config(state='normal')
        self.text_log.insert(tk.END, ts, 'timestamp')
        self.text_log.insert(tk.END, " | ")
        self.text_log.insert(tk.END, f"[TX→ {description:15s}]", 'type_freq')
        self.text_log.insert(tk.END, " ")
        self.text_log.insert(tk.END, hex_data, 'hex')
        self.text_log.insert(tk.END, "\n")
        self.text_log.see(tk.END)
        self.text_log.config(state='disabled')
    
    def deconnecter(self):
        """Déconnecte du serveur."""
        if self.affichage_actif:
            self.arreter_affichage()
        
        if self.connexion:
            try:
                cmd = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x00, 0xFD])
                self.connexion.send(cmd)
                time.sleep(0.1)
                self.connexion.close()
            except:
                pass
            self.connexion = None
        
        self.connecte = False
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.label_freq.config(text="---")
        self.btn_connecter.config(text="🔌 Connecter", highlightbackground='#2a4a6e')
        self.btn_afficher.config(state='disabled', highlightbackground='#4a4a4a')
    
    def toggle_affichage(self):
        """Lance ou arrête l'affichage."""
        if not self.affichage_actif:
            self.lancer_affichage()
        else:
            self.arreter_affichage()
    
    def lancer_affichage(self):
        """Lance la réception et l'affichage."""
        self.affichage_actif = True
        self.btn_afficher.config(text="⏹ Arrêter", highlightbackground='#6e2a2a')
        self.btn_enregistrer.config(state='normal', highlightbackground='#6e2a4a')
        
        # Lancer la réception dans un thread
        self.thread_reception = threading.Thread(target=self.boucle_reception, daemon=True)
        self.thread_reception.start()
        
        # Lancer la mise à jour de l'affichage dans le thread principal
        self.mettre_a_jour_affichage()
        
        # Lancer la mise à jour du log séparément (moins fréquent)
        self.mettre_a_jour_log()
    
    def arreter_affichage(self):
        """Arrête l'affichage."""
        self.affichage_actif = False
        self.btn_afficher.config(text="▶ Démarrer", highlightbackground='#2a6e4a')
        self.btn_enregistrer.config(state='disabled', highlightbackground='#4a4a4a')
        
        # Arrêter l'enregistrement si actif
        if self.enregistrement_actif:
            self.arreter_enregistrement()
    
    def boucle_reception(self):
        """Boucle de réception des données (thread secondaire)."""
        buffer = bytearray()
        self.connexion.settimeout(0.1)
        
        # Compteur pour demander la fréquence périodiquement
        compteur_freq = 0
        
        while self.affichage_actif and self.connecte:
            try:
                data = self.connexion.recv(4096)
                buffer.extend(data)
            except socket.timeout:
                # Demander la fréquence toutes les ~20 itérations (2 secondes)
                compteur_freq += 1
                if compteur_freq >= 20:
                    compteur_freq = 0
                    try:
                        cmd_freq = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x03, 0xFD])
                        self.connexion.send(cmd_freq)
                    except:
                        pass
                continue
            except:
                break
            
            messages = trouver_messages_civ(buffer)
            
            for msg in messages:
                # Créer l'entrée de log avec timestamp
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                type_trame = identifier_type_trame(msg)
                hex_data = trame_vers_hex(msg)
                
                # Ajouter à la file des trames (thread-safe)
                with self.lock_trames:
                    self.compteur_trames_total += 1
                    # Limiter la taille de la file d'attente
                    if len(self.trames_a_logger) < 100:
                        self.trames_a_logger.append((timestamp, type_trame, hex_data))
                
                # Traiter les réponses de fréquence (commande 0x03)
                if len(msg) >= 11 and msg[4] == 0x03:
                    # Réponse fréquence : FE FE E0 A4 03 [5 octets BCD] FD
                    freq = decoder_frequence_bcd(msg[5:10])
                    if freq > 0:
                        self.nouvelle_frequence = freq
                
                # Traiter les données spectre
                if len(msg) >= 5 and msg[4] == 0x27 and len(msg) > 50:
                    amplitudes = extraire_donnees_spectre(msg)
                    if amplitudes is not None:
                        spectre = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        
                        self.spectre_actuel = spectre
                        self.waterfall_data[1:] = self.waterfall_data[:-1]
                        self.waterfall_data[0] = spectre
                        self.nouvelles_donnees = True
                        
                        # Enregistrer dans le CSV si actif
                        if self.enregistrement_actif:
                            self.enregistrer_spectre(spectre)
            
            if len(buffer) > 10000:
                buffer.clear()
    
    def mettre_a_jour_affichage(self):
        """Met à jour l'affichage graphique (appelé dans le thread principal)."""
        if not self.affichage_actif:
            return
        
        # Mettre à jour la fréquence si elle a changé
        if self.nouvelle_frequence is not None:
            if abs(self.nouvelle_frequence - self.freq_centrale) > 0.0001:  # Seuil de 100 Hz
                self.freq_centrale = self.nouvelle_frequence
                self.mettre_a_jour_axe_freq()
                self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            self.nouvelle_frequence = None
        
        # Mettre à jour les graphiques seulement
        if self.nouvelles_donnees:
            self.ligne.set_data(self.axe_freq, self.spectre_actuel)
            self.image.set_data(self.waterfall_data)
            self.canvas.draw_idle()
            self.nouvelles_donnees = False
        
        # Planifier la prochaine mise à jour (30ms = ~33 FPS)
        self.root.after(30, self.mettre_a_jour_affichage)
    
    def mettre_a_jour_log(self):
        """Met à jour le log des trames (moins fréquent pour éviter le lag)."""
        if not self.affichage_actif:
            return
        
        # Récupérer les trames en attente
        with self.lock_trames:
            trames = self.trames_a_logger.copy()
            self.trames_a_logger.clear()
        
        # Ajouter en batch
        if trames:
            self.ajouter_trames_batch(trames)
        
        # Planifier la prochaine mise à jour du log (moins fréquent)
        self.root.after(LOG_UPDATE_INTERVAL, self.mettre_a_jour_log)
    
    def toggle_enregistrement(self):
        """Démarre ou arrête l'enregistrement CSV."""
        if not self.enregistrement_actif:
            # Lire le seuil si trigger actif
            if self.trigger_actif.get():
                try:
                    self.seuil_trigger = float(self.entry_seuil.get())
                except ValueError:
                    messagebox.showerror("Erreur", "Seuil invalide ! Entrez un nombre.")
                    return
                self.au_dessus_seuil = False
                self.nb_fichiers_trigger = 0
                # En mode trigger, on ne crée pas le fichier tout de suite
                self.enregistrement_actif = True
                self.btn_enregistrer.config(text="⏹ STOP", highlightbackground='#ff2222')
                self.label_rec.config(text=f"⏺ TRIGGER: attente signal > {self.seuil_trigger}")
                # Désactiver la modification du trigger pendant l'enregistrement
                self.cb_trigger.config(state='disabled')
                self.entry_seuil.config(state='disabled')
            else:
                self.demarrer_enregistrement()
        else:
            self.arreter_enregistrement()
    
    def demarrer_enregistrement(self):
        """Démarre l'enregistrement dans un fichier CSV."""
        # Créer le dossier si nécessaire
        if not os.path.exists(DOSSIER_CSV):
            os.makedirs(DOSSIER_CSV)
        
        # Créer un nom de fichier unique avec timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.nom_fichier_csv = os.path.join(DOSSIER_CSV, f"spectre_{timestamp}.csv")
        
        try:
            self.fichier_csv = open(self.nom_fichier_csv, 'w', newline='')
            self.writer_csv = csv.writer(self.fichier_csv)
            
            # Écrire l'en-tête
            # Format: timestamp, freq_centrale, span_khz, valeur_0, valeur_1, ..., valeur_474
            header = ['timestamp', 'freq_mhz', 'span_khz']
            header.extend([f'val_{i}' for i in range(LARGEUR_SPECTRE)])
            self.writer_csv.writerow(header)
            
            self.enregistrement_actif = True
            self.nb_lignes_csv = 0
            
            # Mettre à jour l'interface
            self.btn_enregistrer.config(text="⏹ STOP", highlightbackground='#ff2222')
            self.label_rec.config(text=f"⏺ REC: {os.path.basename(self.nom_fichier_csv)}")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de créer le fichier CSV:\n{e}")
    
    def arreter_enregistrement(self):
        """Arrête l'enregistrement CSV."""
        if self.fichier_csv:
            try:
                self.fichier_csv.close()
            except:
                pass
            self.fichier_csv = None
            self.writer_csv = None
        
        self.enregistrement_actif = False
        self.au_dessus_seuil = False
        self.btn_enregistrer.config(text="⏺ REC", highlightbackground='#6e2a4a')
        
        # Réactiver les contrôles du trigger
        self.cb_trigger.config(state='normal')
        self.entry_seuil.config(state='normal')
        
        # Afficher un message de confirmation
        if self.trigger_actif.get() and self.nb_fichiers_trigger > 0:
            self.label_rec.config(text=f"✓ {self.nb_fichiers_trigger} fichier(s) trigger créé(s)")
            self.root.after(3000, lambda: self.label_rec.config(text=""))
        elif self.nom_fichier_csv and self.nb_lignes_csv > 0:
            self.label_rec.config(text=f"✓ {self.nb_lignes_csv} lignes sauvées")
            self.root.after(3000, lambda: self.label_rec.config(text=""))
        else:
            self.label_rec.config(text="")
    
    def enregistrer_spectre(self, spectre):
        """Enregistre une ligne de spectre dans le CSV."""
        if not self.enregistrement_actif:
            return
        
        # Mode Trigger
        if self.trigger_actif.get():
            max_signal = np.max(spectre)
            
            if max_signal >= self.seuil_trigger:
                # Signal au-dessus du seuil
                if not self.au_dessus_seuil:
                    # Transition : on passe au-dessus → créer nouveau fichier
                    self.au_dessus_seuil = True
                    self.creer_nouveau_csv_trigger()
                
                # Enregistrer si on a un fichier ouvert
                if self.writer_csv:
                    self.ecrire_ligne_csv(spectre)
            else:
                # Signal en-dessous du seuil
                if self.au_dessus_seuil:
                    # Transition : on passe en-dessous → fermer le fichier
                    self.au_dessus_seuil = False
                    self.fermer_csv_trigger()
                    self.label_rec.config(text=f"⏺ TRIGGER: attente signal > {self.seuil_trigger}")
        else:
            # Mode normal (sans trigger)
            if self.writer_csv:
                self.ecrire_ligne_csv(spectre)
    
    def creer_nouveau_csv_trigger(self):
        """Crée un nouveau fichier CSV pour le trigger."""
        # Fermer le fichier précédent si ouvert
        if self.fichier_csv:
            try:
                self.fichier_csv.close()
            except:
                pass
        
        # Créer le dossier si nécessaire
        if not os.path.exists(DOSSIER_CSV):
            os.makedirs(DOSSIER_CSV)
        
        # Créer un nom de fichier unique avec timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # Avec millisecondes
        self.nb_fichiers_trigger += 1
        self.nom_fichier_csv = os.path.join(DOSSIER_CSV, f"trigger_{timestamp}.csv")
        
        try:
            self.fichier_csv = open(self.nom_fichier_csv, 'w', newline='')
            self.writer_csv = csv.writer(self.fichier_csv)
            
            # Écrire l'en-tête
            header = ['timestamp', 'freq_mhz', 'span_khz']
            header.extend([f'val_{i}' for i in range(LARGEUR_SPECTRE)])
            self.writer_csv.writerow(header)
            
            self.nb_lignes_csv = 0
            self.label_rec.config(text=f"⏺ TRIGGER #{self.nb_fichiers_trigger}: enregistrement...")
            
        except Exception as e:
            print(f"Erreur création CSV trigger: {e}")
    
    def fermer_csv_trigger(self):
        """Ferme le fichier CSV trigger actuel."""
        if self.fichier_csv:
            try:
                self.fichier_csv.flush()
                self.fichier_csv.close()
            except:
                pass
            self.fichier_csv = None
            self.writer_csv = None
            print(f"Trigger CSV fermé: {self.nb_lignes_csv} lignes")
    
    def ecrire_ligne_csv(self, spectre):
        """Écrit une ligne de spectre dans le CSV."""
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            ligne = [ts, f"{self.freq_centrale:.6f}", SPAN_KHZ]
            ligne.extend([f"{v:.1f}" for v in spectre])
            
            self.writer_csv.writerow(ligne)
            self.nb_lignes_csv += 1
            
            # Flush périodiquement
            if self.nb_lignes_csv % 100 == 0:
                self.fichier_csv.flush()
                if self.trigger_actif.get():
                    self.label_rec.config(text=f"⏺ TRIGGER #{self.nb_fichiers_trigger}: {self.nb_lignes_csv} lignes")
                else:
                    self.label_rec.config(text=f"⏺ REC: {self.nb_lignes_csv} lignes")
                
        except Exception as e:
            print(f"Erreur écriture CSV: {e}")
    
    def ouvrir_csv(self):
        """Ouvre un fichier CSV ou ferme le mode lecture."""
        # Si on est déjà en mode lecture, fermer
        if self.mode_lecture_csv:
            self.fermer_csv()
            return
        
        # Arrêter tout affichage en cours
        if self.affichage_actif:
            self.arreter_affichage()
        if self.connecte:
            self.deconnecter()
        
        # Sélectionner le fichier
        fichier = filedialog.askopenfilename(
            title="Ouvrir un fichier CSV",
            initialdir=DOSSIER_CSV if os.path.exists(DOSSIER_CSV) else ".",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")]
        )
        
        if not fichier:
            return
        
        try:
            # Lire le CSV
            self.donnees_csv = []
            with open(fichier, 'r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader)  # Sauter l'en-tête
                
                for row in reader:
                    if len(row) >= 3 + LARGEUR_SPECTRE:
                        timestamp = row[0]
                        freq = float(row[1])
                        span = int(row[2])
                        valeurs = np.array([float(v) for v in row[3:3+LARGEUR_SPECTRE]])
                        self.donnees_csv.append({
                            'timestamp': timestamp,
                            'freq': freq,
                            'span': span,
                            'spectre': valeurs
                        })
            
            if not self.donnees_csv:
                messagebox.showerror("Erreur", "Aucune donnée valide dans le fichier CSV")
                return
            
            # Passer en mode lecture CSV
            self.mode_lecture_csv = True
            self.index_lecture = 0
            
            # Mettre à jour l'interface
            self.label_status.config(text=f"📂 CSV: {len(self.donnees_csv)} lignes", fg='#00ccff')
            self.btn_ouvrir_csv.config(text="❌ Fermer CSV", highlightbackground='#6e2a2a')
            
            # Désactiver les boutons de connexion
            self.btn_connecter.config(state='disabled')
            self.entry_ip.config(state='disabled')
            self.entry_port.config(state='disabled')
            
            # Charger les données et mettre à jour l'affichage
            self.charger_donnees_csv()
            
            # Créer les contrôles de lecture
            self.creer_controles_lecture()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier CSV:\n{e}")
    
    def fermer_csv(self):
        """Ferme le mode lecture CSV."""
        self.mode_lecture_csv = False
        self.donnees_csv = None
        
        # Supprimer les contrôles de lecture
        if hasattr(self, 'frame_lecture'):
            self.frame_lecture.destroy()
            del self.frame_lecture
        
        # Réactiver l'interface normale
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.btn_ouvrir_csv.config(text="📂 Open CSV", highlightbackground='#4a6e2a')
        self.btn_connecter.config(state='normal')
        self.entry_ip.config(state='normal')
        self.entry_port.config(state='normal')
        self.label_freq.config(text="---")
        
        # Réinitialiser les données
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.freq_centrale = FREQUENCE_DEFAUT
        self.mettre_a_jour_axe_freq()
        
        # Rafraîchir l'affichage
        self.ligne.set_data(self.axe_freq, self.spectre_actuel)
        self.image.set_data(self.waterfall_data)
        self.canvas.draw_idle()
    
    def creer_controles_lecture(self):
        """Crée les contrôles pour naviguer da  ns le CSV."""
        # Supprimer l'ancien frame s'il existe
        if hasattr(self, 'frame_lecture'):
            self.frame_lecture.destroy()
        
        # Frame pour les contrôles de lecture
        self.frame_lecture = tk.Frame(self.root, bg='#1a1a2e')
        # Le placer après les sliders mais avant le graphique
        # On utilise pack avec before pour le mettre au bon endroit
        self.frame_lecture.pack(fill='x', padx=10, pady=5, before=self.frame_principal)
        
        # Label titre
        tk.Label(
            self.frame_lecture,
            text="📼 Lecture CSV:",
            font=("Helvetica", 11, "bold"),
            fg='#00ccff',
            bg='#1a1a2e'
        ).pack(side='left', padx=10)
        
        # Boutons de navigation
        self.btn_debut = tk.Button(
            self.frame_lecture, text="⏮", font=("Helvetica", 12),
            width=3, highlightbackground='#2a4a6e',
            command=lambda: self.aller_a_position(0)
        )
        self.btn_debut.pack(side='left', padx=2)
        
        self.btn_reculer = tk.Button(
            self.frame_lecture, text="◀", font=("Helvetica", 12),
            width=3, highlightbackground='#2a4a6e',
            command=lambda: self.aller_a_position(max(0, self.index_lecture - 10))
        )
        self.btn_reculer.pack(side='left', padx=2)
        
        self.btn_play = tk.Button(
            self.frame_lecture, text="▶ Play", font=("Helvetica", 11, "bold"),
            width=8, highlightbackground='#2a6e4a',
            command=self.toggle_lecture
        )
        self.btn_play.pack(side='left', padx=5)
        
        self.btn_avancer = tk.Button(
            self.frame_lecture, text="▶", font=("Helvetica", 12),
            width=3, highlightbackground='#2a4a6e',
            command=lambda: self.aller_a_position(min(len(self.donnees_csv)-1, self.index_lecture + 10))
        )
        self.btn_avancer.pack(side='left', padx=2)
        
        self.btn_fin = tk.Button(
            self.frame_lecture, text="⏭", font=("Helvetica", 12),
            width=3, highlightbackground='#2a4a6e',
            command=lambda: self.aller_a_position(len(self.donnees_csv) - 1)
        )
        self.btn_fin.pack(side='left', padx=2)
        
        # Slider de position
        self.slider_position = tk.Scale(
            self.frame_lecture,
            from_=0, to=len(self.donnees_csv) - 1,
            orient='horizontal',
            length=300,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 9),
            command=self.on_slider_position_change
        )
        self.slider_position.pack(side='left', padx=10)
        
        # Label position/timestamp
        self.label_position = tk.Label(
            self.frame_lecture,
            text="0 / 0",
            font=("Helvetica", 10),
            fg='#aaaaaa',
            bg='#1a1a2e',
            width=20
        )
        self.label_position.pack(side='left', padx=10)
        
        # Slider vitesse
        tk.Label(
            self.frame_lecture,
            text="Vitesse:",
            font=("Helvetica", 10),
            fg='#aaaaaa',
            bg='#1a1a2e'
        ).pack(side='left', padx=5)
        
        self.slider_vitesse = tk.Scale(
            self.frame_lecture,
            from_=1, to=50,
            orient='horizontal',
            length=100,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 9)
        )
        self.slider_vitesse.set(10)
        self.slider_vitesse.pack(side='left', padx=5)
    
    def on_slider_position_change(self, value):
        """Appelé quand le slider de position change."""
        self.aller_a_position(int(value))
    
    def aller_a_position(self, index):
        """Va à une position spécifique dans le CSV."""
        if not self.donnees_csv or index < 0 or index >= len(self.donnees_csv):
            return
        
        self.index_lecture = index
        self.charger_donnees_csv()
        
        # Mettre à jour le slider sans déclencher l'événement
        self.slider_position.set(index)
    
    def charger_donnees_csv(self):
        """Charge et affiche les données à la position actuelle."""
        if not self.donnees_csv:
            return
        
        data = self.donnees_csv[self.index_lecture]
        
        # Mettre à jour la fréquence si elle a changé
        if data['freq'] != self.freq_centrale:
            self.freq_centrale = data['freq']
            # Recalculer l'axe avec le span du fichier
            demi_span = data['span'] / 2000
            freq_min = self.freq_centrale - demi_span
            freq_max = self.freq_centrale + demi_span
            self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
            
            # Mettre à jour les axes
            self.ax_spectre.set_xlim(freq_min, freq_max)
            self.ax_spectre.set_title(f"Spectre IC-705 - {self.freq_centrale:.3f} MHz (CSV)", 
                                       color='white', fontsize=12, fontweight='bold')
            self.image.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
            
            # Mettre à jour la ligne centrale
            for line in self.ax_spectre.lines[1:]:
                line.remove()
            self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7, linewidth=2)
        
        # Mettre à jour le spectre actuel
        self.spectre_actuel = data['spectre']
        
        # Construire le waterfall avec les lignes précédentes
        start_idx = max(0, self.index_lecture - PROFONDEUR_WATERFALL + 1)
        waterfall_lines = []
        for i in range(start_idx, self.index_lecture + 1):
            waterfall_lines.append(self.donnees_csv[i]['spectre'])
        
        # Remplir le waterfall (les lignes les plus récentes en haut)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        for i, line in enumerate(reversed(waterfall_lines)):
            if i < PROFONDEUR_WATERFALL:
                self.waterfall_data[i] = line
        
        # Mettre à jour l'affichage
        self.ligne.set_data(self.axe_freq, self.spectre_actuel)
        self.image.set_data(self.waterfall_data)
        self.canvas.draw_idle()
        
        # Mettre à jour les labels
        self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
        if hasattr(self, 'label_position'):
            self.label_position.config(
                text=f"{self.index_lecture + 1} / {len(self.donnees_csv)} - {data['timestamp'][-12:]}"
            )
    
    def toggle_lecture(self):
        """Démarre ou arrête la lecture automatique."""
        if self.lecture_en_cours:
            self.arreter_lecture()
        else:
            self.demarrer_lecture()
    
    def demarrer_lecture(self):
        """Démarre la lecture automatique."""
        self.lecture_en_cours = True
        self.btn_play.config(text="⏸ Pause", highlightbackground='#6e6e2a')
        self.lecture_auto()
    
    def arreter_lecture(self):
        """Arrête la lecture automatique."""
        self.lecture_en_cours = False
        self.btn_play.config(text="▶ Play", highlightbackground='#2a6e4a')
    
    def lecture_auto(self):
        """Boucle de lecture automatique."""
        if not self.lecture_en_cours or not self.mode_lecture_csv:
            return
        
        # Avancer d'une position
        if self.index_lecture < len(self.donnees_csv) - 1:
            self.index_lecture += 1
            self.charger_donnees_csv()
            self.slider_position.set(self.index_lecture)
            
            # Calculer le délai basé sur la vitesse (1-50 → 200ms-4ms)
            vitesse = self.slider_vitesse.get()
            delai = max(4, 200 // vitesse)
            
            # Planifier la prochaine mise à jour
            self.root.after(delai, self.lecture_auto)
        else:
            # Fin du fichier
            self.arreter_lecture()
    
    def quitter(self):
        """Ferme l'application proprement."""
        if self.mode_lecture_csv:
            self.fermer_csv()
        self.arreter_affichage()
        self.deconnecter()
        self.root.quit()
        self.root.destroy()


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == '__main__':
    root = tk.Tk()
    app = IC705App(root)
    root.mainloop()
