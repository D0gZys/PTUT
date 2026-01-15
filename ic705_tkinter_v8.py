#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC-705 Spectrum Display - Version 8
===================================
Version optimisée avec calibration dBm automatique.

Fonctionnalités:
- Affichage du spectre et waterfall en dBm calibré
- Lecture automatique du niveau de référence du IC-705
- Maximum de trames affichées (buffer optimisé)
- Sauvegarde CSV avec timestamp
- Mode Trigger pour l'enregistrement
- Curseurs min/max ajustables
"""

import tkinter as tk
from tkinter import messagebox, filedialog
from collections import deque
import socket
import threading
import time
import numpy as np
import csv
import os
from datetime import datetime 

# Backend matplotlib
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

# Paramètres spectre
FREQUENCE_DEFAUT = 7.100
SPAN_KHZ = 5            # Span 2.5 kHz pour détection météores (haute résolution)
LARGEUR_SPECTRE = 475  # Points du spectre (optimisé pour les données IC-705)
PROFONDEUR_WATERFALL = 100

# Calibration dBm - basée sur mesures réelles IC-705
# Mesures: -110dBm=93, -90dBm=133, -80dBm=153, -77dBm=160 (max)
# Plancher bruit antenne: raw~0-6 = -157 à -160 dBm
REF_LEVEL_DEFAULT = -77    # Niveau de référence mesuré (dBm) = raw max 160
RAW_MAX = 160              # Valeur brute maximale mesurée
DYNAMIC_RANGE = 80         # Plage dynamique (dB)
SCALE_DB_PER_POINT = DYNAMIC_RANGE / RAW_MAX  # = 0.5 dB par point
DBM_MIN_DEFAULT = -160     # Min affichage (dBm) - plancher bruit
DBM_MAX_DEFAULT = -80      # Max affichage (dBm) - pour voir les échos météores

# Trigger
TRIGGER_PRE_LINES = 200    # Lignes enregistrées AVANT le déclenchement
TRIGGER_POST_LINES = 200   # Lignes enregistrées APRÈS le déclenchement

# CSV
DOSSIER_CSV = "recep_csv"

# Waterfall colormap
WF_CMAP = "inferno"

# Protocole CI-V
CIV_PREAMBLE = bytes([0xFE, 0xFE])
CIV_END = bytes([0xFD])


def build_civ_frame(cmd, sub_cmd=None, payload=b""):
    """Construit une trame CI-V."""
    frame = CIV_PREAMBLE + bytes([ADRESSE_RADIO, ADRESSE_PC, cmd])
    if sub_cmd is not None:
        frame += bytes([sub_cmd])
    frame += payload + CIV_END
    return frame


# Commandes CI-V
CMD_STREAM_ON = build_civ_frame(0x27, 0x10, bytes([0x01]))   # Activer scope
CMD_STREAM_OFF = build_civ_frame(0x27, 0x10, bytes([0x00]))  # Désactiver scope
CMD_FREQ_REQUEST = build_civ_frame(0x03)                      # Demander fréquence
CMD_REF_LEVEL_READ = build_civ_frame(0x27, 0x19)             # Lire niveau référence


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
# ============================================================

def decoder_frequence_bcd(data):
    """Décode une fréquence BCD (5 octets) vers MHz."""
    if len(data) < 5:
        return FREQUENCE_DEFAUT
    
    factors = (1, 100, 10000, 1000000, 100000000)
    freq_hz = 0
    for factor, byte in zip(factors, data[:5]):
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        freq_hz += low * factor + high * factor * 10
    
    return freq_hz / 1_000_000


def trouver_messages_civ(buffer):
    """Extrait les messages CI-V complets d'un buffer."""
    messages = []
    
    while True:
        debut = buffer.find(CIV_PREAMBLE)
        if debut == -1:
            buffer.clear()
            break
        
        if debut > 0:
            del buffer[:debut]
        
        fin = buffer.find(CIV_END)
        if fin == -1:
            break
        
        message = bytes(buffer[:fin + 1])
        messages.append(message)
        del buffer[:fin + 1]
    
    return messages


def extraire_spectre(msg):
    """Extrait les données spectre d'une trame 0x27."""
    if len(msg) < 20:
        return None
    
    # Données spectre à partir de l'octet 19
    idx_start = 19
    idx_end = len(msg) - 1
    
    if idx_start >= idx_end:
        return None
    
    return np.frombuffer(msg, dtype=np.uint8, offset=idx_start, count=idx_end - idx_start).astype(np.float32)


