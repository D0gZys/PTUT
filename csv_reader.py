#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV Reader - Visualisation des enregistrements IC-705
=====================================================
Lit les fichiers CSV générés par ic705_tkinter_v8.py
et recrée l'affichage du spectre et du waterfall.

Fonctionnalités:
- Lecture des CSV (spectre ou trigger)
- Affichage spectre + waterfall animé
- Contrôles: Play/Pause, vitesse, navigation
- Sliders min/max dBm ajustables
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import csv
import os
from datetime import datetime

# Backend matplotlib
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import FuncFormatter

# ============================================================
#              PARAMÈTRES
# ============================================================

LARGEUR_SPECTRE = 475
PROFONDEUR_WATERFALL = 200
WF_CMAP = "inferno"

DBM_MIN_DEFAULT = -160
DBM_MAX_DEFAULT = -80


# ============================================================
#              CLASSE PRINCIPALE
# ============================================================

class CSVReader:
    """Lecteur et visualiseur de fichiers CSV spectre."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("CSV Reader - IC-705 Spectrum")
        self.root.geometry("1200x750")
        self.root.configure(bg='#1a1a2e')
        
        # Données
        self.donnees = []           # Liste de dictionnaires {timestamp, freq, span, ref, spectre}
        self.index_courant = 0
        self.nb_lignes = 0
        self.largeur_spectre = LARGEUR_SPECTRE
        
        # Waterfall buffer
        self.waterfall = np.full((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE), -160.0)
        self.waterfall_times = [''] * PROFONDEUR_WATERFALL  # Buffer des timestamps
        
        # Paramètres affichage
        self.dbm_min = DBM_MIN_DEFAULT
        self.dbm_max = DBM_MAX_DEFAULT
        
        # État lecture
        self.en_lecture = False
        self.vitesse = 1.0          # Multiplicateur de vitesse
        self.timer_id = None
        
        # Fichier chargé
        self.fichier_charge = None
        
        # Interface
        self.creer_interface()
        self.creer_graphique()
    
    def creer_interface(self):
        """Crée l'interface utilisateur."""
        
        # === Barre supérieure ===
        top = tk.Frame(self.root, bg='#1a1a2e')
        top.pack(fill='x', padx=10, pady=5)
        
        # Bouton ouvrir
        self.btn_ouvrir = tk.Button(top, text="📂 Ouvrir CSV", command=self.ouvrir_fichier,
                                     bg='#4a90d9', fg='white', font=('Helvetica', 10, 'bold'))
        self.btn_ouvrir.pack(side='left', padx=5)
        
        # Bouton exporter waterfall
        self.btn_export = tk.Button(top, text="🖼️ Exporter", command=self.exporter_waterfall,
                                     bg='#9a4ad9', fg='white', font=('Helvetica', 10, 'bold'),
                                     state='disabled')
        self.btn_export.pack(side='left', padx=5)
        
        # Label fichier
        self.lbl_fichier = tk.Label(top, text="Aucun fichier chargé", 
                                     fg='#888888', bg='#1a1a2e', font=('Helvetica', 10))
        self.lbl_fichier.pack(side='left', padx=10)
        
        # Info à droite
        self.lbl_info = tk.Label(top, text="", fg='#ffcc00', bg='#1a1a2e', 
                                  font=('Consolas', 10))
        self.lbl_info.pack(side='right', padx=10)
        
        # === Contrôles de lecture ===
        ctrl = tk.Frame(self.root, bg='#1a1a2e')
        ctrl.pack(fill='x', padx=10, pady=5)
        
        # Boutons de contrôle
        self.btn_debut = tk.Button(ctrl, text="⏮", command=self.aller_debut,
                                    width=3, state='disabled')
        self.btn_debut.pack(side='left', padx=2)
        
        self.btn_reculer = tk.Button(ctrl, text="⏪", command=self.reculer_10,
                                      width=3, state='disabled')
        self.btn_reculer.pack(side='left', padx=2)
        
        self.btn_play = tk.Button(ctrl, text="▶ Play", command=self.toggle_lecture,
                                   width=8, state='disabled', bg='#4a90d9', fg='white')
        self.btn_play.pack(side='left', padx=5)
        
        self.btn_avancer = tk.Button(ctrl, text="⏩", command=self.avancer_10,
                                      width=3, state='disabled')
        self.btn_avancer.pack(side='left', padx=2)
        
        self.btn_fin = tk.Button(ctrl, text="⏭", command=self.aller_fin,
                                  width=3, state='disabled')
        self.btn_fin.pack(side='left', padx=2)
        
        # Slider position
        tk.Label(ctrl, text="  Position:", fg='white', bg='#1a1a2e').pack(side='left', padx=(20, 5))
        self.slider_pos = tk.Scale(ctrl, from_=0, to=100, orient='horizontal', length=300,
                                    bg='#2a2a4e', fg='white', troughcolor='#1a1a3e',
                                    highlightthickness=0, command=self.on_slider_pos, state='disabled')
        self.slider_pos.pack(side='left', padx=5)
        
        self.lbl_position = tk.Label(ctrl, text="0 / 0", fg='white', bg='#1a1a2e',
                                      font=('Consolas', 10))
        self.lbl_position.pack(side='left', padx=5)
        
        # Vitesse
        tk.Label(ctrl, text="  Vitesse:", fg='white', bg='#1a1a2e').pack(side='left', padx=(20, 5))
        self.combo_vitesse = ttk.Combobox(ctrl, values=['0.25x', '0.5x', '1x', '2x', '4x', '10x'], 
                                           width=6, state='readonly')
        self.combo_vitesse.set('1x')
        self.combo_vitesse.pack(side='left', padx=5)
        self.combo_vitesse.bind('<<ComboboxSelected>>', self.on_vitesse_change)
        
        # === Sliders dBm ===
        mid = tk.Frame(self.root, bg='#1a1a2e')
        mid.pack(fill='x', padx=10, pady=5)
        
        # Slider Min
        tk.Label(mid, text="Min (dBm):", fg='#4a90d9', bg='#1a1a2e',
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=5)
        self.slider_min = tk.Scale(mid, from_=-160, to=-60, orient='horizontal', length=150,
                                    bg='#2a2a4e', fg='white', troughcolor='#1a1a3e',
                                    highlightthickness=0, command=self.on_slider_dbm)
        self.slider_min.set(self.dbm_min)
        self.slider_min.pack(side='left', padx=5)
        
        # Slider Max
        tk.Label(mid, text="Max (dBm):", fg='#d94a4a', bg='#1a1a2e',
                 font=('Helvetica', 10, 'bold')).pack(side='left', padx=(20, 5))
        self.slider_max = tk.Scale(mid, from_=-160, to=-60, orient='horizontal', length=150,
                                    bg='#2a2a4e', fg='white', troughcolor='#1a1a3e',
                                    highlightthickness=0, command=self.on_slider_dbm)
        self.slider_max.set(self.dbm_max)
        self.slider_max.pack(side='left', padx=5)
        
        # Stats
        tk.Label(mid, text="│ Min:", fg='#4a90d9', bg='#1a1a2e').pack(side='left', padx=(30, 2))
        self.lbl_min = tk.Label(mid, text="--", fg='white', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_min.pack(side='left')
        
        tk.Label(mid, text="Max:", fg='#d94a4a', bg='#1a1a2e').pack(side='left', padx=(15, 2))
        self.lbl_max = tk.Label(mid, text="--", fg='white', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_max.pack(side='left')
        
        # Timestamp
        tk.Label(mid, text="│ Time:", fg='#888888', bg='#1a1a2e').pack(side='left', padx=(30, 2))
        self.lbl_time = tk.Label(mid, text="--", fg='#ffcc00', bg='#1a1a2e', font=('Consolas', 10))
        self.lbl_time.pack(side='left')
    
    def creer_graphique(self):
        """Crée les graphiques matplotlib."""
        
        # Frame pour le graphique
        frame_graph = tk.Frame(self.root, bg='#1a1a2e')
        frame_graph.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Figure matplotlib
        self.fig, (self.ax_spec, self.ax_wf) = plt.subplots(2, 1, figsize=(12, 6),
                                                             height_ratios=[1, 1.5],
                                                             facecolor='#1a1a2e')
        self.fig.subplots_adjust(hspace=0.15, left=0.08, right=0.95, top=0.95, bottom=0.08)
        
        # === Spectre ===
        self.ax_spec.set_facecolor('#0a0a1a')
        self.ax_spec.tick_params(colors='white', labelsize=8)
        for spine in self.ax_spec.spines.values():
            spine.set_color('#333355')
        
        # Axe fréquence par défaut
        self.axe_freq = np.linspace(0, 1, self.largeur_spectre)
        self.spectre = np.full(self.largeur_spectre, -160.0)
        
        self.ligne_spec, = self.ax_spec.plot(self.axe_freq, self.spectre,
                                              color='#00ff88', linewidth=1)
        self.ax_spec.set_xlim(self.axe_freq[0], self.axe_freq[-1])
        self.ax_spec.set_ylim(self.dbm_min, self.dbm_max)
        self.ax_spec.set_ylabel("dBm", color='white', fontsize=9)
        self.ax_spec.grid(True, alpha=0.2, color='#4444aa')
        
        # Formater axe X pour afficher fréquence centrale complète
        self.ax_spec.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:.6f}'))
        
        # === Waterfall ===
        self.ax_wf.set_facecolor('#0a0a1a')
        self.ax_wf.tick_params(colors='white', labelsize=8)
        for spine in self.ax_wf.spines.values():
            spine.set_color('#333355')
        
        self.im_wf = self.ax_wf.imshow(self.waterfall, aspect='auto', cmap=WF_CMAP,
                                        vmin=self.dbm_min, vmax=self.dbm_max,
                                        extent=[self.axe_freq[0], self.axe_freq[-1], 
                                               PROFONDEUR_WATERFALL, 0])
        self.ax_wf.set_xlabel("Fréquence (MHz)", color='white', fontsize=9)
        self.ax_wf.set_ylabel("Temps", color='white', fontsize=9)
        
        # Formater axe X pour afficher fréquence centrale complète
        self.ax_wf.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:.6f}'))
        
        # Configurer axe Y pour afficher les timestamps
        self.ax_wf.yaxis.set_major_locator(plt.MaxNLocator(6))
        self.ax_wf.yaxis.set_major_formatter(FuncFormatter(self.format_wf_time))
        
        # Canvas Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_graph)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    
    # ========================
    # Gestion fichier
    # ========================
    
    def ouvrir_fichier(self):
        """Ouvre un fichier CSV."""
        
        # Arrêter lecture en cours
        if self.en_lecture:
            self.toggle_lecture()
        
        # Dialogue de sélection
        fichier = filedialog.askopenfilename(
            title="Ouvrir un fichier CSV",
            initialdir="recep_csv",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")]
        )
        
        if not fichier:
            return
        
        self.charger_csv(fichier)
    
    def charger_csv(self, chemin):
        """Charge et parse un fichier CSV."""
        
        try:
            self.donnees = []
            
            with open(chemin, 'r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader)  # Skip header
                
                # Détecter le nombre de colonnes spectre
                nb_cols_data = len(header) - 4  # timestamp, freq, span, ref + data
                if nb_cols_data <= 0:
                    raise ValueError("Format CSV invalide")
                
                self.largeur_spectre = nb_cols_data
                
                for row in reader:
                    if len(row) < 5:
                        continue
                    
                    try:
                        timestamp = row[0]
                        freq = float(row[1])
                        span = float(row[2])
                        ref = float(row[3])
                        spectre = np.array([float(x) for x in row[4:4+nb_cols_data]])
                        
                        self.donnees.append({
                            'timestamp': timestamp,
                            'freq': freq,
                            'span': span,
                            'ref': ref,
                            'spectre': spectre
                        })
                    except (ValueError, IndexError):
                        continue
            
            self.nb_lignes = len(self.donnees)
            
            if self.nb_lignes == 0:
                messagebox.showerror("Erreur", "Aucune donnée valide dans le fichier")
                return
            
            # Mise à jour interface
            self.fichier_charge = chemin
            nom_fichier = os.path.basename(chemin)
            self.lbl_fichier.config(text=nom_fichier, fg='#00ff88')
            self.lbl_info.config(text=f"{self.nb_lignes} lignes | {self.largeur_spectre} points")
            
            # Activer contrôles
            self.activer_controles()
            
            # Reset position
            self.index_courant = 0
            self.slider_pos.config(to=max(1, self.nb_lignes - 1))
            self.slider_pos.set(0)
            
            # Reset waterfall
            self.waterfall = np.full((PROFONDEUR_WATERFALL, self.largeur_spectre), -160.0)
            self.waterfall_times = [''] * PROFONDEUR_WATERFALL
            
            # Mettre à jour axes avec la première ligne
            self.maj_axe_freq()
            
            # Afficher première ligne
            self.afficher_ligne(0)
            
            print(f"[CSV] Chargé: {nom_fichier} ({self.nb_lignes} lignes)")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement:\n{e}")
    
    def activer_controles(self):
        """Active les contrôles après chargement."""
        self.btn_debut.config(state='normal')
        self.btn_reculer.config(state='normal')
        self.btn_play.config(state='normal')
        self.btn_avancer.config(state='normal')
        self.btn_fin.config(state='normal')
        self.slider_pos.config(state='normal')
        self.btn_export.config(state='normal')
    
    def maj_axe_freq(self):
        """Met à jour l'axe des fréquences."""
        if self.nb_lignes == 0:
            return
        
        data = self.donnees[0]
        freq = data['freq']
        span = data['span']
        
        demi_span = span / 2000  # kHz -> MHz / 2
        freq_min = freq - demi_span
        freq_max = freq + demi_span
        
        self.axe_freq = np.linspace(freq_min, freq_max, self.largeur_spectre)
        
        self.ax_spec.set_xlim(freq_min, freq_max)
        self.im_wf.set_extent([freq_min, freq_max, PROFONDEUR_WATERFALL, 0])
        self.ligne_spec.set_xdata(self.axe_freq)
    
    # ========================
    # Affichage
    # ========================
    
    def afficher_ligne(self, index):
        """Affiche une ligne de données."""
        if index < 0 or index >= self.nb_lignes:
            return
        
        self.index_courant = index
        data = self.donnees[index]
        
        spectre = data['spectre']
        timestamp = data['timestamp']
        
        # Mettre à jour spectre
        self.spectre = spectre
        self.ligne_spec.set_ydata(spectre)
        
        # Mettre à jour waterfall (scroll down)
        self.waterfall = np.roll(self.waterfall, 1, axis=0)
        self.waterfall_times = [''] + self.waterfall_times[:-1]  # Scroll timestamps
        self.waterfall_times[0] = timestamp  # Nouveau timestamp en haut
        
        # Redimensionner si nécessaire
        if len(spectre) != self.largeur_spectre:
            spectre_resize = np.interp(
                np.linspace(0, 1, self.largeur_spectre),
                np.linspace(0, 1, len(spectre)),
                spectre
            )
            self.waterfall[0, :] = spectre_resize
        else:
            self.waterfall[0, :] = spectre
        
        self.im_wf.set_data(self.waterfall)
        
        # Stats
        val_min = np.min(spectre)
        val_max = np.max(spectre)
        self.lbl_min.config(text=f"{val_min:.1f}")
        self.lbl_max.config(text=f"{val_max:.1f}")
        self.lbl_time.config(text=timestamp)
        
        # Position
        self.lbl_position.config(text=f"{index + 1} / {self.nb_lignes}")
        
        # Rafraîchir
        self.canvas.draw_idle()
    
    # ========================
    # Contrôles de lecture
    # ========================
    
    def toggle_lecture(self):
        """Démarre ou arrête la lecture."""
        if self.en_lecture:
            self.arreter_lecture()
        else:
            self.demarrer_lecture()
    
    def demarrer_lecture(self):
        """Démarre la lecture automatique."""
        self.en_lecture = True
        self.btn_play.config(text="⏸ Pause", bg='#d94a4a')
        self.lecture_suivante()
    
    def arreter_lecture(self):
        """Arrête la lecture automatique."""
        self.en_lecture = False
        self.btn_play.config(text="▶ Play", bg='#4a90d9')
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
    
    def lecture_suivante(self):
        """Affiche la ligne suivante pendant la lecture."""
        if not self.en_lecture:
            return
        
        if self.index_courant < self.nb_lignes - 1:
            self.index_courant += 1
            self.afficher_ligne(self.index_courant)
            self.slider_pos.set(self.index_courant)
            
            # Timer pour la prochaine frame
            delai = int(40 / self.vitesse)  # ~25 fps à vitesse 1x
            self.timer_id = self.root.after(delai, self.lecture_suivante)
        else:
            # Fin du fichier
            self.arreter_lecture()
    
    def aller_debut(self):
        """Va au début du fichier."""
        self.afficher_ligne(0)
        self.slider_pos.set(0)
        # Reset waterfall
        self.waterfall = np.full((PROFONDEUR_WATERFALL, self.largeur_spectre), -160.0)
        self.waterfall_times = [''] * PROFONDEUR_WATERFALL
    
    def aller_fin(self):
        """Va à la fin du fichier."""
        self.afficher_ligne(self.nb_lignes - 1)
        self.slider_pos.set(self.nb_lignes - 1)
    
    def avancer_10(self):
        """Avance de 10 lignes."""
        new_idx = min(self.index_courant + 10, self.nb_lignes - 1)
        self.afficher_ligne(new_idx)
        self.slider_pos.set(new_idx)
    
    def reculer_10(self):
        """Recule de 10 lignes."""
        new_idx = max(self.index_courant - 10, 0)
        self.afficher_ligne(new_idx)
        self.slider_pos.set(new_idx)
        # Reset waterfall pour reculer proprement
        self.waterfall = np.full((PROFONDEUR_WATERFALL, self.largeur_spectre), -160.0)
        self.waterfall_times = [''] * PROFONDEUR_WATERFALL
    
    # ========================
    # Callbacks
    # ========================
    
    def format_wf_time(self, y, pos):
        """Formate l'axe Y du waterfall avec les timestamps."""
        idx = int(y)
        if 0 <= idx < len(self.waterfall_times) and self.waterfall_times[idx]:
            # Extraire juste HH:MM:SS.mmm du timestamp
            ts = self.waterfall_times[idx]
            # Format attendu: HH:MM:SS.ffffff ou similaire
            if len(ts) >= 8:
                return ts[-12:]  # Retourne les derniers caractères (temps)
            return ts
        return ''
    
    def on_slider_pos(self, val):
        """Callback changement position."""
        if self.nb_lignes == 0:
            return
        
        idx = int(float(val))
        if idx != self.index_courant:
            # Reset waterfall quand on saute
            self.waterfall = np.full((PROFONDEUR_WATERFALL, self.largeur_spectre), -160.0)
            self.waterfall_times = [''] * PROFONDEUR_WATERFALL
            self.afficher_ligne(idx)
    
    def on_slider_dbm(self, val):
        """Callback changement sliders dBm."""
        self.dbm_min = self.slider_min.get()
        self.dbm_max = self.slider_max.get()
        
        if self.dbm_min >= self.dbm_max:
            self.dbm_max = self.dbm_min + 10
            self.slider_max.set(self.dbm_max)
        
        self.ax_spec.set_ylim(self.dbm_min, self.dbm_max)
        self.im_wf.set_clim(self.dbm_min, self.dbm_max)
        self.canvas.draw_idle()
    
    def on_vitesse_change(self, event):
        """Callback changement vitesse."""
        txt = self.combo_vitesse.get()
        self.vitesse = float(txt.replace('x', ''))
    
    def exporter_waterfall(self):
        """Exporte le graphique waterfall COMPLET (toutes les lignes du CSV) en image PNG."""
        if self.nb_lignes == 0:
            messagebox.showwarning("Export", "Aucune donnée à exporter")
            return
        
        # Générer nom de fichier par défaut
        if self.fichier_charge:
            base_name = os.path.splitext(os.path.basename(self.fichier_charge))[0]
        else:
            base_name = "waterfall"
        
        ts = datetime.now().strftime('%H%M%S')
        default_name = f"{base_name}_export_{ts}.png"
        
        # Dialogue de sauvegarde
        fichier = filedialog.asksaveasfilename(
            title="Exporter le waterfall",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("PDF", "*.pdf"), ("Tous les fichiers", "*.*")]
        )
        
        if not fichier:
            return
        
        try:
            # Construire le waterfall COMPLET avec TOUTES les lignes du CSV
            waterfall_complet = np.zeros((self.nb_lignes, self.largeur_spectre))
            
            for i, data in enumerate(self.donnees):
                spectre = data['spectre']
                if len(spectre) != self.largeur_spectre:
                    spectre = np.interp(
                        np.linspace(0, 1, self.largeur_spectre),
                        np.linspace(0, 1, len(spectre)),
                        spectre
                    )
                waterfall_complet[i, :] = spectre
            
            # Récupérer les infos de fréquence
            data_first = self.donnees[0]
            data_last = self.donnees[-1]
            freq = data_first['freq']
            span = data_first['span']
            timestamp_debut = data_first['timestamp']
            timestamp_fin = data_last['timestamp']
            
            # Calculer la hauteur de la figure proportionnelle au nombre de lignes
            # Min 8, max 20 pouces de hauteur
            hauteur = min(20, max(8, self.nb_lignes / 30))
            
            # Créer une figure séparée pour l'export
            fig_export, ax_export = plt.subplots(figsize=(14, hauteur), facecolor='#1a1a2e')
            ax_export.set_facecolor('#0a0a1a')
            
            # Dessiner le waterfall COMPLET 
            # origin='lower' + extent inversé: ligne 0 (début) en bas, dernière ligne en haut
            im = ax_export.imshow(waterfall_complet, aspect='auto', cmap=WF_CMAP,
                                   vmin=self.dbm_min, vmax=self.dbm_max,
                                   extent=[self.axe_freq[0], self.axe_freq[-1], 
                                          0, self.nb_lignes],
                                   origin='lower')
            
            # Colorbar
            cbar = fig_export.colorbar(im, ax=ax_export, label='dBm')
            cbar.ax.yaxis.label.set_color('white')
            cbar.ax.tick_params(colors='white')
            
            # Labels et titre
            ax_export.set_xlabel('Fréquence (MHz)', color='white', fontsize=11)
            ax_export.set_ylabel(f'Temps ({self.nb_lignes} lignes)', color='white', fontsize=11)
            ax_export.set_title(f'Waterfall COMPLET - {freq:.6f} MHz\n{timestamp_debut} → {timestamp_fin}', 
                               color='white', fontsize=12)
            ax_export.tick_params(colors='white')
            ax_export.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:.6f}'))
            
            # Sauvegarder
            fig_export.savefig(fichier, dpi=150, facecolor='#1a1a2e', edgecolor='none',
                               bbox_inches='tight')
            plt.close(fig_export)
            
            messagebox.showinfo("Export", f"Waterfall COMPLET exporté ({self.nb_lignes} lignes):\n{fichier}")
            print(f"[EXPORT] Waterfall complet sauvegardé: {fichier} ({self.nb_lignes} lignes)")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export:\n{e}")


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = CSVReader(root)
    root.mainloop()
