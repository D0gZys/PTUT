#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC-705 Spectrum Display avec Tkinter - Version 7
================================================
Version avec affichage dBm natif (données brutes du IC-705).

Fonctionnalités:
- Affichage du spectre et waterfall en temps réel en dBm
- Les données brutes du IC-705 sont interprétées comme des niveaux dBm
 - Panneau de log des trames CI-V en hexadécimal (optionnel)
- Sliders de niveau min/max en dBm
- Enregistrement CSV
- Mode Trigger pour l'enregistrement
- Lecture de fichiers CSV
"""

import tkinter as tk
from tkinter import messagebox, ttk, filedialog, simpledialog
import tkinter.font as tkfont
from collections import deque
import socket
import threading
import time
import numpy as np
import csv
import os
from datetime import datetime
from functools import lru_cache

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
# Plage dBm par défaut pour l'affichage (données brutes IC-705)
DBM_MIN = 0
DBM_MAX = 120
WF_CMAP = "inferno"  # Colormap pour le waterfall
BUFFER_DELAY_SEC = 5.0
BUFFER_MAX_SEC = 30.0
UI_SCALE = 1.25
FONT_SCALE = 1.35
WINDOW_START_RATIO = 0.9
ENABLE_LOG_PANEL = False
MAX_TRAMES_QUEUE = 100
CIV_PREAMBLE = bytes([0xFE, 0xFE])
CIV_END = bytes([0xFD])
BCD_FACTORS = (1, 100, 10000, 1000000, 100000000)


def build_civ_frame(cmd, payload=b""):
    """Construit une trame CI-V vers la radio."""
    return CIV_PREAMBLE + bytes([ADRESSE_RADIO, ADRESSE_PC, cmd]) + payload + CIV_END


CMD_STREAM_ON = build_civ_frame(0x1A, bytes([0x05, 0x00, 0x01]))
CMD_STREAM_OFF = build_civ_frame(0x1A, bytes([0x05, 0x00, 0x00]))
CMD_FREQ_REQUEST = build_civ_frame(0x03)


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
# ============================================================

def decoder_frequence_bcd(data):
    """Décode une fréquence en BCD (5 octets) vers MHz."""
    if len(data) < 5:
        return FREQUENCE_DEFAUT
    
    freq_hz = 0
    for factor, byte in zip(BCD_FACTORS, data[:5]):
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        freq_hz += low * factor + high * factor * 10
    
    return freq_hz / 1_000_000


def trouver_messages_civ(buffer):
    """Extrait tous les messages CI-V complets d'un buffer."""
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


def extraire_donnees_spectre(msg):
    """
    Extrait les amplitudes d'une trame spectre (commande 0x27).
    
    Structure de la trame:
    [0-1]   FE FE       : Préambule
    [2]     E0          : Adresse destination (PC)
    [3]     A4          : Adresse source (IC-705)
    [4]     27          : Commande (spectre)
    [5-9]   5 octets    : Fréquence centrale BCD
    [10-11] 2 octets    : Information span/step
    [12]    1 octet     : Scope ON/OFF
    [13]    1 octet     : Division de trame (bits 7-4: nb divisions-1, bits 3-0: segment actuel)
    [14-18] 5 octets    : Autres métadonnées
    [19+]   Données     : Amplitudes spectrales (jusqu'à FD-1)
    [-1]    FD          : Terminateur
    
    Retourne: tuple (segment_num, nb_segments, amplitudes) ou None
    """
    if len(msg) < 20:
        return None
    
    # Extraire les informations de segmentation (octet 13)
    division_byte = msg[13]
    nb_segments = ((division_byte >> 4) & 0x0F) + 1
    segment_num = (division_byte & 0x0F)  # 0-indexé
    
    idx_start = 19
    idx_end = len(msg) - 1
    
    if idx_start >= idx_end:
        return None
    
    amplitudes = np.frombuffer(
        msg,
        dtype=np.uint8,
        offset=idx_start,
        count=idx_end - idx_start
    ).astype(np.float32)
    
    return (segment_num, nb_segments, amplitudes)


@lru_cache(maxsize=32)
def _resize_indices(taille_originale, largeur_cible):
    return np.linspace(0, taille_originale - 1, largeur_cible, dtype=np.int32)


@lru_cache(maxsize=32)
def _resize_interp_axes(taille_originale, largeur_cible):
    x_original = np.linspace(0.0, 1.0, taille_originale, dtype=np.float32)
    x_nouveau = np.linspace(0.0, 1.0, largeur_cible, dtype=np.float32)
    return x_original, x_nouveau


def redimensionner_spectre(donnees, largeur_cible):
    """Redimensionne un spectre à la largeur souhaitée."""
    if donnees is None or len(donnees) == 0:
        return np.zeros(largeur_cible)
    
    taille_originale = len(donnees)
    
    if taille_originale >= largeur_cible:
        indices = _resize_indices(taille_originale, largeur_cible)
        return donnees[indices]
    else:
        x_original, x_nouveau = _resize_interp_axes(taille_originale, largeur_cible)
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

