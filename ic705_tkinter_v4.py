#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC-705 Spectrum Display avec Tkinter - Version 4
================================================
Version complète avec toutes les fonctionnalités.

Fonctionnalités:
- Affichage du spectre et waterfall en temps réel
- Panneau de log des trames CI-V en hexadécimal
- Sliders de gain min/max
- Enregistrement CSV
- Mode Trigger pour l'enregistrement
- Lecture de fichiers CSV
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

# Forcer le backend TkAgg pour matplotlib
import matplotlib
matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ============================================================
#              PARAMÈTRES DE CONFIGURATION
# ============================================================

SERVEUR_IP = "127.0.0.1"
SERVEUR_PORT = 50002
ADRESSE_RADIO = 0xA4
ADRESSE_PC = 0xE0
FREQUENCE_DEFAUT = 7.100
SPAN_KHZ = 200
LARGEUR_SPECTRE = 950  # Augmenté pour plus de détails
PROFONDEUR_WATERFALL = 80  # Réduit pour maintenir les performances
MAX_LOG_LINES = 200
LOG_UPDATE_INTERVAL = 300  # Moins fréquent pour économiser des ressources
MAX_TRAMES_PAR_UPDATE = 15
DOSSIER_CSV = "recep_csv"


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
# ============================================================

def decoder_frequence_bcd(data):
    """Décode une fréquence en BCD (5 octets) vers MHz."""
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
    """Extrait tous les messages CI-V complets d'un buffer."""
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
    """Extrait les amplitudes d'une trame spectre (commande 0x27)."""
    if len(msg) < 20:
        return None
    
    idx_start = 19
    idx_end = len(msg) - 1
    
    if idx_start >= idx_end:
        return None
    
    return np.array(list(msg[idx_start:idx_end]), dtype=np.float32)


def redimensionner_spectre(donnees, largeur_cible):
    """Redimensionne un spectre à la largeur souhaitée."""
    if donnees is None or len(donnees) == 0:
        return np.zeros(largeur_cible)
    
    taille_originale = len(donnees)
    
    if taille_originale >= largeur_cible:
        indices = np.linspace(0, taille_originale - 1, largeur_cible, dtype=int)
        return donnees[indices]
    else:
        x_original = np.linspace(0, 1, len(donnees))
        x_nouveau = np.linspace(0, 1, largeur_cible)
        return np.interp(x_nouveau, x_original, donnees)


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