def decoder_ref_level(msg):
    """Décode le niveau de référence d'une réponse 0x27 0x19."""
    # Format: FE FE E0 A4 27 19 XX XX FD
    # XX XX = niveau en BCD (ex: 00 10 = +10 dBm, 01 10 = -10 dBm)
    if len(msg) < 9:
        return None
    
    if msg[4] != 0x27 or msg[5] != 0x19:
        return None
    
    # Décodage BCD signé
    low = msg[6]
    high = msg[7] if len(msg) > 7 else 0
    
    value = (low & 0x0F) + ((low >> 4) & 0x0F) * 10
    if high & 0x01:  # Signe négatif
        value = -value
    
    return value


def brut_vers_dbm(valeur_brute, ref_level=REF_LEVEL_DEFAULT, raw_max=RAW_MAX):
    """
    Convertit une valeur brute 0-160 en dBm.
    
    Calibration basée sur mesures réelles IC-705:
    - raw=160 → REF_LEVEL (-77 dBm)
    - raw=153 → -80 dBm
    - raw=133 → -90 dBm  
    - raw=93  → -110 dBm
    
    Formule: dBm = REF_LEVEL - (RAW_MAX - raw) * 0.5
    """
    return ref_level - (raw_max - valeur_brute) * SCALE_DB_PER_POINT


def redimensionner_spectre(donnees, largeur_cible):
    """Redimensionne le spectre à la largeur cible."""
    if donnees is None or len(donnees) == 0:
        return np.full(largeur_cible, -100.0)
    
    n = len(donnees)
    if n == largeur_cible:
        return donnees
    elif n > largeur_cible:
        indices = np.linspace(0, n - 1, largeur_cible, dtype=np.int32)
        return donnees[indices]
    else:
        x_old = np.linspace(0, 1, n)
        x_new = np.linspace(0, 1, largeur_cible)
        return np.interp(x_new, x_old, donnees)


# ============================================================
#              CLASSE PRINCIPALE
# ============================================================