class IC705AppV7:
    """Application principale avec interface Tkinter - Version 7."""
    
    def __init__(self, root):
        """Initialise l'application."""
        self.root = root
        self.root.title("IC-705 Spectrum Display v7 - dBm")
        self.root.geometry("1400x800")
        self.root.configure(bg='#1a1a2e')
        self.root.minsize(1200, 600)
        self.ajuster_taille_fenetre()
        self.appliquer_scaling_ui()
        
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
        self.waterfall_time_labels = [""] * PROFONDEUR_WATERFALL
        self.waterfall_zoom_lignes = PROFONDEUR_WATERFALL
        self.nouvelles_donnees = False
        self.lock_donnees = threading.Lock()
        self.derniere_ligne_rejouee = None
        self.slider_update_en_cours = False
        self.derniere_maj_temps = 0.0
        self.interval_maj_temps = 0.2
        self.waterfall_extent = None
        self.use_blit_avant_csv = None
        
        # Gestion des segments spectre (l'IC-705 envoie le spectre en plusieurs segments)
        self.segments_spectre = []
        self.nb_segments_attendus = 0
        self.segments_recus_count = 0
        
        # Paramètres de niveau dBm (données brutes IC-705)
        self.dbm_min = DBM_MIN
        self.dbm_max = DBM_MAX
        self.offset_calibration = 0  # Offset de calibration en dB
        
        # Statistiques cumulatives depuis le démarrage
        self.stat_global_min = None  # Min absolu depuis démarrage
        self.stat_global_max = None  # Max absolu depuis démarrage
        self.stat_somme = 0.0        # Somme pour calcul moyenne
        self.stat_count = 0          # Nombre d'échantillons
        
        # File des trames à afficher (thread-safe)
        self.trames_a_logger = []
        self.lock_trames = threading.Lock()
        self.compteur_trames_total = 0
        
        # Options de log
        self.log_spectre = tk.BooleanVar(value=False)
        self.log_autres = tk.BooleanVar(value=True)
        self.log_gains = tk.BooleanVar(value=False)
        self.log_actif = tk.BooleanVar(value=True)
        self.log_spectre_flag = False
        self.log_autres_flag = True
        self.log_gains_flag = False
        self.log_actif_flag = True
        if not ENABLE_LOG_PANEL:
            self.log_actif.set(False)
            self.log_actif_flag = False
            self.log_spectre_flag = False
            self.log_autres_flag = False
            self.log_gains_flag = False
        
        # Option de conversion log (désactivée par défaut car données déjà en dBm)
        self.conversion_log = tk.BooleanVar(value=False)
        self.conversion_log_flag = False
        
        # Enregistrement CSV
        self.enregistrement_actif = False
        self.fichier_csv = None
        self.writer_csv = None
        self.nom_fichier_csv = None
        self.nb_lignes_csv = 0
        self.rec_status_text = ""
        self.rec_status_last = None
        
        # Trigger pour enregistrement
        self.trigger_actif = tk.BooleanVar(value=False)
        self.trigger_actif_flag = False
        self.seuil_trigger = 70
        self.au_dessus_seuil = False
        self.nb_fichiers_trigger = 0
        
        # Mode lecture CSV
        self.mode_lecture_csv = False
        self.donnees_csv = None
        self.csv_filter_info = None
        self.index_lecture = 0
        self.lecture_en_cours = False
        self.csv_frame_count = 0
        self.csv_render_every = 2
        self.csv_stats_every = 4
        self.csv_ticks_every = 5
        self.csv_slider_every = 2

        self.font_cache = {}

        # Buffer binaire pour affichage decale
        self.use_buffer_bin = True
        self.buffer_delay_sec = BUFFER_DELAY_SEC
        self.buffer_max_sec = BUFFER_MAX_SEC
        self.buffer_bin = deque()
        self.lock_buffer = threading.Lock()
        self.buffer_dropped = 0
        
        # Annotations souris sur waterfall (mode CSV)
        self.annotation_survol = None
        self.annotation_clic = None
        self.clic_markers = []  # Liste pour stocker les marqueurs de clic
        
        # Créer l'interface
        self.creer_interface()
        self.appliquer_scale_police()
        self.creer_graphique()
        
        # Gestion de la fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)

    def appliquer_scaling_ui(self):
        """Applique un scaling global UI pour ecrans haute densite."""
        try:
            self.root.tk.call('tk', 'scaling', UI_SCALE)
        except tk.TclError:
            pass

    def ajuster_taille_fenetre(self):
        """Ajuste la taille initiale de la fenetre."""
        try:
            system = self.root.tk.call('tk', 'windowingsystem')
            if system == 'win32':
                self.root.state('zoomed')
            else:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                width = int(sw * WINDOW_START_RATIO)
                height = int(sh * WINDOW_START_RATIO)
                self.root.geometry(f"{width}x{height}")
        except tk.TclError:
            pass

    def _get_scaled_font(self, font_spec):
        """Retourne une police mise a l'echelle avec cache."""
        cached = self.font_cache.get(font_spec)
        if cached is not None:
            return cached
        try:
            font_obj = tkfont.Font(root=self.root, font=font_spec)
        except tk.TclError:
            return font_spec
        size = font_obj.cget('size')
        if size == 0:
            return font_obj
        if size > 0:
            new_size = max(1, int(round(size * FONT_SCALE)))
        else:
            new_size = -max(1, int(round(abs(size) * FONT_SCALE)))
        font_obj.configure(size=new_size)
        self.font_cache[font_spec] = font_obj
        return font_obj

    def _scale_widget(self, widget):
        """Applique le scaling de police a un widget."""
        try:
            font_spec = widget.cget('font')
        except tk.TclError:
            font_spec = None
        if font_spec:
            try:
                widget.configure(font=self._get_scaled_font(font_spec))
            except tk.TclError:
                pass
        if isinstance(widget, tk.Scale):
            try:
                length = int(float(widget.cget('length')))
                widget.configure(length=int(length * FONT_SCALE))
            except tk.TclError:
                pass

    def appliquer_scale_police(self, widget=None):
        """Applique le scaling des polices a tous les widgets."""
        if FONT_SCALE == 1.0:
            return
        if widget is None:
            widget = self.root
        self._scale_widget(widget)
        for child in widget.winfo_children():
            self.appliquer_scale_police(child)


    def creer_interface(self):
        """Crée les widgets de l'interface."""
        
        # === Frame du haut pour les contrôles ===
        frame_controles = tk.Frame(self.root, bg='#1a1a2e')
        frame_controles.pack(fill='x', padx=10, pady=10)
        
        # Titre
        titre = tk.Label(
            frame_controles,
            text="📡 IC-705 Spectrum Display v7 - dBm",
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
            selectcolor='#2a2a4e',
            command=self.on_toggle_trigger
        )
        self.cb_trigger.pack(side='left')
        
        self.entry_seuil = tk.Entry(frame_trigger, width=5, font=('Helvetica', 11),
                                     justify='center')
        self.entry_seuil.insert(0, "70")
        self.entry_seuil.pack(side='left', padx=2)
        self.label_trigger_unit = tk.Label(
            frame_trigger,
            text="(lin)",
            fg='white',
            bg='#1a1a2e',
            font=('Helvetica', 10)
        )
        self.label_trigger_unit.pack(side='left', padx=2)
        
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
        
        # === Frame pour les sliders de niveau dBm ===
        frame_sliders = tk.Frame(self.root, bg='#1a1a2e')
        frame_sliders.pack(fill='x', padx=10, pady=5)
        
        tk.Label(frame_sliders, text="dBm Min:", fg='#4a90d9', bg='#1a1a2e', 
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
        self.slider_min.set(self.dbm_min)
        self.slider_min.pack(side='left', padx=10)
        
        tk.Label(frame_sliders, text="dBm Max:", fg='#d94a4a', bg='#1a1a2e',
                 font=('Helvetica', 11, 'bold')).pack(side='left', padx=5)
        self.slider_max = tk.Scale(
            frame_sliders,
            from_=50, to=150,
            orient='horizontal',
            length=180,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 10),
            command=self.on_slider_change
        )
        self.slider_max.set(self.dbm_max)
        self.slider_max.pack(side='left', padx=10)
        
        self.label_gain = tk.Label(
            frame_sliders,
            text=f"Plage dBm: [{self.dbm_min} - {self.dbm_max}]",
            fg='#00ccff',
            bg='#1a1a2e',
            font=('Helvetica', 11, 'bold')
        )
        self.label_gain.pack(side='left', padx=20)

        # Checkbox pour conversion log supplémentaire (optionnelle)
        self.cb_conversion_log = tk.Checkbutton(
            frame_sliders,
            text="Conv. Log",
            variable=self.conversion_log,
            font=('Helvetica', 10, 'bold'),
            bg='#1a1a2e',
            fg='white',
            selectcolor='#2a2a4e',
            command=self.on_toggle_conversion_log
        )
        self.cb_conversion_log.pack(side='left', padx=10)
        
        # Slider de calibration (offset)
        tk.Label(frame_sliders, text="📏 Calibration:", fg='#ff9900', bg='#1a1a2e',
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=(15, 2))
        self.slider_calibration = tk.Scale(
            frame_sliders,
            from_=-50, to=50,
            orient='horizontal',
            length=120,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 9),
            command=self.on_calibration_change
        )
        self.slider_calibration.set(0)
        self.slider_calibration.pack(side='left', padx=2)
        
        self.label_calibration = tk.Label(
            frame_sliders,
            text="0 dB",
            fg='#ff9900',
            bg='#1a1a2e',
            font=('Consolas', 10, 'bold'),
            width=6
        )
        self.label_calibration.pack(side='left', padx=2)
        
        # === Frame pour les statistiques en temps réel ===
        frame_stats = tk.Frame(self.root, bg='#1a1a2e')
        frame_stats.pack(fill='x', padx=10, pady=2)
        
        tk.Label(frame_stats, text="📊 Signal détecté:", fg='#00ff88', bg='#1a1a2e', 
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=5)
        
        # Label pour Min
        tk.Label(frame_stats, text="Min:", fg='#4a90d9', bg='#1a1a2e', 
                 font=('Helvetica', 10)).pack(side='left', padx=(10, 2))
        self.label_stat_min = tk.Label(
            frame_stats,
            text="-- dBm (--)",
            fg='white',
            bg='#1a1a2e',
            font=('Consolas', 10)
        )
        self.label_stat_min.pack(side='left', padx=2)
        
        # Label pour Max
        tk.Label(frame_stats, text="Max:", fg='#d94a4a', bg='#1a1a2e', 
                 font=('Helvetica', 10)).pack(side='left', padx=(15, 2))
        self.label_stat_max = tk.Label(
            frame_stats,
            text="-- dBm (--)",
            fg='white',
            bg='#1a1a2e',
            font=('Consolas', 10)
        )
        self.label_stat_max.pack(side='left', padx=2)
        
        # Label pour Moyenne
        tk.Label(frame_stats, text="Moy:", fg='#ffcc00', bg='#1a1a2e', 
                 font=('Helvetica', 10)).pack(side='left', padx=(15, 2))
        self.label_stat_moy = tk.Label(
            frame_stats,
            text="-- dBm (--)",
            fg='white',
            bg='#1a1a2e',
            font=('Consolas', 10)
        )
        self.label_stat_moy.pack(side='left', padx=2)
        
        # Bouton Reset pour réinitialiser les statistiques
        self.btn_reset_stats = tk.Button(
            frame_stats,
            text="🔄 Reset",
            command=self.reset_statistiques,
            font=('Helvetica', 9),
            bg='#3a3a5e',
            fg='white',
            relief='flat'
        )
        self.btn_reset_stats.pack(side='left', padx=(20, 5))
        
        # === Frame principale contenant graphique + log ===
        self.frame_principal = tk.Frame(self.root, bg='#1a1a2e')
        self.frame_principal.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Frame gauche pour le graphique
        self.frame_graph = tk.Frame(self.frame_principal, bg='#1a1a2e')
        self.frame_graph.pack(side='left', fill='both', expand=True)
        
        # Frame droite pour le log des trames (optionnel)
        self.frame_log = None
        self.log_visible = False
        if ENABLE_LOG_PANEL:
            self.log_visible = True
            self.creer_panneau_log()
    
    def creer_panneau_log(self):
        """Crée le panneau de log des trames CI-V."""
        if not ENABLE_LOG_PANEL:
            return
        if self.frame_log is None:
            self.frame_log = tk.Frame(self.frame_principal, bg='#1a1a2e', width=400)
        self.frame_log.pack(side='right', fill='y', padx=(10, 0))
        self.frame_log.pack_propagate(False)
        
        # Titre du panneau
        titre_log = tk.Label(
            self.frame_log,
            text="📋 Trames CI-V Reçues",
            font=("Helvetica", 12, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre_log.pack(pady=(0, 5))
        
        # Options de filtrage
        frame_options = tk.Frame(self.frame_log, bg='#1a1a2e')
        frame_options.pack(fill='x', pady=5)
        
        cb_spectre = tk.Checkbutton(
            frame_options,
            text="Spectre (0x27)",
            variable=self.log_spectre,
            fg='#aaaaaa',
            bg='#1a1a2e',
            selectcolor='#2a2a4e',
            font=('Helvetica', 9),
            command=self.on_toggle_log_options
        )
        cb_spectre.pack(side='left', padx=5)
        
        cb_autres = tk.Checkbutton(
            frame_options,
            text="Autres",
            variable=self.log_autres,
            fg='#aaaaaa',
            bg='#1a1a2e',
            selectcolor='#2a2a4e',
            font=('Helvetica', 9),
            command=self.on_toggle_log_options
        )
        cb_autres.pack(side='left', padx=5)

        cb_gains = tk.Checkbutton(
            frame_options,
            text="Gain/Freq",
            variable=self.log_gains,
            fg='#aaaaaa',
            bg='#1a1a2e',
            selectcolor='#2a2a4e',
            font=('Helvetica', 9),
            command=self.on_toggle_log_options
        )
        cb_gains.pack(side='left', padx=5)
        
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
        frame_text = tk.Frame(self.frame_log, bg='#0a0a1a')
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
        scrollbar_h = tk.Scrollbar(self.frame_log, orient='horizontal')
        scrollbar_h.pack(fill='x')
        self.text_log.config(xscrollcommand=scrollbar_h.set)
        scrollbar_h.config(command=self.text_log.xview)
        
        # Compteur de trames
        self.label_compteur = tk.Label(
            self.frame_log,
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
            self.log_actif_flag = False
            self.btn_pause_log.config(text="▶")
        else:
            self.log_actif.set(True)
            self.log_actif_flag = True
            self.btn_pause_log.config(text="⏸")

    def on_toggle_log_options(self):
        """Met à jour les drapeaux de log (appelé depuis les checkboxes)."""
        try:
            self.log_spectre_flag = bool(self.log_spectre.get())
            self.log_autres_flag = bool(self.log_autres.get())
            self.log_gains_flag = bool(self.log_gains.get())
        except tk.TclError:
            self.log_spectre_flag = False
            self.log_autres_flag = False
            self.log_gains_flag = False

    def on_toggle_trigger(self):
        """Met à jour le drapeau trigger (thread-safe)."""
        try:
            self.trigger_actif_flag = bool(self.trigger_actif.get())
        except tk.TclError:
            self.trigger_actif_flag = False
    
    def clear_log(self):
        """Efface le log des trames."""
        if not ENABLE_LOG_PANEL or not hasattr(self, 'text_log'):
            return
        self.text_log.config(state='normal')
        self.text_log.delete('1.0', tk.END)
        self.text_log.config(state='disabled')
        self.compteur_trames_total = 0
        self.label_compteur.config(text="Total: 0 | Affichées: 0")
    
    def masquer_panneau_log(self):
        """Cache le panneau de log pour élargir le graphique (utilisé en lecture CSV)."""
        if self.frame_log and self.log_visible:
            self.frame_log.pack_forget()
            self.log_visible = False
            # S'assure que le graphe occupe tout l'espace disponible
            self.frame_graph.pack_configure(side='left', fill='both', expand=True)
    
    def afficher_panneau_log(self):
        """Réaffiche le panneau de log."""
        if self.frame_log and not self.log_visible:
            self.frame_log.pack(side='right', fill='y', padx=(10, 0))
            self.log_visible = True
    
    def ajouter_trames_batch(self, trames):
        """Ajoute plusieurs trames au log en une seule opération."""
        if not ENABLE_LOG_PANEL or not hasattr(self, 'text_log'):
            return
        if not trames or not self.log_actif_flag:
            return
        
        trames_filtrees = []
        for ts, type_t, hex_d in trames:
            if type_t == "SPECTRE" and not self.log_spectre_flag:
                continue
            if type_t in ("GAIN", "LEVEL") and not self.log_gains_flag:
                continue
            if type_t not in ("SPECTRE", "GAIN", "LEVEL") and not self.log_autres_flag:
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
            line = f"{ts} | [{type_t:8s}] {hex_d}\\n"
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
        self.dbm_min = self.slider_min.get()
        self.dbm_max = self.slider_max.get()
        
        if self.dbm_min >= self.dbm_max:
            self.dbm_min = self.dbm_max - 10
            self.slider_min.set(self.dbm_min)
        
        self.label_gain.config(text=f"Plage dBm: [{self.dbm_min} - {self.dbm_max}]")
        
        if hasattr(self, 'ax_spectre'):
            self.ax_spectre.set_ylim(self.dbm_min, self.dbm_max)
            self.image_waterfall.set_clim(vmin=self.dbm_min, vmax=self.dbm_max)
            
            # Mettre à jour les ticks de la colorbar pour refléter la nouvelle plage
            if hasattr(self, 'colorbar'):
                # La colorbar se met à jour automatiquement via set_clim
                # mais on force le rafraîchissement des graduations
                self.colorbar.update_normal(self.image_waterfall)
            
            self.canvas.draw()
            # Recréer le background après modification
            if hasattr(self, 'use_blit') and self.use_blit:
                self.background = self.canvas.copy_from_bbox(self.fig.bbox)
    
    def on_calibration_change(self, value):
        """Appelé quand le slider de calibration change."""
        self.offset_calibration = int(value)
        
        # Mise à jour du label
        sign = "+" if self.offset_calibration >= 0 else ""
        self.label_calibration.config(text=f"{sign}{self.offset_calibration} dB")
        
        # Rafraîchir l'affichage si données disponibles
        if hasattr(self, 'spectre_actuel') and hasattr(self, 'waterfall_data'):
            self.rafraichir_graphique(self.spectre_actuel, self.waterfall_data, force_full=True)
    
    def creer_graphique(self):
        """Crée le graphique matplotlib - IDENTIQUE à ic705_simple.py."""
        
        # Calculer l'axe des fréquences
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Créer la figure avec GridSpec pour avoir la colorbar à droite du waterfall
        self.fig = plt.figure(figsize=(9.5, 6), facecolor='#1a1a2e')
        gs = self.fig.add_gridspec(2, 2, width_ratios=[30, 1], hspace=0.3, wspace=0.05)
        
        self.ax_spectre = self.fig.add_subplot(gs[0, 0])
        self.ax_waterfall = self.fig.add_subplot(gs[1, 0])
        self.ax_colorbar = self.fig.add_subplot(gs[1, 1])
        
        # Style sombre
        self.ax_spectre.set_facecolor('#0a0a1a')
        self.ax_waterfall.set_facecolor('#0a0a1a')
        
        # === Configurer le spectre ===
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
        self.ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_spectre.set_ylabel('Niveau (dBm)', color='white')
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_ylim(self.dbm_min, self.dbm_max)
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
            cmap=WF_CMAP,
            vmin=self.dbm_min, vmax=self.dbm_max,
            origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        self.ax_waterfall.set_ylim(self.image_waterfall.get_extent()[2], 0)
        
        # === Créer la colorbar (jauge de couleurs) ===
        self.colorbar = self.fig.colorbar(
            self.image_waterfall, 
            cax=self.ax_colorbar,
            orientation='vertical'
        )
        self.colorbar.set_label('Niveau (dBm)', color='white', fontsize=10)
        self.ax_colorbar.tick_params(colors='white', labelsize=9)
        self.ax_colorbar.yaxis.set_ticks_position('right')
        self.ax_colorbar.yaxis.set_label_position('right')
        
        self.fig.tight_layout()
        
        # Intégrer dans Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_graph)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # Sauvegarder le background pour le blitting (optimisation)
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)
        self.use_blit = True
        
        # Connecter les événements souris pour le waterfall (mode CSV)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move_waterfall)
        self.canvas.mpl_connect('button_press_event', self.on_mouse_click_waterfall)
    
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
        current_depth = self.image_waterfall.get_array().shape[0] if hasattr(self.image_waterfall, 'get_array') else PROFONDEUR_WATERFALL
        self.image_waterfall.set_extent([freq_min, freq_max, current_depth, 0])
        self.ax_waterfall.set_xlim(freq_min, freq_max)
        self.ax_waterfall.set_ylim(current_depth, 0)
        self.waterfall_extent = (freq_min, freq_max, current_depth, 0)
        self.canvas.draw()
        # Recréer le background après modification
        if hasattr(self, 'use_blit') and self.use_blit:
            self.background = self.canvas.copy_from_bbox(self.fig.bbox)
    
    def on_mouse_move_waterfall(self, event):
        """Gère le survol de la souris sur le waterfall (mode CSV uniquement)."""
        # Seulement actif en mode lecture CSV
        if not self.mode_lecture_csv or not self.donnees_csv:
            return
        
        # Vérifier que la souris est dans l'axe du waterfall
        if event.inaxes != self.ax_waterfall:
            # Supprimer l'annotation de survol si on sort du waterfall
            if self.annotation_survol is not None:
                self.annotation_survol.remove()
                self.annotation_survol = None
                self.canvas.draw_idle()
            return
        
        # Récupérer les coordonnées
        x_freq = event.xdata
        y_ligne = event.ydata
        
        if x_freq is None or y_ligne is None:
            return
        
        # Obtenir les données du waterfall
        wf_data = self.image_waterfall.get_array()
        nb_lignes, nb_points = wf_data.shape
        
        # Convertir la position en indices
        extent = self.image_waterfall.get_extent()
        freq_min, freq_max = extent[0], extent[1]
        
        # Calculer l'index de fréquence
        idx_freq = int((x_freq - freq_min) / (freq_max - freq_min) * nb_points)
        idx_freq = max(0, min(idx_freq, nb_points - 1))
        
        # Calculer l'index de ligne
        idx_ligne = int(y_ligne)
        idx_ligne = max(0, min(idx_ligne, nb_lignes - 1))
        
        # Récupérer la valeur de gain
        gain = wf_data[idx_ligne, idx_freq]
        
        # Déterminer l'unité
        unite = "dB (log)" if self.conversion_log_flag else "dBm"
        
        # Mettre à jour ou créer l'annotation de survol
        texte = f"{gain:.1f} {unite}\n{x_freq:.4f} MHz"
        
        if self.annotation_survol is None:
            self.annotation_survol = self.ax_waterfall.annotate(
                texte,
                xy=(x_freq, y_ligne),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=9,
                color='white',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#333366', alpha=0.9, edgecolor='#00ccff'),
                zorder=100
            )
        else:
            self.annotation_survol.set_text(texte)
            self.annotation_survol.xy = (x_freq, y_ligne)
        
        self.canvas.draw_idle()
    
    def on_mouse_click_waterfall(self, event):
        """Gère le clic sur le waterfall (mode CSV) pour afficher gain et temps."""
        # Seulement actif en mode lecture CSV
        if not self.mode_lecture_csv or not self.donnees_csv:
            return
        
        # Vérifier que le clic est dans l'axe du waterfall
        if event.inaxes != self.ax_waterfall:
            return
        
        # Clic droit = effacer tous les marqueurs
        if event.button == 3:
            self.effacer_marqueurs_clic()
            return
        
        # Clic gauche uniquement
        if event.button != 1:
            return
        
        # Récupérer les coordonnées
        x_freq = event.xdata
        y_ligne = event.ydata
        
        if x_freq is None or y_ligne is None:
            return
        
        # Obtenir les données du waterfall
        wf_data = self.image_waterfall.get_array()
        nb_lignes, nb_points = wf_data.shape
        
        # Convertir la position en indices
        extent = self.image_waterfall.get_extent()
        freq_min, freq_max = extent[0], extent[1]
        
        idx_freq = int((x_freq - freq_min) / (freq_max - freq_min) * nb_points)
        idx_freq = max(0, min(idx_freq, nb_points - 1))
        
        idx_ligne = int(y_ligne)
        idx_ligne = max(0, min(idx_ligne, nb_lignes - 1))
        
        # Récupérer la valeur de gain
        gain = wf_data[idx_ligne, idx_freq]
        
        # Récupérer le timestamp associé à cette ligne
        timestamp_label = ""
        if hasattr(self, 'waterfall_time_labels') and idx_ligne < len(self.waterfall_time_labels):
            timestamp_label = self.waterfall_time_labels[idx_ligne]
        
        # Déterminer l'unité
        unite = "dB (log)" if self.conversion_log_flag else "dBm"
        
        # Créer le texte de l'annotation (sans emojis pour compatibilité police)
        texte = f"{gain:.1f} {unite}\n{x_freq:.4f} MHz\nT: {timestamp_label}"
        
        # Créer un marqueur et une annotation permanente
        marker, = self.ax_waterfall.plot(x_freq, y_ligne, 'o', color='#00ff00', markersize=8, zorder=99)
        
        annotation = self.ax_waterfall.annotate(
            texte,
            xy=(x_freq, y_ligne),
            xytext=(15, -15),
            textcoords='offset points',
            fontsize=9,
            color='white',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#1a4a1a', alpha=0.95, edgecolor='#00ff00'),
            arrowprops=dict(arrowstyle='->', color='#00ff00', lw=1.5),
            zorder=100
        )
        
        # Stocker pour pouvoir effacer plus tard
        self.clic_markers.append((marker, annotation))
        
        self.canvas.draw_idle()
        
        # Afficher aussi dans la console
        print(f"[Clic WF] {gain:.1f} {unite} @ {x_freq:.4f} MHz | {timestamp_label}")
    
    def effacer_marqueurs_clic(self):
        """Efface tous les marqueurs de clic sur le waterfall."""
        for marker, annotation in self.clic_markers:
            marker.remove()
            annotation.remove()
        self.clic_markers.clear()
        
        if self.annotation_clic is not None:
            self.annotation_clic.remove()
            self.annotation_clic = None
        
        self.canvas.draw_idle()
        print("[WF] Marqueurs effacés")
    
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
            self.connexion.send(CMD_STREAM_ON)
            self.log_trame_envoyee(CMD_STREAM_ON, "Activation streaming")
            time.sleep(0.3)
            
            # Demander la fréquence
            self.connexion.send(CMD_FREQ_REQUEST)
            self.log_trame_envoyee(CMD_FREQ_REQUEST, "Demande frequence")
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
        if not ENABLE_LOG_PANEL or not hasattr(self, 'text_log'):
            return
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
                self.connexion.send(CMD_STREAM_OFF)
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
        
        # Réinitialiser les statistiques cumulatives
        self.reset_statistiques()
        self.reset_buffer_binaire()
        
        # Lancer la réception dans un thread
        self.thread_reception = threading.Thread(target=self.boucle_reception, daemon=True)
        self.thread_reception.start()
        
        # Lancer la mise à jour de l'affichage
        self.boucle_affichage()
        
        # Lancer la mise à jour du log
        if ENABLE_LOG_PANEL:
            self.boucle_log()
    
    def arreter_affichage(self):
        """Arrête l'affichage."""
        self.affichage_actif = False
        self.btn_afficher.config(text="▶ Démarrer")
        self.btn_enregistrer.config(state='disabled')
        
        if self.enregistrement_actif:
            self.arreter_enregistrement()

    def reinitialiser_segments(self, nb_segments):
        """Reinitialise le buffer de segments spectre."""
        self.nb_segments_attendus = nb_segments
        self.segments_spectre = [None] * nb_segments
        self.segments_recus_count = 0

    def reset_buffer_binaire(self):
        """Reinitialise le buffer binaire."""
        if not self.use_buffer_bin:
            return
        with self.lock_buffer:
            self.buffer_bin.clear()
            self.buffer_dropped = 0

    def push_buffer_binaire(self, spectre, freq_centrale):
        """Ajoute un spectre au buffer binaire avec horodatage monotone."""
        if not self.use_buffer_bin:
            return
        now = time.monotonic()
        with self.lock_buffer:
            self.buffer_bin.append((now, freq_centrale, spectre))
            cutoff = now - self.buffer_max_sec
            while self.buffer_bin and self.buffer_bin[0][0] < cutoff:
                self.buffer_bin.popleft()
                self.buffer_dropped += 1

    def pop_buffer_binaire(self):
        """Recupere le dernier spectre disponible selon le delai configure."""
        if not self.use_buffer_bin:
            return None
        now = time.monotonic()
        ready = None
        with self.lock_buffer:
            while self.buffer_bin and (now - self.buffer_bin[0][0]) >= self.buffer_delay_sec:
                ready = self.buffer_bin.popleft()
        return ready


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
                        self.connexion.send(CMD_FREQ_REQUEST)
                    except:
                        pass
                continue
            except:
                break
            
            messages = trouver_messages_civ(buffer)
            
            for msg in messages:
                cmd = msg[4] if len(msg) > 4 else None

                log_enabled = self.log_actif_flag
                should_log_frame = False
                type_trame = None
                timestamp = None
                hex_data = None
                want_gain_info = log_enabled and self.log_gains_flag and not self.mode_lecture_csv

                if log_enabled:
                    type_trame = identifier_type_trame(msg)
                    if type_trame == "SPECTRE":
                        should_log_frame = self.log_spectre_flag
                    elif type_trame in ("GAIN", "LEVEL"):
                        should_log_frame = self.log_gains_flag
                    else:
                        should_log_frame = self.log_autres_flag

                    if should_log_frame or want_gain_info:
                        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    if should_log_frame:
                        hex_data = trame_vers_hex(msg)

                with self.lock_trames:
                    self.compteur_trames_total += 1
                    if should_log_frame and len(self.trames_a_logger) < MAX_TRAMES_QUEUE:
                        self.trames_a_logger.append((timestamp, type_trame, hex_data))
                    if want_gain_info and len(self.trames_a_logger) < MAX_TRAMES_QUEUE:
                        info_gain = f"f={self.freq_centrale:.3f} MHz | min={self.dbm_min} dBm | max={self.dbm_max} dBm"
                        self.trames_a_logger.append((timestamp, "LEVEL", info_gain))

                # Traiter les reponses de frequence (commande 0x03)
                if cmd == 0x03 and len(msg) >= 11:
                    freq = decoder_frequence_bcd(msg[5:10])
                    if freq > 0:
                        self.nouvelle_frequence = freq

                # Traiter les donnees spectre (commande 0x27)
                if cmd == 0x27 and len(msg) > 50:
                    result = extraire_donnees_spectre(msg)
                    if result is not None:
                        segment_num, nb_segments, amplitudes = result

                        # Si le nombre de segments change, reinitialiser
                        if nb_segments != self.nb_segments_attendus:
                            self.reinitialiser_segments(nb_segments)

                        # Stocker ce segment
                        if 0 <= segment_num < self.nb_segments_attendus:
                            if self.segments_spectre[segment_num] is None:
                                self.segments_recus_count += 1
                            self.segments_spectre[segment_num] = amplitudes

                        # Verifier si tous les segments sont recus
                        if self.nb_segments_attendus > 0 and self.segments_recus_count >= self.nb_segments_attendus:
                            spectre_array = np.concatenate(self.segments_spectre)
                            spectre = redimensionner_spectre(spectre_array, LARGEUR_SPECTRE)

                            if self.use_buffer_bin:
                                freq_centrale = self.nouvelle_frequence if self.nouvelle_frequence is not None else self.freq_centrale

                                self.push_buffer_binaire(spectre, freq_centrale)
                            else:
                                with self.lock_donnees:
                                    self.spectre_actuel = spectre.copy()
                                    self.waterfall_data[1:] = self.waterfall_data[:-1]
                                    self.waterfall_data[0] = spectre.copy()
                                    self.nouvelles_donnees = True

                            # Enregistrer dans le CSV si actif
                            if self.enregistrement_actif:
                                self.enregistrer_spectre(spectre)

                            # Reinitialiser pour le prochain cycle
                            self.reinitialiser_segments(self.nb_segments_attendus)

            if len(buffer) > 10000:
                buffer.clear()
    
    def boucle_affichage(self):
        """Boucle de mise à jour de l'affichage (thread principal)."""
        if not self.affichage_actif:
            return

        if self.use_buffer_bin and not self.mode_lecture_csv:
            ready = self.pop_buffer_binaire()
            if ready is not None:
                _, freq_centrale, spectre = ready
                if abs(freq_centrale - self.freq_centrale) > 0.0001:
                    self.freq_centrale = freq_centrale
                    self.mettre_a_jour_axe_freq()
                    self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
                with self.lock_donnees:
                    self.spectre_actuel = spectre
                    self.waterfall_data[1:] = self.waterfall_data[:-1]
                    self.waterfall_data[0] = spectre
                    self.nouvelles_donnees = True

        
        # Mettre à jour la fréquence si elle a changé
        if not self.use_buffer_bin and self.nouvelle_frequence is not None:
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
            self.rafraichir_graphique(spectre, waterfall)
            # Mise à jour des statistiques en temps réel
            self.mettre_a_jour_statistiques(spectre)

        # Mettre à jour le statut d'enregistrement (thread réception -> UI)
        if self.enregistrement_actif and hasattr(self, 'label_rec'):
            if self.rec_status_text != self.rec_status_last:
                try:
                    self.label_rec.config(text=self.rec_status_text)
                except tk.TclError:
                    pass
                self.rec_status_last = self.rec_status_text
        
        # Planifier la prochaine mise à jour (40ms = 25 FPS)
        self.root.after(40, self.boucle_affichage)
    
    def mettre_a_jour_statistiques(self, spectre):
        """Met à jour les labels de statistiques cumulatives depuis le démarrage."""
        try:
            if spectre is None or len(spectre) == 0:
                return
            
            # Calcul des statistiques de la trame actuelle
            trame_min = np.min(spectre)
            trame_max = np.max(spectre)
            trame_somme = np.sum(spectre)
            trame_count = len(spectre)
            
            # Mise à jour des statistiques cumulatives
            if self.stat_global_min is None:
                self.stat_global_min = trame_min
            else:
                self.stat_global_min = min(self.stat_global_min, trame_min)
            
            if self.stat_global_max is None:
                self.stat_global_max = trame_max
            else:
                self.stat_global_max = max(self.stat_global_max, trame_max)
            
            self.stat_somme += trame_somme
            self.stat_count += trame_count
            
            # Calcul de la moyenne globale
            val_moy = self.stat_somme / self.stat_count if self.stat_count > 0 else 0
            
            # Conversion en raw 0-255
            raw_min = int(round(self.stat_global_min))
            raw_max = int(round(self.stat_global_max))
            raw_moy = int(round(val_moy))
            
            # Mise à jour des labels
            self.label_stat_min.config(text=f"{self.stat_global_min:.1f} dBm ({raw_min})")
            self.label_stat_max.config(text=f"{self.stat_global_max:.1f} dBm ({raw_max})")
            self.label_stat_moy.config(text=f"{val_moy:.1f} dBm ({raw_moy})")
        except Exception:
            pass  # Ignore les erreurs pour ne pas bloquer l'affichage
    
    def reset_statistiques(self):
        """Réinitialise les statistiques cumulatives."""
        self.stat_global_min = None
        self.stat_global_max = None
        self.stat_somme = 0.0
        self.stat_count = 0
        try:
            self.label_stat_min.config(text="-- dBm (--)")
            self.label_stat_max.config(text="-- dBm (--)")
            self.label_stat_moy.config(text="-- dBm (--)")
        except (tk.TclError, AttributeError):
            pass
    
    def rafraichir_graphique(self, spectre=None, waterfall=None, force_full=False):
        """
        Redessine le spectre et/ou le waterfall.
        
        Quand force_full=True, on force un draw complet (utile hors mode temps réel)
        pour que la ligne du spectre soit bien visible même en mode lecture CSV.
        
        Les données brutes du IC-705 sont interprétées directement comme des niveaux dBm.
        """
        # Application optionnelle d'une conversion log supplémentaire
        if self.conversion_log_flag:
            if spectre is not None:
                spectre = self.convertir_spectre_log(spectre)
            if waterfall is not None:
                waterfall = self.convertir_spectre_log(waterfall)
        
        # Application de l'offset de calibration
        if self.offset_calibration != 0:
            if spectre is not None:
                spectre = spectre + self.offset_calibration
            if waterfall is not None:
                waterfall = waterfall + self.offset_calibration
        
        if spectre is not None:
            self.ligne_spectre.set_data(self.axe_freq, spectre)
        if waterfall is not None:
            waterfall = self.preparer_waterfall_pour_affichage(waterfall)
            self.image_waterfall.set_data(waterfall)
            depth = waterfall.shape[0]
            freq_min = self.axe_freq[0] if len(self.axe_freq) > 0 else 0
            freq_max = self.axe_freq[-1] if len(self.axe_freq) > 0 else 0
            new_extent = (freq_min, freq_max, depth, 0)
            if self.waterfall_extent != new_extent:
                self.image_waterfall.set_extent(new_extent)
                self.ax_waterfall.set_xlim(freq_min, freq_max)
                self.ax_waterfall.set_ylim(depth, 0)
                self.waterfall_extent = new_extent
        
        use_blit = getattr(self, 'use_blit', False) and hasattr(self, 'background')
        
        if use_blit and not force_full:
            try:
                self.canvas.restore_region(self.background)
                if spectre is not None:
                    self.ax_spectre.draw_artist(self.ligne_spectre)
                if waterfall is not None:
                    self.ax_waterfall.draw_artist(self.image_waterfall)
                self.canvas.blit(self.fig.bbox)
                self.canvas.flush_events()
                return
            except Exception:
                self.use_blit = False
                use_blit = False
        
        if force_full:
            use_blit = getattr(self, 'use_blit', False)
            if use_blit:
                # Recréer un background propre sans la ligne animée pour éviter les "doublons".
                self.ligne_spectre.set_animated(True)
                self.canvas.draw()
                self.background = self.canvas.copy_from_bbox(self.fig.bbox)
                self.ax_spectre.draw_artist(self.ligne_spectre)
                self.canvas.blit(self.fig.bbox)
            else:
                was_animated = self.ligne_spectre.get_animated()
                if was_animated:
                    self.ligne_spectre.set_animated(False)
                self.canvas.draw()
                if was_animated:
                    self.ligne_spectre.set_animated(True)
        else:
            self.canvas.draw_idle()
    
    def preparer_waterfall_pour_affichage(self, waterfall):
        """Retourne les données waterfall en tenant compte du zoom."""
        total_lignes = waterfall.shape[0]
        if not self.mode_lecture_csv:
            return waterfall
        lignes_voulues = min(self.get_waterfall_zoom_depth(), total_lignes)
        return waterfall[:lignes_voulues, :]
    
    def get_waterfall_zoom_depth(self):
        """Nombre de lignes de waterfall à afficher (mode lecture)."""
        return max(1, min(getattr(self, 'waterfall_zoom_lignes', PROFONDEUR_WATERFALL), PROFONDEUR_WATERFALL))
    
    def appliquer_zoom_waterfall(self):
        """Réapplique le zoom waterfall (utilisé lors d'un changement de slider)."""
        if not self.mode_lecture_csv:
            return
        self.rafraichir_graphique(self.spectre_actuel, self.waterfall_data, force_full=True)
        self.mettre_a_jour_echelle_temps(force=True)
    
    def configurer_affichage_csv(self, actif):
        """Active/désactive le mode affichage CSV (sans blitting pour éviter le clignotement)."""
        if actif:
            self.use_blit_avant_csv = getattr(self, 'use_blit', False)
            self.use_blit = False
            if hasattr(self, 'ligne_spectre'):
                self.ligne_spectre.set_animated(False)
        else:
            if self.use_blit_avant_csv:
                self.use_blit = True
                if hasattr(self, 'ligne_spectre'):
                    self.ligne_spectre.set_animated(True)
                if hasattr(self, 'canvas') and hasattr(self, 'fig'):
                    self.canvas.draw()
                    self.background = self.canvas.copy_from_bbox(self.fig.bbox)
            else:
                self.use_blit = False
                if hasattr(self, 'ligne_spectre'):
                    self.ligne_spectre.set_animated(False)
    
    def mettre_a_jour_echelle_temps(self, force=False):
        """Mets à jour les ticks Y du waterfall pour afficher les timestamps en lecture CSV."""
        if not hasattr(self, 'ax_waterfall'):
            return
        
        if not self.mode_lecture_csv:
            self.ax_waterfall.set_yticks([])
            self.ax_waterfall.set_yticklabels([])
            return
        
        now = time.monotonic()
        if not force and (now - self.derniere_maj_temps) < self.interval_maj_temps:
            return
        self.derniere_maj_temps = now
        
        depth = self.image_waterfall.get_array().shape[0] if hasattr(self.image_waterfall, 'get_array') else 0
        valides = [(i, ts) for i, ts in enumerate(self.waterfall_time_labels[:depth]) if ts]
        if not valides:
            self.ax_waterfall.set_yticks([])
            self.ax_waterfall.set_yticklabels([])
            return
        
        nb_ticks = min(6, len(valides))
        indices = np.linspace(0, len(valides) - 1, nb_ticks, dtype=int)
        ticks = []
        labels = []
        for idx in indices:
            pos, ts = valides[idx]
            ticks.append(pos)
            labels.append(self.formater_label_temps(ts))
        
        self.ax_waterfall.set_yticks(ticks)
        self.ax_waterfall.set_yticklabels(labels, color='white', fontsize=8)
        self.canvas.draw_idle()
    
    @staticmethod
    def formater_label_temps(ts):
        """Retourne une version lisible du timestamp pour l'affichage."""
        if ts is None:
            return ""
        ts = str(ts).strip()
        if not ts:
            return ""
        
        formats = (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%H:%M:%S.%f",
            "%H:%M:%S",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(ts, fmt)
                if "%f" in fmt:
                    return dt.strftime("%H:%M:%S.%f")[:-3]
                return dt.strftime("%H:%M:%S")
            except ValueError:
                continue
        
        # Fallback: extraire la partie temps si possible
        if "T" in ts:
            ts = ts.split("T", 1)[-1]
        if " " in ts:
            ts = ts.split(" ", 1)[-1]
        if ts.endswith("Z"):
            ts = ts[:-1]
        if "+" in ts:
            ts = ts.split("+", 1)[0]
        return ts

    def configurer_sliders_dbm(self):
        """Réinitialise les sliders à leurs valeurs dBm par défaut."""
        if not hasattr(self, 'slider_min') or not hasattr(self, 'slider_max'):
            return
        
        self.slider_min.config(from_=0, to=100)
        self.slider_max.config(from_=50, to=150)
        self.slider_min.set(self.dbm_min)
        self.slider_max.set(self.dbm_max)
        self.label_gain.config(text=f"Plage dBm: [{self.dbm_min} - {self.dbm_max}]")

    @staticmethod
    def convertir_spectre_log(spectre):
        """Applique une conversion logarithmique supplémentaire (optionnelle)."""
        valeurs = np.asarray(spectre, dtype=np.float32)
        valeurs = np.maximum(valeurs, 1e-3)
        return 20.0 * np.log10(valeurs)
    
    def on_toggle_conversion_log(self):
        """Appelé quand l'option de conversion log change."""
        try:
            self.conversion_log_flag = bool(self.conversion_log.get())
        except tk.TclError:
            self.conversion_log_flag = False

    def unite_trigger(self):
        """Retourne l'unité affichée pour le trigger (toujours dBm)."""
        return "dBm"
    
    def boucle_log(self):
        """Met à jour le log des trames."""
        if not ENABLE_LOG_PANEL or not hasattr(self, 'text_log'):
            return
        if not self.affichage_actif:
            return
        
        try:
            with self.lock_trames:
                trames = self.trames_a_logger
                self.trames_a_logger = []
            
            if trames:
                self.ajouter_trames_batch(trames)
            
            if self.affichage_actif:
                self.root.after(LOG_UPDATE_INTERVAL, self.boucle_log)
        except tk.TclError:
            pass  # Fenêtre fermée, ignorer
    
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
                self.rec_status_text = f"⏺ TRIGGER: attente signal > {self.seuil_trigger} {self.unite_trigger()}"
                self.rec_status_last = None
                self.label_rec.config(text=self.rec_status_text)
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
            
            # Header avec le bon nombre de colonnes (LARGEUR_SPECTRE = 950)
            header = ['timestamp', 'freq_mhz', 'span_khz']
            header.extend([f'val_{i}' for i in range(LARGEUR_SPECTRE)])
            self.writer_csv.writerow(header)
            print(f"CSV créé avec {len(header)} colonnes (3 + {LARGEUR_SPECTRE} valeurs)")
            
            self.enregistrement_actif = True
            self.nb_lignes_csv = 0
            
            self.btn_enregistrer.config(text="⏹ STOP")
            self.rec_status_text = f"⏺ REC: {os.path.basename(self.nom_fichier_csv)}"
            self.rec_status_last = None
            self.label_rec.config(text=self.rec_status_text)
            
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
        self.rec_status_text = ""
        self.rec_status_last = None
        
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
        
        # Les données brutes sont déjà en dBm
        max_signal = float(np.max(spectre))
        seuil = self.seuil_trigger
        
        if self.trigger_actif_flag:
            if max_signal >= seuil:
                if not self.au_dessus_seuil:
                    self.au_dessus_seuil = True
                    self.creer_nouveau_csv_trigger()
                
                if self.writer_csv:
                    self.ecrire_ligne_csv(spectre)
            else:
                if self.au_dessus_seuil:
                    self.au_dessus_seuil = False
                    self.fermer_csv_trigger()
                    self.rec_status_text = f"⏺ TRIGGER: attente signal > {seuil} dBm"
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
            self.rec_status_text = f"⏺ TRIGGER #{self.nb_fichiers_trigger}: enregistrement..."
            
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
            # Vérifier que le spectre a la bonne taille
            if len(spectre) != LARGEUR_SPECTRE:
                print(f"Attention: spectre de taille {len(spectre)} au lieu de {LARGEUR_SPECTRE}")
                return
            
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            ligne = [ts, f"{self.freq_centrale:.6f}", SPAN_KHZ]
            ligne.extend([f"{v:.1f}" for v in spectre])
            
            self.writer_csv.writerow(ligne)
            self.nb_lignes_csv += 1
            
            if self.nb_lignes_csv % 100 == 0:
                self.fichier_csv.flush()
                if self.trigger_actif_flag:
                    self.rec_status_text = f"⏺ TRIGGER #{self.nb_fichiers_trigger}: {self.nb_lignes_csv} lignes"
                else:
                    self.rec_status_text = f"⏺ REC: {self.nb_lignes_csv} lignes"
                
        except Exception as e:
            print(f"Erreur écriture CSV: {e}")
    
    # === Fonctions de lecture CSV ===
    @staticmethod
    def _spectre_max_from_row(row):
        """Retourne le max d'une ligne CSV sans stocker le spectre."""
        try:
            return max(float(v) for v in row[3:3 + LARGEUR_SPECTRE])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parser_csv_row(row):
        """Parse une ligne CSV en dictionnaire de donnees."""
        try:
            timestamp = row[0]
            freq = float(row[1])
            span = int(float(row[2]))
            valeurs = np.fromiter(
                (float(v) for v in row[3:3 + LARGEUR_SPECTRE]),
                dtype=np.float32,
                count=LARGEUR_SPECTRE
            )
            if valeurs.size != LARGEUR_SPECTRE:
                return None
            return {
                'timestamp': timestamp,
                'timestamp_label': None,
                'freq': freq,
                'span': span,
                'spectre': valeurs
            }
        except (ValueError, IndexError):
            return None

    def _get_timestamp_label(self, data):
        """Calcule le label temps a la demande (cache dans la ligne)."""
        label = data.get('timestamp_label')
        if not label:
            label = self.formater_label_temps(data.get('timestamp'))
            data['timestamp_label'] = label
        return label

    
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
            lignes_ignorees = 0
            nb_colonnes_attendues = 3 + LARGEUR_SPECTRE

            use_filter = messagebox.askyesno(
                "Filtre CSV",
                "Filtrer les lignes par seuil de gain ?"
            )
            seuil_gain = None
            contexte_lignes = 0
            if use_filter:
                seuil_gain = simpledialog.askfloat(
                    "Seuil gain",
                    "Seuil dBm (ex: 70):",
                    parent=self.root
                )
                if seuil_gain is None:
                    return
                contexte_lignes = simpledialog.askinteger(
                    "Contexte",
                    "Nb lignes avant/apres (ex: 10):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=500
                )
                if contexte_lignes is None:
                    return

            with open(fichier, 'r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    messagebox.showerror("Erreur", "Fichier CSV vide.")
                    return
                nb_colonnes_header = len(header)

                print(f"CSV: {nb_colonnes_header} colonnes dans le header, {nb_colonnes_attendues} attendues")

                if use_filter:
                    buffer_avant = deque(maxlen=contexte_lignes)
                    after_count = 0
                    last_index_added = -1

                for idx, row in enumerate(reader):
                    if len(row) < nb_colonnes_attendues:
                        lignes_ignorees += 1
                        if lignes_ignorees <= 5:
                            print(f"Ligne {idx+2} ignoree: {len(row)} colonnes au lieu de {nb_colonnes_attendues}")
                        continue

                    if use_filter:
                        max_val = self._spectre_max_from_row(row)
                        if max_val is None:
                            lignes_ignorees += 1
                            if lignes_ignorees <= 5:
                                print(f"Ligne {idx+2} ignoree: valeurs invalides")
                            continue

                        hit = max_val >= seuil_gain
                        if hit:
                            for prev_idx, prev_row in buffer_avant:
                                if prev_idx > last_index_added:
                                    data = self._parser_csv_row(prev_row)
                                    if data:
                                        self.donnees_csv.append(data)
                                        last_index_added = prev_idx
                                    else:
                                        lignes_ignorees += 1
                            buffer_avant.clear()

                            data = self._parser_csv_row(row)
                            if data:
                                self.donnees_csv.append(data)
                                last_index_added = idx
                            else:
                                lignes_ignorees += 1

                            after_count = contexte_lignes
                            continue

                        if after_count > 0:
                            data = self._parser_csv_row(row)
                            if data:
                                self.donnees_csv.append(data)
                                last_index_added = idx
                            else:
                                lignes_ignorees += 1
                            after_count -= 1
                            continue

                        buffer_avant.append((idx, row))
                    else:
                        data = self._parser_csv_row(row)
                        if data:
                            self.donnees_csv.append(data)
                        else:
                            lignes_ignorees += 1
                            if lignes_ignorees <= 5:
                                print(f"Ligne {idx+2} ignoree: valeurs invalides")

            if lignes_ignorees > 0:
                print(f"Total: {lignes_ignorees} ligne(s) ignoree(s)")

            if not self.donnees_csv:
                if use_filter:
                    messagebox.showerror("Erreur", "Aucune donnee apres filtrage.")
                else:
                    messagebox.showerror("Erreur", "Aucune donnee valide dans le fichier CSV")
                return

            print(f"CSV charge: {len(self.donnees_csv)} lignes valides")

            self.waterfall_zoom_lignes = PROFONDEUR_WATERFALL
            self.derniere_ligne_rejouee = None
            self.mode_lecture_csv = True
            self.index_lecture = 0
            self.masquer_panneau_log()
            self.configurer_affichage_csv(True)

            if use_filter:
                self.csv_filter_info = f">= {seuil_gain} dBm, ctx {contexte_lignes}"
                self.label_status.config(
                    text=f"CSV: {len(self.donnees_csv)} lignes (filtre {self.csv_filter_info})",
                    fg='#00ccff'
                )
            else:
                self.csv_filter_info = None
                self.label_status.config(text=f"CSV: {len(self.donnees_csv)} lignes", fg='#00ccff')

            self.btn_ouvrir_csv.config(text="Fermer CSV")

            self.btn_connecter.config(state='disabled')
            self.entry_ip.config(state='disabled')
            self.entry_port.config(state='disabled')

            self.charger_donnees_csv(force_rebuild=True)
            self.creer_controles_lecture()

        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier CSV:\n{e}")

    def fermer_csv_lecture(self):
        """Ferme le mode lecture CSV."""
        self.arreter_lecture()
        self.mode_lecture_csv = False
        self.donnees_csv = None
        self.csv_filter_info = None
        self.waterfall_zoom_lignes = PROFONDEUR_WATERFALL
        self.derniere_ligne_rejouee = None
        self.afficher_panneau_log()
        self.configurer_affichage_csv(False)
        self.conversion_log.set(False)
        self.conversion_log_flag = False
        
        # Effacer les marqueurs de clic sur le waterfall
        self.effacer_marqueurs_clic()
        if self.annotation_survol is not None:
            self.annotation_survol.remove()
            self.annotation_survol = None
        
        if hasattr(self, 'label_trigger_unit'):
            self.label_trigger_unit.config(text="(dBm)")
        if hasattr(self, 'image_waterfall'):
            self.image_waterfall.set_cmap(WF_CMAP)
            self.image_waterfall.set_clim(vmin=self.dbm_min, vmax=self.dbm_max)
        if hasattr(self, 'ax_spectre'):
            self.ax_spectre.set_ylabel("Niveau (dBm)")
            self.ax_spectre.set_ylim(self.dbm_min, self.dbm_max)
        self.configurer_sliders_dbm()
        
        if hasattr(self, 'frame_lecture'):
            self.frame_lecture.destroy()
            del self.frame_lecture
        if hasattr(self, 'btn_play'):
            del self.btn_play
        
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.btn_ouvrir_csv.config(text="Open CSV")
        self.btn_connecter.config(state='normal')
        self.entry_ip.config(state='normal')
        self.entry_port.config(state='normal')
        self.label_freq.config(text="---")
        
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.waterfall_time_labels = [""] * PROFONDEUR_WATERFALL
        self.freq_centrale = FREQUENCE_DEFAUT
        self.mettre_a_jour_axe_freq()
        
        self.rafraichir_graphique(self.spectre_actuel, self.waterfall_data, force_full=True)
        self.mettre_a_jour_echelle_temps(force=True)
    
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
        
        tk.Label(
            self.frame_lecture,
            text="Rendu:",
            font=("Helvetica", 10),
            fg='#aaaaaa',
            bg='#1a1a2e'
        ).pack(side='left', padx=5)

        self.slider_rendu = tk.Scale(
            self.frame_lecture,
            from_=1, to=5,
            orient='horizontal',
            length=90,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 9),
            command=self.on_rendu_change
        )
        self.slider_rendu.set(self.csv_render_every)
        self.slider_rendu.pack(side='left', padx=5)

        tk.Label(
            self.frame_lecture,
            text="Zoom WF:",
            font=("Helvetica", 10),
            fg='#aaaaaa',
            bg='#1a1a2e'
        ).pack(side='left', padx=5)
        
        self.slider_zoom_wf = tk.Scale(
            self.frame_lecture,
            from_=5, to=PROFONDEUR_WATERFALL,
            orient='horizontal',
            length=120,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            font=('Helvetica', 9),
            command=self.on_zoom_waterfall_change
        )
        self.slider_zoom_wf.set(self.get_waterfall_zoom_depth())
        self.slider_zoom_wf.pack(side='left', padx=5)
        
        self.cb_conv_log = tk.Checkbutton(
            self.frame_lecture,
            text="Conv. Log",
            variable=self.conversion_log,
            font=('Helvetica', 10, 'bold'),
            bg='#1a1a2e',
            fg='white',
            selectcolor='#2a2a4e',
            command=self.on_toggle_conversion_log_lecture
        )
        self.cb_conv_log.pack(side='left', padx=10)
        
        self.mettre_slider_position(self.index_lecture)
        self.appliquer_scale_police(self.frame_lecture)
    
    def mettre_slider_position(self, index):
        """Met à jour le slider de position sans déclencher d'événement."""
        if hasattr(self, 'slider_position'):
            self.slider_update_en_cours = True
            self.slider_position.set(index)
            self.slider_update_en_cours = False
    
    def on_slider_position_change(self, value):
        """Appelé quand le slider de position change."""
        if self.slider_update_en_cours:
            return
        self.aller_a_position(int(value), force_rebuild=True)
    
    def on_rendu_change(self, value):
        """Ajuste la cadence de rendu pour la lecture CSV."""
        try:
            rendu = int(float(value))
        except (TypeError, ValueError):
            return
        rendu = max(1, min(rendu, 5))
        self.csv_render_every = rendu
        self.csv_stats_every = max(1, rendu * 2)
        self.csv_ticks_every = max(1, rendu * 3)
        self.csv_slider_every = max(1, rendu)

    def on_zoom_waterfall_change(self, value):
        """Change le zoom du waterfall (lecture CSV)."""
        try:
            lignes = int(float(value))
        except (TypeError, ValueError):
            return
        self.waterfall_zoom_lignes = max(1, min(lignes, PROFONDEUR_WATERFALL))
        self.appliquer_zoom_waterfall()
    
    def on_toggle_conversion_log_lecture(self):
        """Bascule la conversion log supplémentaire (lecture CSV)."""
        try:
            actif = bool(self.conversion_log.get())
        except tk.TclError:
            actif = False
        self.conversion_log_flag = actif
        
        # Rafraîchir avec les données courantes
        self.rafraichir_graphique(self.spectre_actuel, self.waterfall_data, force_full=True)
    
    def aller_a_position(self, index, force_rebuild=True):
        """Va à une position spécifique dans le CSV."""
        if not self.donnees_csv or index < 0 or index >= len(self.donnees_csv):
            return
        
        self.index_lecture = index
        self.charger_donnees_csv(force_rebuild=force_rebuild)
        self.mettre_slider_position(index)
    
    def charger_donnees_csv(self, force_rebuild=False, render=True, update_stats=True, update_ticks=True, update_labels=True):
        """Charge et affiche les données à la position actuelle."""
        if not self.donnees_csv:
            return
        
        data = self.donnees_csv[self.index_lecture]
        
        if len(data['spectre']) != LARGEUR_SPECTRE:
            print(f"Attention: spectre ligne {self.index_lecture} a {len(data['spectre'])} points au lieu de {LARGEUR_SPECTRE}")
        
        freq_changed = data['freq'] != self.freq_centrale
        if freq_changed:
            self.freq_centrale = data['freq']
            demi_span = SPAN_KHZ / 2000
            freq_min = self.freq_centrale - demi_span
            freq_max = self.freq_centrale + demi_span
            self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
            self.ax_spectre.set_xlim(freq_min, freq_max)
            self.ax_spectre.set_title(f"Spectre IC-705 - {self.freq_centrale:.3f} MHz (CSV)", color='white')
            self.ax_spectre.set_ylabel("Niveau (dBm)")
            self.ax_spectre.set_ylim(self.dbm_min, self.dbm_max)
            current_depth = self.waterfall_data.shape[0]
            self.image_waterfall.set_extent([freq_min, freq_max, current_depth, 0])
            self.ax_waterfall.set_xlim(freq_min, freq_max)
            self.ax_waterfall.set_ylim(current_depth, 0)
            self.waterfall_extent = (freq_min, freq_max, current_depth, 0)
            self.ligne_centre.set_xdata([self.freq_centrale, self.freq_centrale])
        
        self.spectre_actuel = data['spectre']
        
        if not force_rebuild and self.derniere_ligne_rejouee is not None and self.index_lecture == self.derniere_ligne_rejouee + 1:
            self.mettre_a_jour_waterfall_incremental(data)
            force_full = False
        else:
            self.reconstruire_waterfall_depuis_index()
            force_full = True
        
        self.derniere_ligne_rejouee = self.index_lecture
        
        if render:
            self.rafraichir_graphique(self.spectre_actuel, self.waterfall_data, force_full=force_full)
        if update_stats:
            self.mettre_a_jour_statistiques(self.spectre_actuel)
        if update_ticks:
            self.mettre_a_jour_echelle_temps(force=force_full)
        
        if update_labels or freq_changed:
            self.label_freq.config(text=f"{self.freq_centrale:.3f} MHz")
            if hasattr(self, 'label_position'):
                self.label_position.config(
                    text=f"{self.index_lecture + 1} / {len(self.donnees_csv)} - {self._get_timestamp_label(data)}"
                )
    
    def mettre_a_jour_waterfall_incremental(self, data):
        """Décale le waterfall et insère la nouvelle ligne (lecture séquentielle)."""
        self.waterfall_data[1:] = self.waterfall_data[:-1]
        self.waterfall_data[0] = data['spectre']
        self.waterfall_time_labels[1:] = self.waterfall_time_labels[:-1]
        self.waterfall_time_labels[0] = self._get_timestamp_label(data)
    
    def reconstruire_waterfall_depuis_index(self):
        """Reconstruit entièrement le waterfall autour de l'index courant."""
        self.waterfall_data.fill(0)
        self.waterfall_time_labels = [""] * PROFONDEUR_WATERFALL
        
        dest = 0
        for src in range(self.index_lecture, -1, -1):
            if dest >= PROFONDEUR_WATERFALL:
                break
            ligne = self.donnees_csv[src]['spectre']
            self.waterfall_data[dest] = ligne
            self.waterfall_time_labels[dest] = self._get_timestamp_label(self.donnees_csv[src])
            dest += 1
    
    def toggle_lecture(self):
        """Démarre ou arrête la lecture automatique."""
        if self.lecture_en_cours:
            self.arreter_lecture()
        else:
            self.demarrer_lecture()
    
    def demarrer_lecture(self):
        """Démarre la lecture automatique."""
        self.lecture_en_cours = True
        self.csv_frame_count = 0
        if hasattr(self, 'btn_play'):
            try:
                self.btn_play.config(text="⏸ Pause")
            except tk.TclError:
                pass
        self.lecture_auto()
    
    def arreter_lecture(self):
        """Arrête la lecture automatique."""
        self.lecture_en_cours = False
        if hasattr(self, 'btn_play'):
            try:
                self.btn_play.config(text="▶ Play")
            except tk.TclError:
                pass
    
    def lecture_auto(self):
        """Boucle de lecture automatique."""
        if not self.lecture_en_cours or not self.mode_lecture_csv:
            return

        if self.index_lecture < len(self.donnees_csv) - 1:
            self.index_lecture += 1
            self.csv_frame_count += 1

            render = (self.csv_frame_count % self.csv_render_every) == 0
            update_stats = (self.csv_frame_count % self.csv_stats_every) == 0
            update_ticks = (self.csv_frame_count % self.csv_ticks_every) == 0
            update_slider = (self.csv_frame_count % self.csv_slider_every) == 0

            self.charger_donnees_csv(
                force_rebuild=False,
                render=render,
                update_stats=update_stats,
                update_ticks=update_ticks,
                update_labels=render
            )
            if update_slider:
                self.mettre_slider_position(self.index_lecture)

            try:
                vitesse = self.slider_vitesse.get()
            except Exception:
                vitesse = 10
            # Pour limiter la charge CPU/Tk sur macOS, delai min 40ms (~25 FPS)
            delai = max(40, 200 // max(1, int(vitesse)))

            try:
                self.after_lecture_id = self.root.after(delai, self.lecture_auto)
            except tk.TclError:
                self.after_lecture_id = None
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
    app = IC705AppV7(root)
    root.mainloop()