class IC705AppV4:
    """Application principale avec interface Tkinter - Version 4."""
    
    def __init__(self, root):
        """Initialise l'application."""
        self.root = root
        self.root.title("IC-705 Spectrum Display v4")
        self.root.geometry("1400x800")
        self.root.configure(bg='#1a1a2e')
        self.root.minsize(1200, 600)
        
        # Variables d'état
        self.connexion = None
        self.connecte = False
        self.affichage_actif = False
        self.freq_centrale = FREQUENCE_DEFAUT
        self.thread_reception = None
        self.nouvelle_frequence = None
        
        # Données du spectre et waterfall
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.nouvelles_donnees = False
        self.lock_donnees = threading.Lock()
        
        # Paramètres de gain
        self.gain_min = 0
        self.gain_max = 200
        
        # File des trames à afficher (thread-safe)
        self.trames_a_logger = []
        self.lock_trames = threading.Lock()
        self.compteur_trames_total = 0
        
        # Options de log
        self.log_spectre = tk.BooleanVar(value=False)
        self.log_autres = tk.BooleanVar(value=True)
        self.log_actif = tk.BooleanVar(value=True)
        
        # Enregistrement CSV
        self.enregistrement_actif = False
        self.fichier_csv = None
        self.writer_csv = None
        self.nom_fichier_csv = None
        self.nb_lignes_csv = 0
        
        # Trigger pour enregistrement
        self.trigger_actif = tk.BooleanVar(value=False)
        self.seuil_trigger = 70
        self.au_dessus_seuil = False
        self.nb_fichiers_trigger = 0
        
        # Mode lecture CSV
        self.mode_lecture_csv = False
        self.donnees_csv = None
        self.index_lecture = 0
        self.lecture_en_cours = False
        
        # Créer l'interface
        self.creer_interface()
        self.creer_graphique()
        
        # Gestion de la fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)
    
    def creer_interface(self):
        """Crée les widgets de l'interface."""
        
        # === Frame du haut pour les contrôles ===
        frame_controles = tk.Frame(self.root, bg='#1a1a2e')
        frame_controles.pack(fill='x', padx=10, pady=10)
        
        # Titre
        titre = tk.Label(
            frame_controles,
            text="📡 IC-705 Spectrum Display v4",
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
        
        # Boutons
        self.btn_connecter = tk.Button(
            frame_controles,
            text="🔌 Connecter",
            font=("Helvetica", 12, "bold"),
            width=14,
            command=self.toggle_connexion
        )
        self.btn_connecter.pack(side='left', padx=10)
        
        self.btn_afficher = tk.Button(
            frame_controles,
            text="▶ Démarrer",
            font=("Helvetica", 12, "bold"),
            width=14,
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
            state='disabled',
            command=self.toggle_enregistrement
        )
        self.btn_enregistrer.pack(side='left', padx=5)
        
        # Frame pour le trigger
        frame_trigger = tk.Frame(frame_controles, bg='#1a1a2e')
        frame_trigger.pack(side='left', padx=5)
        
        self.cb_trigger = tk.Checkbutton(
            frame_trigger,
            text="Trigger >",
            variable=self.trigger_actif,
            font=('Helvetica', 10, 'bold'),
            bg='#1a1a2e',
            fg='white',
            selectcolor='#2a2a4e'
        )
        self.cb_trigger.pack(side='left')
        
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
        
        # === Frame pour les sliders de gain ===
        frame_sliders = tk.Frame(self.root, bg='#1a1a2e')
        frame_sliders.pack(fill='x', padx=10, pady=5)
        
        tk.Label(frame_sliders, text="Gain Min:", fg='#4a90d9', bg='#1a1a2e', 
                 font=('Helvetica', 11, 'bold')).pack(side='left', padx=5)
        self.slider_min = tk.Scale(
            frame_sliders,
            from_=0, to=100,
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
        frame_log.pack_propagate(False)
        
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
            font=('Helvetica', 9)
        )
        cb_autres.pack(side='left', padx=5)
        
        self.btn_pause_log = tk.Button(
            frame_options,
            text="⏸",
            font=("Helvetica", 9),
            width=3,
            command=self.toggle_log_pause
        )
        self.btn_pause_log.pack(side='left', padx=2)
        
        btn_clear = tk.Button(
            frame_options,
            text="🗑 Clear",
            font=("Helvetica", 9),
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
            self.btn_pause_log.config(text="▶")
        else:
            self.log_actif.set(True)
            self.btn_pause_log.config(text="⏸")
    
    def clear_log(self):
        """Efface le log des trames."""
        self.text_log.config(state='normal')
        self.text_log.delete('1.0', tk.END)
        self.text_log.config(state='disabled')
        self.compteur_trames_total = 0
        self.label_compteur.config(text="Total: 0 | Affichées: 0")
    
    def ajouter_trames_batch(self, trames):
        """Ajoute plusieurs trames au log en une seule opération."""
        if not trames or not self.log_actif.get():
            return
        
        trames_filtrees = []
        for ts, type_t, hex_d in trames:
            if type_t == "SPECTRE" and not self.log_spectre.get():
                continue
            if type_t != "SPECTRE" and not self.log_autres.get():
                continue
            trames_filtrees.append((ts, type_t, hex_d))
        
        if not trames_filtrees:
            return
        
        if len(trames_filtrees) > MAX_TRAMES_PAR_UPDATE:
            trames_filtrees = trames_filtrees[-MAX_TRAMES_PAR_UPDATE:]
        
        self.text_log.config(state='normal')
        
        for ts, type_t, hex_d in trames_filtrees:
            if type_t == "SPECTRE":
                hex_d = hex_d[:35] + "..."
            line = f"{ts} | [{type_t:8s}] {hex_d}\n"
            self.text_log.insert(tk.END, line)
        
        num_lines = int(self.text_log.index('end-1c').split('.')[0])
        if num_lines > MAX_LOG_LINES:
            self.text_log.delete('1.0', f'{num_lines - MAX_LOG_LINES + 50}.0')
        
        self.text_log.see(tk.END)
        self.text_log.config(state='disabled')
        
        num_lines = int(self.text_log.index('end-1c').split('.')[0]) - 1
        self.label_compteur.config(text=f"Total: {self.compteur_trames_total} | Affichées: {num_lines}")
    
    def on_slider_change(self, value):
        """Appelé quand un slider change."""
        self.gain_min = self.slider_min.get()
        self.gain_max = self.slider_max.get()
        
        if self.gain_min >= self.gain_max:
            self.gain_min = self.gain_max - 10
            self.slider_min.set(self.gain_min)
        
        self.label_gain.config(text=f"Plage: [{self.gain_min} - {self.gain_max}]")
        
        if hasattr(self, 'ax_spectre'):
            self.ax_spectre.set_ylim(self.gain_min, self.gain_max)
            self.image_waterfall.set_clim(vmin=self.gain_min, vmax=self.gain_max)
            self.canvas.draw()
            # Recréer le background après modification
            if hasattr(self, 'use_blit') and self.use_blit:
                self.background = self.canvas.copy_from_bbox(self.fig.bbox)
    
    def creer_graphique(self):
        """Crée le graphique matplotlib - IDENTIQUE à ic705_simple.py."""
        
        # Calculer l'axe des fréquences
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Créer la figure avec 2 sous-graphiques
        self.fig, (self.ax_spectre, self.ax_waterfall) = plt.subplots(
            2, 1, figsize=(9, 6), facecolor='#1a1a2e'
        )
        
        # Style sombre
        self.ax_spectre.set_facecolor('#0a0a1a')
        self.ax_waterfall.set_facecolor('#0a0a1a')
        
        # === Configurer le spectre ===
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
        self.ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_spectre.set_ylabel('Amplitude', color='white')
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_ylim(self.gain_min, self.gain_max)
        self.ax_spectre.tick_params(colors='white')
        self.ax_spectre.grid(True, alpha=0.3)
        
        # Ligne verticale rouge au centre
        self.ligne_centre = self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7)
        
        # Créer la ligne du spectre
        self.ligne_spectre, = self.ax_spectre.plot(
            self.axe_freq, 
            np.zeros(LARGEUR_SPECTRE), 
            color='yellow', 
            linewidth=1,
            animated=True  # Active le blitting pour de meilleures performances
        )
        
        # === Configurer le waterfall ===
        self.ax_waterfall.set_title('Waterfall', color='white')
        self.ax_waterfall.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_waterfall.set_ylabel('Temps', color='white')
        self.ax_waterfall.tick_params(colors='white')
        
        # Créer l'image du waterfall
        self.image_waterfall = self.ax_waterfall.imshow(
            np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE)),
            aspect='auto',
            cmap='viridis',
            vmin=self.gain_min, vmax=self.gain_max,
            origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        
        self.fig.tight_layout()
        
        # Intégrer dans Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_graph)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # Sauvegarder le background pour le blitting (optimisation)
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)
        self.use_blit = True
    
    def mettre_a_jour_axe_freq(self):
        """Met à jour l'axe des fréquences quand la fréquence centrale change."""
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Mettre à jour la ligne centrale
        self.ligne_centre.set_xdata([self.freq_centrale, self.freq_centrale])
        
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
        self.image_waterfall.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
        self.ax_waterfall.set_xlim(freq_min, freq_max)
        self.canvas.draw()
        # Recréer le background après modification
        if hasattr(self, 'use_blit') and self.use_blit:
            self.background = self.canvas.copy_from_bbox(self.fig.bbox)
    
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
            self.btn_connecter.config(text="🔌 Déconnecter")
            self.btn_afficher.config(state='normal')
            
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
        self.text_log.insert(tk.END, f"{ts} | [TX→ {description:15s}] {hex_data}\n")
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
        self.btn_connecter.config(text="🔌 Connecter")
        self.btn_afficher.config(state='disabled')
    
    def toggle_affichage(self):
        """Lance ou arrête l'affichage."""
        if not self.affichage_actif:
            self.lancer_affichage()
        else:
            self.arreter_affichage()
    
    def lancer_affichage(self):
        """Lance la réception et l'affichage."""
        self.affichage_actif = True
        self.btn_afficher.config(text="⏹ Arrêter")
        self.btn_enregistrer.config(state='normal')
        
        # Lancer la réception dans un thread
        self.thread_reception = threading.Thread(target=self.boucle_reception, daemon=True)
        self.thread_reception.start()
        
        # Lancer la mise à jour de l'affichage
        self.boucle_affichage()
        
        # Lancer la mise à jour du log
        self.boucle_log()
    
    def arreter_affichage(self):
        """Arrête l'affichage."""
        self.affichage_actif = False
        self.btn_afficher.config(text="▶ Démarrer")
        self.btn_enregistrer.config(state='disabled')
        
        if self.enregistrement_actif:
            self.arreter_enregistrement()
    
    def boucle_reception(self):
        """Boucle de réception des données (thread secondaire)."""
        buffer = bytearray()
        self.connexion.settimeout(0.1)
        compteur_freq = 0
        
        while self.affichage_actif and self.connecte:
            try:
                data = self.connexion.recv(4096)
                buffer.extend(data)
            except socket.timeout:
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
                # Créer l'entrée de log
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                type_trame = identifier_type_trame(msg)
                hex_data = trame_vers_hex(msg)
                
                with self.lock_trames:
                    self.compteur_trames_total += 1
                    if len(self.trames_a_logger) < 100:
                        self.trames_a_logger.append((timestamp, type_trame, hex_data))
                
                # Traiter les réponses de fréquence (commande 0x03)
                if len(msg) >= 11 and msg[4] == 0x03:
                    freq = decoder_frequence_bcd(msg[5:10])
                    if freq > 0:
                        self.nouvelle_frequence = freq
                
                # Traiter les données spectre (commande 0x27)
                if len(msg) >= 5 and msg[4] == 0x27 and len(msg) > 50:
                    amplitudes = extraire_donnees_spectre(msg)
                    if amplitudes is not None:
                        spectre = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        
                        with self.lock_donnees:
                            self.spectre_actuel = spectre.copy()
                            self.waterfall_data[1:] = self.waterfall_data[:-1]
                            self.waterfall_data[0] = spectre.copy()
                            self.nouvelles_donnees = True
                        
                        # Enregistrer dans le CSV si actif
                        if self.enregistrement_actif:
                            self.enregistrer_spectre(spectre)
            
            if len(buffer) > 10000:
                buffer.clear()
    
    def boucle_affichage(self):
        """Boucle de mise à jour de l'affichage (thread principal)."""
        if not self.affichage_actif:
            return
        
        # Mettre à jour la fréquence si elle a changé
        if self.nouvelle_frequence is not None:
            if abs(self.nouvelle_frequence - self.freq_centrale) > 0.0001:
                self.freq_centrale = self.nouvelle_frequence
                self.mettre_a_jour_axe_freq()
                self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            self.nouvelle_frequence = None
        
        # Mettre à jour les graphiques si nouvelles données
        with self.lock_donnees:
            if self.nouvelles_donnees:
                spectre = self.spectre_actuel.copy()
                waterfall = self.waterfall_data.copy()
                self.nouvelles_donnees = False
            else:
                spectre = None
                waterfall = None
        
        if spectre is not None:
            try:
                if self.use_blit and hasattr(self, 'background'):
                    # Utiliser le blitting pour de meilleures performances
                    self.canvas.restore_region(self.background)
                    
                    # Mise à jour du spectre
                    self.ligne_spectre.set_data(self.axe_freq, spectre)
                    
                    # Mise à jour du waterfall
                    self.image_waterfall.set_data(waterfall)
                    
                    # Redessiner uniquement les éléments modifiés
                    self.ax_spectre.draw_artist(self.ligne_spectre)
                    self.ax_waterfall.draw_artist(self.image_waterfall)
                    
                    # Rafraîchir le canvas
                    self.canvas.blit(self.fig.bbox)
                    self.canvas.flush_events()
                else:
                    # Fallback sans blitting
                    self.ligne_spectre.set_data(self.axe_freq, spectre)
                    self.image_waterfall.set_data(waterfall)
                    self.canvas.draw_idle()
            except:
                # Si le blitting échoue, désactiver et utiliser draw_idle
                self.use_blit = False
                self.ligne_spectre.set_data(self.axe_freq, spectre)
                self.image_waterfall.set_data(waterfall)
                self.canvas.draw_idle()
        
        # Planifier la prochaine mise à jour (40ms = 25 FPS)
        self.root.after(40, self.boucle_affichage)
    
    def boucle_log(self):
        """Met à jour le log des trames."""
        if not self.affichage_actif:
            return
        
        with self.lock_trames:
            trames = self.trames_a_logger.copy()
            self.trames_a_logger.clear()
        
        if trames:
            self.ajouter_trames_batch(trames)
        
        self.root.after(LOG_UPDATE_INTERVAL, self.boucle_log)
    
    # === Fonctions d'enregistrement CSV ===
    
    def toggle_enregistrement(self):
        """Démarre ou arrête l'enregistrement CSV."""
        if not self.enregistrement_actif:
            if self.trigger_actif.get():
                try:
                    self.seuil_trigger = float(self.entry_seuil.get())
                except ValueError:
                    messagebox.showerror("Erreur", "Seuil invalide !")
                    return
                self.au_dessus_seuil = False
                self.nb_fichiers_trigger = 0
                self.enregistrement_actif = True
                self.btn_enregistrer.config(text="⏹ STOP")
                self.label_rec.config(text=f"⏺ TRIGGER: attente signal > {self.seuil_trigger}")
                self.cb_trigger.config(state='disabled')
                self.entry_seuil.config(state='disabled')
            else:
                self.demarrer_enregistrement()
        else:
            self.arreter_enregistrement()
    
    def demarrer_enregistrement(self):
        """Démarre l'enregistrement dans un fichier CSV."""
        if not os.path.exists(DOSSIER_CSV):
            os.makedirs(DOSSIER_CSV)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.nom_fichier_csv = os.path.join(DOSSIER_CSV, f"spectre_{timestamp}.csv")
        
        try:
            self.fichier_csv = open(self.nom_fichier_csv, 'w', newline='')
            self.writer_csv = csv.writer(self.fichier_csv)
            
            header = ['timestamp', 'freq_mhz', 'span_khz']
            header.extend([f'val_{i}' for i in range(LARGEUR_SPECTRE)])
            self.writer_csv.writerow(header)
            
            self.enregistrement_actif = True
            self.nb_lignes_csv = 0
            
            self.btn_enregistrer.config(text="⏹ STOP")
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
        self.btn_enregistrer.config(text="⏺ REC")
        
        self.cb_trigger.config(state='normal')
        self.entry_seuil.config(state='normal')
        
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
        
        if self.trigger_actif.get():
            max_signal = np.max(spectre)
            
            if max_signal >= self.seuil_trigger:
                if not self.au_dessus_seuil:
                    self.au_dessus_seuil = True
                    self.creer_nouveau_csv_trigger()
                
                if self.writer_csv:
                    self.ecrire_ligne_csv(spectre)
            else:
                if self.au_dessus_seuil:
                    self.au_dessus_seuil = False
                    self.fermer_csv_trigger()
                    self.label_rec.config(text=f"⏺ TRIGGER: attente signal > {self.seuil_trigger}")
        else:
            if self.writer_csv:
                self.ecrire_ligne_csv(spectre)
    
    def creer_nouveau_csv_trigger(self):
        """Crée un nouveau fichier CSV pour le trigger."""
        if self.fichier_csv:
            try:
                self.fichier_csv.close()
            except:
                pass
        
        if not os.path.exists(DOSSIER_CSV):
            os.makedirs(DOSSIER_CSV)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        self.nb_fichiers_trigger += 1
        self.nom_fichier_csv = os.path.join(DOSSIER_CSV, f"trigger_{timestamp}.csv")
        
        try:
            self.fichier_csv = open(self.nom_fichier_csv, 'w', newline='')
            self.writer_csv = csv.writer(self.fichier_csv)
            
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
    
    def ecrire_ligne_csv(self, spectre):
        """Écrit une ligne de spectre dans le CSV."""
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            ligne = [ts, f"{self.freq_centrale:.6f}", SPAN_KHZ]
            ligne.extend([f"{v:.1f}" for v in spectre])
            
            self.writer_csv.writerow(ligne)
            self.nb_lignes_csv += 1
            
            if self.nb_lignes_csv % 100 == 0:
                self.fichier_csv.flush()
                if self.trigger_actif.get():
                    self.label_rec.config(text=f"⏺ TRIGGER #{self.nb_fichiers_trigger}: {self.nb_lignes_csv} lignes")
                else:
                    self.label_rec.config(text=f"⏺ REC: {self.nb_lignes_csv} lignes")
                
        except Exception as e:
            print(f"Erreur écriture CSV: {e}")
    
    # === Fonctions de lecture CSV ===
    
    def ouvrir_csv(self):
        """Ouvre un fichier CSV ou ferme le mode lecture."""
        if self.mode_lecture_csv:
            self.fermer_csv_lecture()
            return
        
        if self.affichage_actif:
            self.arreter_affichage()
        if self.connecte:
            self.deconnecter()
        
        fichier = filedialog.askopenfilename(
            title="Ouvrir un fichier CSV",
            initialdir=DOSSIER_CSV if os.path.exists(DOSSIER_CSV) else ".",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")]
        )
        
        if not fichier:
            return
        
        try:
            self.donnees_csv = []
            with open(fichier, 'r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader)
                
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
            
            self.mode_lecture_csv = True
            self.index_lecture = 0
            
            self.label_status.config(text=f"📂 CSV: {len(self.donnees_csv)} lignes", fg='#00ccff')
            self.btn_ouvrir_csv.config(text="❌ Fermer CSV")
            
            self.btn_connecter.config(state='disabled')
            self.entry_ip.config(state='disabled')
            self.entry_port.config(state='disabled')
            
            self.charger_donnees_csv()
            self.creer_controles_lecture()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier CSV:\n{e}")
    
    def fermer_csv_lecture(self):
        """Ferme le mode lecture CSV."""
        self.mode_lecture_csv = False
        self.donnees_csv = None
        
        if hasattr(self, 'frame_lecture'):
            self.frame_lecture.destroy()
            del self.frame_lecture
        
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.btn_ouvrir_csv.config(text="📂 Open CSV")
        self.btn_connecter.config(state='normal')
        self.entry_ip.config(state='normal')
        self.entry_port.config(state='normal')
        self.label_freq.config(text="---")
        
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.freq_centrale = FREQUENCE_DEFAUT
        self.mettre_a_jour_axe_freq()
        
        self.ligne_spectre.set_data(self.axe_freq, self.spectre_actuel)
        self.image_waterfall.set_data(self.waterfall_data)
        self.canvas.draw()
    
    def creer_controles_lecture(self):
        """Crée les contrôles pour naviguer dans le CSV."""
        if hasattr(self, 'frame_lecture'):
            self.frame_lecture.destroy()
        
        self.frame_lecture = tk.Frame(self.root, bg='#1a1a2e')
        self.frame_lecture.pack(fill='x', padx=10, pady=5, before=self.frame_principal)
        
        tk.Label(
            self.frame_lecture,
            text="📼 Lecture CSV:",
            font=("Helvetica", 11, "bold"),
            fg='#00ccff',
            bg='#1a1a2e'
        ).pack(side='left', padx=10)
        
        self.btn_debut = tk.Button(
            self.frame_lecture, text="⏮", font=("Helvetica", 12),
            width=3, command=lambda: self.aller_a_position(0)
        )
        self.btn_debut.pack(side='left', padx=2)
        
        self.btn_reculer = tk.Button(
            self.frame_lecture, text="◀", font=("Helvetica", 12),
            width=3, command=lambda: self.aller_a_position(max(0, self.index_lecture - 10))
        )
        self.btn_reculer.pack(side='left', padx=2)
        
        self.btn_play = tk.Button(
            self.frame_lecture, text="▶ Play", font=("Helvetica", 11, "bold"),
            width=8, command=self.toggle_lecture
        )
        self.btn_play.pack(side='left', padx=5)
        
        self.btn_avancer = tk.Button(
            self.frame_lecture, text="▶", font=("Helvetica", 12),
            width=3, command=lambda: self.aller_a_position(min(len(self.donnees_csv)-1, self.index_lecture + 10))
        )
        self.btn_avancer.pack(side='left', padx=2)
        
        self.btn_fin = tk.Button(
            self.frame_lecture, text="⏭", font=("Helvetica", 12),
            width=3, command=lambda: self.aller_a_position(len(self.donnees_csv) - 1)
        )
        self.btn_fin.pack(side='left', padx=2)
        
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
        
        self.label_position = tk.Label(
            self.frame_lecture,
            text="0 / 0",
            font=("Helvetica", 10),
            fg='#aaaaaa',
            bg='#1a1a2e',
            width=20
        )
        self.label_position.pack(side='left', padx=10)
        
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
        self.slider_position.set(index)
    
    def charger_donnees_csv(self):
        """Charge et affiche les données à la position actuelle."""
        if not self.donnees_csv:
            return
        
        data = self.donnees_csv[self.index_lecture]
        
        if data['freq'] != self.freq_centrale:
            self.freq_centrale = data['freq']
            demi_span = data['span'] / 2000
            freq_min = self.freq_centrale - demi_span
            freq_max = self.freq_centrale + demi_span
            self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
            
            self.ax_spectre.set_xlim(freq_min, freq_max)
            self.ax_spectre.set_title(f"Spectre IC-705 - {self.freq_centrale:.3f} MHz (CSV)", color='white')
            self.image_waterfall.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
            self.ligne_centre.set_xdata([self.freq_centrale, self.freq_centrale])
        
        self.spectre_actuel = data['spectre']
        
        start_idx = max(0, self.index_lecture - PROFONDEUR_WATERFALL + 1)
        waterfall_lines = []
        for i in range(start_idx, self.index_lecture + 1):
            waterfall_lines.append(self.donnees_csv[i]['spectre'])
        
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        for i, line in enumerate(reversed(waterfall_lines)):
            if i < PROFONDEUR_WATERFALL:
                self.waterfall_data[i] = line
        
        self.ligne_spectre.set_data(self.axe_freq, self.spectre_actuel)
        self.image_waterfall.set_data(self.waterfall_data)
        self.canvas.draw()
        
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
        self.btn_play.config(text="⏸ Pause")
        self.lecture_auto()
    
    def arreter_lecture(self):
        """Arrête la lecture automatique."""
        self.lecture_en_cours = False
        self.btn_play.config(text="▶ Play")
    
    def lecture_auto(self):
        """Boucle de lecture automatique."""
        if not self.lecture_en_cours or not self.mode_lecture_csv:
            return
        
        if self.index_lecture < len(self.donnees_csv) - 1:
            self.index_lecture += 1
            self.charger_donnees_csv()
            self.slider_position.set(self.index_lecture)
            
            vitesse = self.slider_vitesse.get()
            delai = max(4, 200 // vitesse)
            
            self.root.after(delai, self.lecture_auto)
        else:
            self.arreter_lecture()
    
    def quitter(self):
        """Ferme l'application proprement."""
        if self.mode_lecture_csv:
            self.fermer_csv_lecture()
        self.arreter_affichage()
        self.deconnecter()
        plt.close('all')
        self.root.quit()
        self.root.destroy()


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == '__main__':
    root = tk.Tk()
    app = IC705AppV4(root)
    root.mainloop()