class IC705SpectrumV8:
    """Application spectre IC-705 optimisée."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("IC-705 Spectrum v8 - dBm calibré")
        self.root.geometry("1200x700")
        self.root.configure(bg='#1a1a2e')
        self.root.minsize(1000, 600)
        
        # État connexion
        self.connexion = None
        self.connecte = False
        self.actif = False
        self.thread_rx = None
        
        # Données
        self.freq_centrale = FREQUENCE_DEFAUT
        self.ref_level = REF_LEVEL_DEFAULT
        self.spectre = np.full(LARGEUR_SPECTRE, -100.0)
        self.waterfall = np.full((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE), -100.0)
        self.waterfall_times = [""] * PROFONDEUR_WATERFALL
        
        # Thread-safe
        self.lock = threading.Lock()
        self.nouvelles_donnees = False
        self.nouvelle_freq = None
        self.nouveau_ref = None
        
        # Affichage
        self.dbm_min = DBM_MIN_DEFAULT
        self.dbm_max = DBM_MAX_DEFAULT
        
        # Statistiques
        self.stat_min = None
        self.stat_max = None
        self.stat_count = 0
        self.stat_sum = 0.0
        self.frames_count = 0
        self.last_fps_time = time.time()
        self.fps = 0
        
        # Enregistrement CSV
        self.enregistrement = False
        self.fichier_csv = None
        self.writer_csv = None
        self.nom_csv = None
        self.lignes_csv = 0
        
        # Trigger
        self.trigger_actif = tk.BooleanVar(value=False)
        self.trigger_flag = False
        self.seuil_trigger = -130  # dBm (juste au-dessus du plancher bruit -160)
        self.au_dessus = False
        self.nb_triggers = 0
        self.trigger_max_dbm = -999  # Puissance max mesurée pendant ce trigger
        self.pre_buffer = deque(maxlen=TRIGGER_PRE_LINES)
        self.post_restantes = 0
        
        # Interface
        self.creer_interface()
        self.creer_graphique()
        
        # Fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)
    
    # ========================
    # Interface
    # ========================
    
    def creer_interface(self):
        """Crée l'interface utilisateur épurée."""
        
        # === Barre supérieure ===
        top = tk.Frame(self.root, bg='#1a1a2e')
        top.pack(fill='x', padx=10, pady=5)
        
        # Titre
        tk.Label(top, text="📡 IC-705 Spectrum v8", font=("Helvetica", 16, "bold"),
                 fg='#00ff88', bg='#1a1a2e').pack(side='left', padx=10)
        
        # Connexion
        tk.Label(top, text="IP:", fg='white', bg='#1a1a2e').pack(side='left', padx=(20, 5))
        self.entry_ip = tk.Entry(top, width=12)
        self.entry_ip.insert(0, SERVEUR_IP)
        self.entry_ip.pack(side='left')
        
        tk.Label(top, text="Port:", fg='white', bg='#1a1a2e').pack(side='left', padx=(10, 5))
        self.entry_port = tk.Entry(top, width=6)
        self.entry_port.insert(0, str(SERVEUR_PORT))
        self.entry_port.pack(side='left')
        
        # Boutons
        self.btn_connect = tk.Button(top, text="🔌 Connecter", font=("Helvetica", 11, "bold"),
                                      width=12, command=self.toggle_connexion)
        self.btn_connect.pack(side='left', padx=15)
        
        self.btn_start = tk.Button(top, text="▶ Start", font=("Helvetica", 11, "bold"),
                                    width=10, state='disabled', command=self.toggle_affichage)
        self.btn_start.pack(side='left', padx=5)
        
        # Enregistrement
        self.btn_rec = tk.Button(top, text="⏺ REC", font=("Helvetica", 11, "bold"),
                                  width=8, state='disabled', command=self.toggle_enregistrement)
        self.btn_rec.pack(side='left', padx=5)
        
        # Trigger
        frame_trig = tk.Frame(top, bg='#1a1a2e')
        frame_trig.pack(side='left', padx=10)
        
        tk.Checkbutton(frame_trig, text="Trigger >", variable=self.trigger_actif,
                       bg='#1a1a2e', fg='white', selectcolor='#2a2a4e',
                       command=self.on_trigger_change).pack(side='left')
        
        self.entry_seuil = tk.Entry(frame_trig, width=6, justify='center')
        self.entry_seuil.insert(0, "-130")
        self.entry_seuil.pack(side='left', padx=2)
        tk.Label(frame_trig, text="dBm", fg='white', bg='#1a1a2e').pack(side='left')
        
        # Status à droite
        self.label_status = tk.Label(top, text="⚪ Non connecté", font=("Helvetica", 11, "bold"),
                                      fg='#ff6666', bg='#1a1a2e')
        self.label_status.pack(side='right', padx=10)
        
        self.label_freq = tk.Label(top, text="-- MHz", font=("Helvetica", 12, "bold"),
                                    fg='#ffcc00', bg='#1a1a2e')
        self.label_freq.pack(side='right', padx=10)
        
        self.label_ref = tk.Label(top, text="Ref: -- dBm", font=("Helvetica", 10),
                                   fg='#00ccff', bg='#1a1a2e')
        self.label_ref.pack(side='right', padx=10)
        
        # === Sliders et stats ===
        mid = tk.Frame(self.root, bg='#1a1a2e')
        mid.pack(fill='x', padx=10, pady=5)
        
        # Slider Min
        tk.Label(mid, text="Min (dBm):", fg='#4a90d9', bg='#1a1a2e',
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=5)
        self.slider_min = tk.Scale(mid, from_=-160, to=-60, orient='horizontal', length=150,
                                    bg='#2a2a4e', fg='white', troughcolor='#1a1a3e',
                                    highlightthickness=0, command=self.on_slider_change)
        self.slider_min.set(self.dbm_min)
        self.slider_min.pack(side='left', padx=5)
        
        # Slider Max
        tk.Label(mid, text="Max (dBm):", fg='#d94a4a', bg='#1a1a2e',
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=(20, 5))
        self.slider_max = tk.Scale(mid, from_=-160, to=-60, orient='horizontal', length=150,
                                    bg='#2a2a4e', fg='white', troughcolor='#1a1a3e',
                                    highlightthickness=0, command=self.on_slider_change)
        self.slider_max.set(self.dbm_max)
        self.slider_max.pack(side='left', padx=5)
        
        # Stats
        tk.Label(mid, text="│ Min:", fg='#4a90d9', bg='#1a1a2e').pack(side='left', padx=(30, 2))
        self.lbl_min = tk.Label(mid, text="--", fg='white', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_min.pack(side='left')
        
        tk.Label(mid, text="Max:", fg='#d94a4a', bg='#1a1a2e').pack(side='left', padx=(15, 2))
        self.lbl_max = tk.Label(mid, text="--", fg='white', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_max.pack(side='left')
        
        tk.Label(mid, text="Moy:", fg='#ffcc00', bg='#1a1a2e').pack(side='left', padx=(15, 2))
        self.lbl_moy = tk.Label(mid, text="--", fg='white', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_moy.pack(side='left')
        
        # FPS et frames
        self.lbl_fps = tk.Label(mid, text="0 fps", fg='#888888', bg='#1a1a2e', font=('Consolas', 9))
        self.lbl_fps.pack(side='right', padx=10)
        
        self.lbl_rec = tk.Label(mid, text="", fg='#ff4444', bg='#1a1a2e', font=('Helvetica', 9))
        self.lbl_rec.pack(side='right', padx=10)
        
        # Reset stats
        tk.Button(mid, text="🔄", command=self.reset_stats, bg='#3a3a5e', fg='white',
                  relief='flat', font=('Helvetica', 9)).pack(side='right', padx=5)
        
        # === Zone graphique ===
        self.frame_graph = tk.Frame(self.root, bg='#1a1a2e')
        self.frame_graph.pack(fill='both', expand=True, padx=10, pady=5)
    
    def creer_graphique(self):
        """Crée le graphique matplotlib."""
        
        # Axes fréquence
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Figure
        self.fig = plt.figure(figsize=(10, 5.5), facecolor='#1a1a2e')
        gs = self.fig.add_gridspec(2, 2, width_ratios=[30, 1], hspace=0.25, wspace=0.05)
        
        self.ax_spec = self.fig.add_subplot(gs[0, 0])
        self.ax_wf = self.fig.add_subplot(gs[1, 0])
        self.ax_cb = self.fig.add_subplot(gs[1, 1])
        
        # Style
        for ax in [self.ax_spec, self.ax_wf]:
            ax.set_facecolor('#0a0a1a')
        
        # Spectre
        self.ax_spec.set_title(f'Spectre - {self.freq_centrale:.3f} MHz', color='white')
        self.ax_spec.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_spec.set_ylabel('Niveau (dBm)', color='white')
        self.ax_spec.set_xlim(freq_min, freq_max)
        self.ax_spec.set_ylim(self.dbm_min, self.dbm_max)
        self.ax_spec.tick_params(colors='white')
        self.ax_spec.grid(True, alpha=0.3)
        
        # Ligne centre
        self.ligne_centre = self.ax_spec.axvline(x=self.freq_centrale, color='red',
                                                   linestyle='--', alpha=0.7)
        
        # Courbe spectre
        self.ligne_spec, = self.ax_spec.plot(self.axe_freq, self.spectre,
                                               color='#00ff88', linewidth=1)
        
        # Waterfall
        self.ax_wf.set_title('Waterfall', color='white')
        self.ax_wf.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_wf.set_ylabel('Temps', color='white')
        self.ax_wf.tick_params(colors='white')
        
        self.img_wf = self.ax_wf.imshow(
            self.waterfall, aspect='auto', cmap=WF_CMAP,
            vmin=self.dbm_min, vmax=self.dbm_max, origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        
        # Colorbar
        self.colorbar = self.fig.colorbar(self.img_wf, cax=self.ax_cb)
        self.colorbar.set_label('dBm', color='white')
        self.ax_cb.tick_params(colors='white')
        
        # Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_graph)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    
    # ========================
    # Callbacks UI
    # ========================
    
    def on_slider_change(self, val):
        """Callback changement sliders."""
        self.dbm_min = self.slider_min.get()
        self.dbm_max = self.slider_max.get()
        
        if self.dbm_min >= self.dbm_max:
            self.dbm_min = self.dbm_max - 10
            self.slider_min.set(self.dbm_min)
        
        self.ax_spec.set_ylim(self.dbm_min, self.dbm_max)
        self.img_wf.set_clim(vmin=self.dbm_min, vmax=self.dbm_max)
        self.canvas.draw_idle()
    
    def on_trigger_change(self):
        """Callback checkbox trigger."""
        self.trigger_flag = self.trigger_actif.get()
    
    def reset_stats(self):
        """Reset statistiques."""
        self.stat_min = None
        self.stat_max = None
        self.stat_count = 0
        self.stat_sum = 0.0
        self.lbl_min.config(text="--")
        self.lbl_max.config(text="--")
        self.lbl_moy.config(text="--")
    
    # ========================
    # Connexion
    # ========================
    
    def toggle_connexion(self):
        if not self.connecte:
            self.connecter()
        else:
            self.deconnecter()
    
    def connecter(self):
        ip = self.entry_ip.get()
        try:
            port = int(self.entry_port.get())
        except ValueError:
            messagebox.showerror("Erreur", "Port invalide")
            return
        
        try:
            self.connexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connexion.settimeout(3)
            self.connexion.connect((ip, port))
            
            # Activer le scope
            self.connexion.send(CMD_STREAM_ON)
            time.sleep(0.2)
            
            # Demander fréquence et niveau référence
            self.connexion.send(CMD_FREQ_REQUEST)
            self.connexion.send(CMD_REF_LEVEL_READ)
            time.sleep(0.2)
            
            # Lire réponses
            try:
                data = self.connexion.recv(2048)
                self.traiter_reponse_initiale(data)
            except:
                pass
            
            self.connecte = True
            self.label_status.config(text="🟢 Connecté", fg='#00ff88')
            self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            self.label_ref.config(text=f"Ref: {self.ref_level} dBm")
            self.btn_connect.config(text="🔌 Déconnecter")
            self.btn_start.config(state='normal')
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Connexion impossible:\n{e}")
            if self.connexion:
                self.connexion.close()
                self.connexion = None
    
    def traiter_reponse_initiale(self, data):
        """Traite les réponses initiales."""
        buffer = bytearray(data)
        messages = trouver_messages_civ(buffer)
        
        for msg in messages:
            if len(msg) < 5:
                continue
            
            cmd = msg[4]
            
            # Fréquence
            if cmd == 0x03 and len(msg) >= 11:
                freq = decoder_frequence_bcd(msg[5:10])
                if freq > 0:
                    self.freq_centrale = freq
                    self.maj_axe_freq()
            
            # Niveau référence (CI-V) - pour info seulement
            # On garde notre calibration fixe basée sur les mesures réelles
            if cmd == 0x27 and len(msg) >= 8 and msg[5] == 0x19:
                ref = decoder_ref_level(msg)
                if ref is not None:
                    print(f"[INFO] IC-705 REF_LEVEL reçu via CI-V: {ref} dBm (ignoré, on utilise calibration fixe)")
                    # self.ref_level = ref  # Désactivé - on garde la calibration mesurée
    
    def deconnecter(self):
        if self.actif:
            self.arreter()
        
        if self.connexion:
            try:
                self.connexion.send(CMD_STREAM_OFF)
                time.sleep(0.1)
                self.connexion.close()
            except:
                pass
            self.connexion = None
        
        self.connecte = False
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.btn_connect.config(text="🔌 Connecter")
        self.btn_start.config(state='disabled')
    
    # ========================
    # Affichage
    # ========================
    
    def toggle_affichage(self):
        if not self.actif:
            self.demarrer()
        else:
            self.arreter()
    
    def demarrer(self):
        self.actif = True
        self.btn_start.config(text="⏹ Stop")
        self.btn_rec.config(state='normal')
        self.reset_stats()
        self.frames_count = 0
        self.last_fps_time = time.time()
        
        # Thread réception
        self.thread_rx = threading.Thread(target=self.boucle_reception, daemon=True)
        self.thread_rx.start()
        
        # Boucle affichage
        self.boucle_affichage()
    
    def arreter(self):
        self.actif = False
        self.btn_start.config(text="▶ Start")
        self.btn_rec.config(state='disabled')
        
        if self.enregistrement:
            self.arreter_enregistrement()
    
    def boucle_reception(self):
        """Thread de réception des données."""
        buffer = bytearray()
        self.connexion.settimeout(0.05)
        compteur_freq = 0
        
        while self.actif and self.connecte:
            try:
                data = self.connexion.recv(4096)
                buffer.extend(data)
            except socket.timeout:
                compteur_freq += 1
                if compteur_freq >= 40:  # Toutes les 2 secondes
                    compteur_freq = 0
                    try:
                        self.connexion.send(CMD_FREQ_REQUEST)
                        self.connexion.send(CMD_REF_LEVEL_READ)
                    except:
                        pass
                continue
            except:
                break
            
            messages = trouver_messages_civ(buffer)
            
            for msg in messages:
                if len(msg) < 5:
                    continue
                
                cmd = msg[4]
                
                # Fréquence
                if cmd == 0x03 and len(msg) >= 11:
                    freq = decoder_frequence_bcd(msg[5:10])
                    if freq > 0:
                        self.nouvelle_freq = freq
                
                # Niveau référence
                if cmd == 0x27 and len(msg) >= 8:
                    if msg[5] == 0x19:
                        ref = decoder_ref_level(msg)
                        if ref is not None:
                            self.nouveau_ref = ref
                    
                    # Données spectre (sous-commande différente ou pas de sous-commande pour données)
                    elif len(msg) > 50:
                        amplitudes = extraire_spectre(msg)
                        if amplitudes is not None and len(amplitudes) > 10:
                            # DEBUG CALIBRATION: Afficher les valeurs brutes et converties
                            # SANS AUCUNE LIMITE - valeurs brutes directes du IC-705
                            raw_min = float(np.min(amplitudes))
                            raw_max = float(np.max(amplitudes))
                            raw_moy = float(np.mean(amplitudes))
                            
                            # Trouver la position et valeur du pic (signal injecté)
                            idx_pic = int(np.argmax(amplitudes))
                            raw_pic = float(amplitudes[idx_pic])
                            
                            # Calcul du bruit de fond (moyenne sans le pic)
                            mask = np.ones(len(amplitudes), dtype=bool)
                            # Exclure 10 points autour du pic
                            start = max(0, idx_pic - 5)
                            end = min(len(amplitudes), idx_pic + 5)
                            mask[start:end] = False
                            if np.sum(mask) > 0:
                                raw_floor = float(np.mean(amplitudes[mask]))
                            else:
                                raw_floor = raw_moy
                            
                            # Convertir en dBm SANS LIMITE
                            spectre_dbm = brut_vers_dbm(amplitudes, self.ref_level)
                            
                            dbm_min = float(np.min(spectre_dbm))
                            dbm_max = float(np.max(spectre_dbm))
                            dbm_pic = float(brut_vers_dbm(raw_pic, self.ref_level))
                            dbm_floor = float(brut_vers_dbm(raw_floor, self.ref_level))
                            
                            # Afficher aussi les 5 valeurs max brutes pour voir si ça dépasse 160
                            top5_idx = np.argsort(amplitudes)[-5:][::-1]
                            top5_vals = [int(amplitudes[i]) for i in top5_idx]
                            
                            print(f"[CALIB] PIC: brut={raw_pic:.0f} -> {dbm_pic:.1f} dBm (pos={idx_pic}) | "
                                  f"FLOOR: brut={raw_floor:.1f} -> {dbm_floor:.1f} dBm | "
                                  f"Ref={self.ref_level} dBm | "
                                  f"Range: [{raw_min:.0f}-{raw_max:.0f}] | "
                                  f"Top5: {top5_vals}")
                            
                            spectre_resize = redimensionner_spectre(spectre_dbm, LARGEUR_SPECTRE)
                            
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                            
                            with self.lock:
                                self.spectre = spectre_resize.copy()
                                self.waterfall[1:] = self.waterfall[:-1]
                                self.waterfall[0] = spectre_resize.copy()
                                self.waterfall_times[1:] = self.waterfall_times[:-1]
                                self.waterfall_times[0] = timestamp
                                self.nouvelles_donnees = True
                                self.frames_count += 1
                            
                            # Enregistrement
                            if self.enregistrement:
                                self.enregistrer_ligne(spectre_resize, timestamp)
            
            # Éviter accumulation buffer
            if len(buffer) > 8000:
                buffer.clear()
    
    def boucle_affichage(self):
        """Boucle de mise à jour de l'affichage."""
        if not self.actif:
            return
        
        # Mise à jour fréquence
        if self.nouvelle_freq is not None:
            if abs(self.nouvelle_freq - self.freq_centrale) > 0.0001:
                self.freq_centrale = self.nouvelle_freq
                self.maj_axe_freq()
                self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            self.nouvelle_freq = None
        
        # Mise à jour niveau référence
        if self.nouveau_ref is not None:
            if self.nouveau_ref != self.ref_level:
                self.ref_level = self.nouveau_ref
                self.label_ref.config(text=f"Ref: {self.ref_level} dBm")
            self.nouveau_ref = None
        
        # Mise à jour graphique
        with self.lock:
            if self.nouvelles_donnees:
                spectre = self.spectre.copy()
                waterfall = self.waterfall.copy()
                self.nouvelles_donnees = False
            else:
                spectre = None
                waterfall = None
        
        if spectre is not None:
            self.ligne_spec.set_ydata(spectre)
            self.img_wf.set_data(waterfall)
            self.canvas.draw_idle()
            
            # Stats
            self.maj_stats(spectre)
        
        # FPS
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps = self.frames_count
            self.frames_count = 0
            self.last_fps_time = now
            self.lbl_fps.config(text=f"{self.fps} fps")
        
        # Prochaine mise à jour (25ms = 40 fps max UI)
        self.root.after(25, self.boucle_affichage)
    
    def maj_axe_freq(self):
        """Met à jour l'axe des fréquences."""
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        self.ligne_spec.set_xdata(self.axe_freq)
        self.ligne_centre.set_xdata([self.freq_centrale, self.freq_centrale])
        self.ax_spec.set_xlim(freq_min, freq_max)
        self.ax_spec.set_title(f'Spectre - {self.freq_centrale:.3f} MHz', color='white')
        
        self.img_wf.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
        self.ax_wf.set_xlim(freq_min, freq_max)
        
        self.canvas.draw_idle()
    
    def maj_stats(self, spectre):
        """Met à jour les statistiques."""
        if spectre is None or len(spectre) == 0:
            return
        
        s_min = np.min(spectre)
        s_max = np.max(spectre)
        s_sum = np.sum(spectre)
        s_count = len(spectre)
        
        if self.stat_min is None:
            self.stat_min = s_min
        else:
            self.stat_min = min(self.stat_min, s_min)
        
        if self.stat_max is None:
            self.stat_max = s_max
        else:
            self.stat_max = max(self.stat_max, s_max)
        
        self.stat_sum += s_sum
        self.stat_count += s_count
        
        moy = self.stat_sum / self.stat_count if self.stat_count > 0 else 0
        
        self.lbl_min.config(text=f"{self.stat_min:.0f}")
        self.lbl_max.config(text=f"{self.stat_max:.0f}")
        self.lbl_moy.config(text=f"{moy:.0f}")
    
    # ========================
    # Enregistrement CSV
    # ========================
    
    def toggle_enregistrement(self):
        if not self.enregistrement:
            self.demarrer_enregistrement()
        else:
            self.arreter_enregistrement()
    
    def demarrer_enregistrement(self):
        # Valider seuil trigger
        if self.trigger_flag:
            try:
                self.seuil_trigger = float(self.entry_seuil.get())
            except ValueError:
                messagebox.showerror("Erreur", "Seuil invalide")
                return
            self.au_dessus = False
            self.nb_triggers = 0
            self.pre_buffer.clear()
            self.post_restantes = 0
            self.lbl_rec.config(text=f"TRIGGER: attente > {self.seuil_trigger} dBm")
        else:
            self.creer_csv()
        
        self.enregistrement = True
        self.btn_rec.config(text="⏹ STOP", bg='#ff4444')
    
    def arreter_enregistrement(self):
        self.enregistrement = False
        self.fermer_csv()
        self.btn_rec.config(text="⏺ REC", bg='SystemButtonFace')
        self.lbl_rec.config(text="")
    
    def get_dossier_jour(self):
        """Retourne le chemin du dossier du jour, le crée si nécessaire."""
        date_jour = datetime.now().strftime('%Y%m%d')
        dossier = os.path.join(DOSSIER_CSV, date_jour)
        if not os.path.exists(dossier):
            os.makedirs(dossier)
            print(f"[CSV] Dossier créé: {dossier}")
        return dossier
    
    def creer_csv(self):
        dossier = self.get_dossier_jour()
        
        ts = datetime.now().strftime('%H%M%S')
        
        if self.trigger_flag:
            # Nom temporaire pour trigger - sera renommé à la fermeture avec la puissance max
            self.trigger_max_dbm = -999  # Reset du max
            self.nom_csv = os.path.join(dossier, f"trigger_{int(self.seuil_trigger)}dBm_{ts}_TEMP.csv")
        else:
            self.nom_csv = os.path.join(dossier, f"spectre_{ts}.csv")
        
        self.fichier_csv = open(self.nom_csv, 'w', newline='')
        self.writer_csv = csv.writer(self.fichier_csv)
        
        # Header
        header = ['timestamp', 'freq_mhz', 'span_khz', 'ref_level_dbm']
        header.extend([f'dbm_{i}' for i in range(LARGEUR_SPECTRE)])
        self.writer_csv.writerow(header)
        self.lignes_csv = 0
        print(f"[CSV] Fichier créé: {self.nom_csv}")
    
    def fermer_csv(self):
        if self.fichier_csv:
            try:
                self.fichier_csv.close()
            except:
                pass
            
            # Renommer le fichier trigger avec la puissance max mesurée
            if self.trigger_flag and self.nom_csv and '_TEMP.csv' in self.nom_csv:
                try:
                    nouveau_nom = self.nom_csv.replace('_TEMP.csv', f'_max{int(self.trigger_max_dbm)}dBm.csv')
                    os.rename(self.nom_csv, nouveau_nom)
                    print(f"[CSV] Trigger renommé: {os.path.basename(nouveau_nom)}")
                    self.nom_csv = nouveau_nom
                except Exception as e:
                    print(f"[CSV] Erreur renommage: {e}")
            
            self.fichier_csv = None
            self.writer_csv = None
    
    def enregistrer_ligne(self, spectre, timestamp):
        """Enregistre une ligne avec gestion du trigger."""
        max_signal = np.max(spectre)
        
        if self.trigger_flag:
            if max_signal >= self.seuil_trigger:
                if not self.au_dessus:
                    self.au_dessus = True
                    if not self.writer_csv:
                        self.nb_triggers += 1
                        self.creer_csv()
                        # Flush pre-buffer
                        for ts, freq, ref, spec in self.pre_buffer:
                            self.ecrire_csv(spec, ts, freq, ref)
                            # Mettre à jour le max avec les données du pre-buffer
                            buf_max = np.max(spec)
                            if buf_max > self.trigger_max_dbm:
                                self.trigger_max_dbm = buf_max
                        self.pre_buffer.clear()
                
                self.post_restantes = TRIGGER_POST_LINES
                
                # Mettre à jour le max du trigger
                if max_signal > self.trigger_max_dbm:
                    self.trigger_max_dbm = max_signal
                
                if self.writer_csv:
                    self.ecrire_csv(spectre, timestamp, self.freq_centrale, self.ref_level)
                    self.lbl_rec.config(text=f"⏺ TRIGGER #{self.nb_triggers}: {self.lignes_csv} lignes | Max: {self.trigger_max_dbm:.1f} dBm")
            else:
                if self.au_dessus:
                    self.au_dessus = False
                
                if self.writer_csv:
                    if self.post_restantes > 0:
                        self.ecrire_csv(spectre, timestamp, self.freq_centrale, self.ref_level)
                        self.post_restantes -= 1
                        if self.post_restantes <= 0:
                            self.fermer_csv()
                            self.lbl_rec.config(text=f"TRIGGER: attente > {self.seuil_trigger} dBm")
                    else:
                        self.fermer_csv()
                        self.lbl_rec.config(text=f"TRIGGER: attente > {self.seuil_trigger} dBm")
                
                if not self.writer_csv:
                    self.pre_buffer.append((timestamp, self.freq_centrale, self.ref_level, spectre.copy()))
        else:
            if self.writer_csv:
                self.ecrire_csv(spectre, timestamp, self.freq_centrale, self.ref_level)
                if self.lignes_csv % 50 == 0:
                    self.lbl_rec.config(text=f"⏺ REC: {self.lignes_csv} lignes")
    
    def ecrire_csv(self, spectre, timestamp, freq, ref_level):
        """Écrit une ligne dans le CSV."""
        if not self.writer_csv:
            return
        
        try:
            ligne = [timestamp, f"{freq:.6f}", SPAN_KHZ, ref_level]
            ligne.extend([f"{v:.1f}" for v in spectre])
            self.writer_csv.writerow(ligne)
            self.lignes_csv += 1
            
            if self.lignes_csv % 100 == 0:
                self.fichier_csv.flush()
        except Exception as e:
            print(f"Erreur CSV: {e}")
    
    # ========================
    # Fermeture
    # ========================
    
    def quitter(self):
        self.actif = False
        if self.enregistrement:
            self.arreter_enregistrement()
        if self.connecte:
            self.deconnecter()
        self.root.quit()
        self.root.destroy()


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = IC705SpectrumV8(root)
    root.mainloop()
