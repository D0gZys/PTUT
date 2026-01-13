#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC-705 CSV Viewer v7
===================
Lecture et visualisation des spectres CSV (post-capture).

Fonctions:
- Chargement CSV avec filtre et contexte
- Lecture pas a pas / auto
- Affichage spectre + waterfall en dBm
"""

import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import tkinter.font as tkfont
from collections import deque
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

FREQUENCE_DEFAUT = 7.100
SPAN_KHZ = 200
LARGEUR_SPECTRE = 950  # Augmentee pour plus de details
PROFONDEUR_WATERFALL = 80  # Reduit pour maintenir les performances
DOSSIER_CSV = "recep_csv"
# Plage dBm par defaut pour l'affichage (donnees brutes IC-705)
DBM_MIN = 0
DBM_MAX = 120
WF_CMAP = "inferno"  # Colormap pour le waterfall
UI_SCALE = 1.25
FONT_SCALE = 1.35
WINDOW_START_RATIO = 0.9
BASE_WINDOW_WIDTH = 1400
BASE_WINDOW_HEIGHT = 800
MIN_FONT_SCALE = 1.0
MAX_FONT_SCALE = 2.0

class IC705AppV7:
    """Application principale avec interface Tkinter - Version 7."""
    
    def __init__(self, root):
        """Initialise l'application."""
        self.root = root
        self.root.title("IC-705 CSV Viewer v7 - dBm")
        self.root.geometry("1400x800")
        self.root.configure(bg='#1a1a2e')
        self.root.minsize(1200, 600)
        self.ajuster_taille_fenetre()
        self.appliquer_scaling_ui()
        
        self.freq_centrale = FREQUENCE_DEFAUT
        
        # Données du spectre et waterfall
        self.spectre_actuel = np.zeros(LARGEUR_SPECTRE)
        self.waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        self.waterfall_time_labels = [""] * PROFONDEUR_WATERFALL
        self.waterfall_zoom_lignes = PROFONDEUR_WATERFALL
        self.derniere_ligne_rejouee = None
        self.slider_update_en_cours = False
        self.derniere_maj_temps = 0.0
        self.interval_maj_temps = 0.2
        self.waterfall_extent = None
        self.use_blit_avant_csv = None
        
        
        # Paramètres de niveau dBm (données brutes IC-705)
        self.dbm_min = DBM_MIN
        self.dbm_max = DBM_MAX
        self.offset_calibration = 0  # Offset de calibration en dB
        
        # Statistiques cumulatives depuis le démarrage
        self.stat_global_min = None  # Min absolu depuis démarrage
        self.stat_global_max = None  # Max absolu depuis démarrage
        self.stat_somme = 0.0        # Somme pour calcul moyenne
        self.stat_count = 0          # Nombre d'échantillons
        
        
        
        # Option de conversion log (désactivée par défaut car données déjà en dBm)
        self.conversion_log = tk.BooleanVar(value=False)
        self.conversion_log_flag = False
        
        
        
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

        self.widget_fonts = {}
        self.widget_base_sizes = {}
        self.widget_base_lengths = {}
        self.font_scale_current = FONT_SCALE
        self.pending_resize_id = None

        
        # Annotations souris sur waterfall (mode CSV)
        self.annotation_survol = None
        self.annotation_clic = None
        self.clic_markers = []  # Liste pour stocker les marqueurs de clic
        
        # Créer l'interface
        self.creer_interface()
        self.appliquer_scale_police()
        self.root.bind("<Configure>", self.on_window_resize)
        self.root.after(200, self._apply_resize_scale)
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

    def _calc_window_scale(self):
        """Calcule le facteur de scale selon la taille de la fenetre."""
        try:
            width = self.root.winfo_width()
            height = self.root.winfo_height()
        except tk.TclError:
            return FONT_SCALE
        if width <= 1 or height <= 1:
            width = int(self.root.winfo_screenwidth() * WINDOW_START_RATIO)
            height = int(self.root.winfo_screenheight() * WINDOW_START_RATIO)
        scale = min(width / BASE_WINDOW_WIDTH, height / BASE_WINDOW_HEIGHT)
        scale = max(MIN_FONT_SCALE, min(MAX_FONT_SCALE, scale))
        return scale * FONT_SCALE

    def on_window_resize(self, event):
        """Planifie une mise a jour du scale lors du resize."""
        if event.widget != self.root:
            return
        if self.pending_resize_id is not None:
            try:
                self.root.after_cancel(self.pending_resize_id)
            except tk.TclError:
                pass
        try:
            self.pending_resize_id = self.root.after(150, self._apply_resize_scale)
        except tk.TclError:
            self.pending_resize_id = None

    def _apply_resize_scale(self):
        """Applique le scale calcule aux widgets."""
        self.pending_resize_id = None
        new_scale = self._calc_window_scale()
        if abs(new_scale - self.font_scale_current) < 0.05:
            return
        self.font_scale_current = new_scale
        self.appliquer_scale_police()

    def _scale_widget(self, widget):
        """Applique le scaling de police a un widget."""
        try:
            font_spec = widget.cget('font')
        except tk.TclError:
            font_spec = None

        if font_spec:
            font_obj = self.widget_fonts.get(widget)
            if font_obj is None:
                try:
                    font_obj = tkfont.Font(root=self.root, font=font_spec)
                except tk.TclError:
                    font_obj = None
                if font_obj is not None:
                    base_size = font_obj.cget('size')
                    self.widget_base_sizes[widget] = base_size
                    self.widget_fonts[widget] = font_obj
                    try:
                        widget.configure(font=font_obj)
                    except tk.TclError:
                        pass
            else:
                base_size = self.widget_base_sizes.get(widget, font_obj.cget('size'))

            if font_obj is not None:
                if base_size == 0:
                    return
                if base_size > 0:
                    new_size = max(1, int(round(base_size * self.font_scale_current)))
                else:
                    new_size = -max(1, int(round(abs(base_size) * self.font_scale_current)))
                try:
                    font_obj.configure(size=new_size)
                except tk.TclError:
                    pass

        if isinstance(widget, tk.Scale):
            if widget not in self.widget_base_lengths:
                try:
                    self.widget_base_lengths[widget] = int(float(widget.cget('length')))
                except tk.TclError:
                    self.widget_base_lengths[widget] = None
            base_len = self.widget_base_lengths.get(widget)
            if base_len:
                try:
                    widget.configure(length=int(base_len * self.font_scale_current))
                except tk.TclError:
                    pass

    def appliquer_scale_police(self, widget=None):
        """Applique le scaling des polices a tous les widgets."""
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
            text="IC-705 CSV Viewer v7 - dBm",
            font=("Helvetica", 18, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre.pack(side='left', padx=10)
        
        # Bouton ouvrir CSV
        self.btn_ouvrir_csv = tk.Button(
            frame_controles,
            text="Open CSV",
            font=("Helvetica", 12, "bold"),
            width=12,
            command=self.ouvrir_csv
        )
        self.btn_ouvrir_csv.pack(side='left', padx=10)
        
        # Status
        self.label_status = tk.Label(
            frame_controles,
            text="Aucun CSV",
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
        
        # === Frame principale contenant le graphique ===
        self.frame_principal = tk.Frame(self.root, bg='#1a1a2e')
        self.frame_principal.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Frame gauche pour le graphique
        self.frame_graph = tk.Frame(self.frame_principal, bg='#1a1a2e')
        self.frame_graph.pack(side='left', fill='both', expand=True)
        
        # Frame droite pour le log des trames (optionnel)
    
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
        self.configurer_affichage_csv(False)
        self.conversion_log.set(False)
        self.conversion_log_flag = False

        # Effacer les marqueurs de clic sur le waterfall
        self.effacer_marqueurs_clic()
        if self.annotation_survol is not None:
            self.annotation_survol.remove()
            self.annotation_survol = None

        if hasattr(self, "image_waterfall"):
            self.image_waterfall.set_cmap(WF_CMAP)
            self.image_waterfall.set_clim(vmin=self.dbm_min, vmax=self.dbm_max)
        if hasattr(self, "ax_spectre"):
            self.ax_spectre.set_ylabel("Niveau (dBm)")
            self.ax_spectre.set_ylim(self.dbm_min, self.dbm_max)
        self.configurer_sliders_dbm()

        if hasattr(self, "frame_lecture"):
            self.frame_lecture.destroy()
            del self.frame_lecture
        if hasattr(self, "btn_play"):
            del self.btn_play

        self.label_status.config(text="Aucun CSV", fg="#ff6666")
        self.btn_ouvrir_csv.config(text="Open CSV")
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
