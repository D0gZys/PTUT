#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Interface Tkinter (Corrigée)
======================================================
Interface graphique avec graphique intégré dans Tkinter.
Le graphique matplotlib est dans la même fenêtre (pas de thread GUI).

Auteur: Étudiant PTUT
Date: Décembre 2025
"""

import tkinter as tk
from tkinter import messagebox
import socket
import time
import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # Backend Tkinter AVANT import pyplot
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading

# ============================================================
#                    PARAMÈTRES DE CONFIGURATION
# ============================================================

SERVEUR_IP = '127.0.0.1'
SERVEUR_PORT = 50002
LARGEUR_SPECTRE = 200
PROFONDEUR_WATERFALL = 100
SPAN_KHZ = 50
FREQUENCE_DEFAUT = 145.000

ADRESSE_RADIO = 0xA4
ADRESSE_PC = 0xE0


# ============================================================
#              FONCTIONS CI-V (Communication avec la radio)
# ============================================================

def decoder_frequence_bcd(octets_frequence):
    """Décode une fréquence BCD little-endian en MHz."""
    frequence_hz = 0
    multiplicateur = 1
    for octet in octets_frequence:
        chiffre_bas = octet & 0x0F
        frequence_hz += chiffre_bas * multiplicateur
        multiplicateur *= 10
        chiffre_haut = (octet >> 4) & 0x0F
        frequence_hz += chiffre_haut * multiplicateur
        multiplicateur *= 10
    return frequence_hz / 1_000_000


def trouver_messages_civ(buffer):
    """Trouve et extrait les messages CI-V complets."""
    messages = []
    while True:
        try:
            debut = buffer.index(0xFE)
        except ValueError:
            break
        if debut > 0:
            del buffer[:debut]
        if len(buffer) < 2:
            break
        if buffer[1] != 0xFE:
            del buffer[:1]
            continue
        try:
            fin = buffer.index(0xFD, 2) + 1
        except ValueError:
            break
        messages.append(bytes(buffer[:fin]))
        del buffer[:fin]
    return messages


def extraire_donnees_spectre(message):
    """Extrait les données d'amplitude d'un message de spectre."""
    if len(message) < 50:
        return None
    donnees = message[19:-1]
    if len(donnees) < 10:
        return None
    return np.array(list(donnees), dtype=float)


def redimensionner_spectre(amplitudes, taille):
    """Redimensionne le spectre à la taille voulue."""
    n = len(amplitudes)
    if n >= taille:
        indices = np.linspace(0, n - 1, taille, dtype=int)
        return amplitudes[indices]
    else:
        resultat = np.zeros(taille)
        resultat[:n] = amplitudes
        return resultat


# ============================================================
#              CLASSE PRINCIPALE - APPLICATION TKINTER
# ============================================================

class IC705App:
    """Application principale avec interface Tkinter."""
    
    def __init__(self, root):
        """Initialise l'application."""
        self.root = root
        self.root.title("IC-705 Spectrum Display")
        self.root.geometry("950x750")
        self.root.configure(bg='#1a1a2e')
        
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
        
        # Paramètres de gain
        self.gain_min = 20
        self.gain_max = 120
        
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
            text="IC-705 Spectrum Display",
            font=("Helvetica", 16, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre.pack(side='left', padx=10)
        
        # Frame connexion
        frame_conn = tk.Frame(frame_controles, bg='#1a1a2e')
        frame_conn.pack(side='left', padx=20)
        
        tk.Label(frame_conn, text="IP:", fg='white', bg='#1a1a2e').pack(side='left')
        self.entry_ip = tk.Entry(frame_conn, width=12)
        self.entry_ip.insert(0, SERVEUR_IP)
        self.entry_ip.pack(side='left', padx=5)
        
        tk.Label(frame_conn, text="Port:", fg='white', bg='#1a1a2e').pack(side='left')
        self.entry_port = tk.Entry(frame_conn, width=6)
        self.entry_port.insert(0, str(SERVEUR_PORT))
        self.entry_port.pack(side='left', padx=5)
        
        # Boutons
        self.btn_connecter = tk.Button(
            frame_controles,
            text="🔌 Connecter",
            font=("Helvetica", 11),
            width=12,
            bg='#2a4a6e',
            fg='white',
            command=self.toggle_connexion
        )
        self.btn_connecter.pack(side='left', padx=10)
        
        self.btn_afficher = tk.Button(
            frame_controles,
            text="▶ Démarrer",
            font=("Helvetica", 11),
            width=12,
            bg='#4a4a4a',
            fg='#888888',
            state='disabled',
            command=self.toggle_affichage
        )
        self.btn_afficher.pack(side='left', padx=10)
        
        # Status
        self.label_status = tk.Label(
            frame_controles,
            text="⚪ Non connecté",
            font=("Helvetica", 11),
            fg='#ff6666',
            bg='#1a1a2e'
        )
        self.label_status.pack(side='right', padx=10)
        
        # Fréquence
        self.label_freq = tk.Label(
            frame_controles,
            text="---",
            font=("Helvetica", 11),
            fg='#aaaaaa',
            bg='#1a1a2e'
        )
        self.label_freq.pack(side='right', padx=10)
        
        # Gestion de la fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)
        
        # === Frame pour les sliders de gain ===
        frame_sliders = tk.Frame(self.root, bg='#1a1a2e')
        frame_sliders.pack(fill='x', padx=10, pady=5)
        
        # Slider Gain Min
        tk.Label(frame_sliders, text="Gain Min:", fg='#4a90d9', bg='#1a1a2e', 
                 font=('Helvetica', 10)).pack(side='left', padx=5)
        self.slider_min = tk.Scale(
            frame_sliders,
            from_=0, to=150,
            orient='horizontal',
            length=200,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            command=self.on_slider_change
        )
        self.slider_min.set(self.gain_min)
        self.slider_min.pack(side='left', padx=10)
        
        # Slider Gain Max
        tk.Label(frame_sliders, text="Gain Max:", fg='#d94a4a', bg='#1a1a2e',
                 font=('Helvetica', 10)).pack(side='left', padx=5)
        self.slider_max = tk.Scale(
            frame_sliders,
            from_=50, to=255,
            orient='horizontal',
            length=200,
            bg='#2a2a4e',
            fg='white',
            troughcolor='#1a1a3e',
            highlightthickness=0,
            command=self.on_slider_change
        )
        self.slider_max.set(self.gain_max)
        self.slider_max.pack(side='left', padx=10)
        
        # Label affichant les valeurs
        self.label_gain = tk.Label(
            frame_sliders,
            text=f"[{self.gain_min} - {self.gain_max}]",
            fg='#aaaaaa',
            bg='#1a1a2e',
            font=('Helvetica', 10)
        )
        self.label_gain.pack(side='left', padx=20)
    
    def on_slider_change(self, value):
        """Appelé quand un slider change."""
        self.gain_min = self.slider_min.get()
        self.gain_max = self.slider_max.get()
        
        # S'assurer que min < max
        if self.gain_min >= self.gain_max:
            self.gain_min = self.gain_max - 10
            self.slider_min.set(self.gain_min)
        
        # Mettre à jour le label
        self.label_gain.config(text=f"[{self.gain_min} - {self.gain_max}]")
        
        # Mettre à jour les graphiques
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
        
        # Créer la figure matplotlib (PAS plt.figure, mais Figure directement)
        self.fig = Figure(figsize=(10, 6), facecolor='#1a1a2e')
        
        # Spectre
        self.ax_spectre = self.fig.add_subplot(211)
        self.ax_spectre.set_facecolor('#0a0a1a')
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
        self.ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_spectre.set_ylabel('Amplitude', color='white')
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_ylim(self.gain_min, self.gain_max)
        self.ax_spectre.tick_params(colors='white')
        self.ax_spectre.grid(True, alpha=0.3)
        self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7)
        self.ligne, = self.ax_spectre.plot(self.axe_freq, self.spectre_actuel, color='yellow', linewidth=1)
        
        # Waterfall
        self.ax_waterfall = self.fig.add_subplot(212)
        self.ax_waterfall.set_facecolor('#0a0a1a')
        self.ax_waterfall.set_xlabel('Fréquence (MHz)', color='white')
        self.ax_waterfall.set_ylabel('Temps', color='white')
        self.ax_waterfall.tick_params(colors='white')
        
        self.image = self.ax_waterfall.imshow(
            self.waterfall_data,
            aspect='auto',
            cmap='viridis',
            vmin=self.gain_min, vmax=self.gain_max,
            origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        
        self.fig.tight_layout()
        
        # Intégrer dans Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
    
    def mettre_a_jour_axe_freq(self):
        """Met à jour l'axe des fréquences quand la fréquence centrale change."""
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        self.axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Effacer et recréer la ligne centrale
        for line in self.ax_spectre.lines[1:]:  # Garder la ligne du spectre
            line.remove()
        self.ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7)
        
        self.ax_spectre.set_xlim(freq_min, freq_max)
        self.ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
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
            time.sleep(0.3)
            
            # Demander la fréquence
            cmd = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x03, 0xFD])
            self.connexion.send(cmd)
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
            self.btn_connecter.config(text="🔌 Déconnecter", bg='#6e4a2a')
            self.btn_afficher.config(state='normal', bg='#2a6e4a', fg='white')
            
        except Exception as e:
            messagebox.showerror("Erreur de connexion", f"Impossible de se connecter:\n{e}")
            if self.connexion:
                self.connexion.close()
                self.connexion = None
    
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
        self.btn_connecter.config(text="🔌 Connecter", bg='#2a4a6e')
        self.btn_afficher.config(state='disabled', bg='#4a4a4a', fg='#888888')
    
    def toggle_affichage(self):
        """Lance ou arrête l'affichage."""
        if not self.affichage_actif:
            self.lancer_affichage()
        else:
            self.arreter_affichage()
    
    def lancer_affichage(self):
        """Lance la réception et l'affichage."""
        self.affichage_actif = True
        self.btn_afficher.config(text="⏹ Arrêter", bg='#6e2a2a')
        
        # Lancer la réception dans un thread (données seulement, pas de GUI)
        self.thread_reception = threading.Thread(target=self.boucle_reception, daemon=True)
        self.thread_reception.start()
        
        # Lancer la mise à jour de l'affichage dans le thread principal
        self.mettre_a_jour_affichage()
    
    def arreter_affichage(self):
        """Arrête l'affichage."""
        self.affichage_actif = False
        self.btn_afficher.config(text="▶ Démarrer", bg='#2a6e4a')
    
    def boucle_reception(self):
        """Boucle de réception des données (thread secondaire - PAS de GUI ici)."""
        buffer = bytearray()
        self.connexion.settimeout(0.1)
        
        while self.affichage_actif and self.connecte:
            try:
                data = self.connexion.recv(4096)
                buffer.extend(data)
            except socket.timeout:
                continue
            except:
                break
            
            messages = trouver_messages_civ(buffer)
            
            for msg in messages:
                if len(msg) >= 5 and msg[4] == 0x27 and len(msg) > 50:
                    amplitudes = extraire_donnees_spectre(msg)
                    if amplitudes is not None:
                        spectre = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        
                        # Mettre à jour les données (thread-safe via variables)
                        self.spectre_actuel = spectre
                        self.waterfall_data[1:] = self.waterfall_data[:-1]
                        self.waterfall_data[0] = spectre
                        self.nouvelles_donnees = True
            
            if len(buffer) > 10000:
                buffer.clear()
    
    def mettre_a_jour_affichage(self):
        """Met à jour l'affichage (appelé dans le thread principal via after)."""
        if not self.affichage_actif:
            return
        
        if self.nouvelles_donnees:
            # Mettre à jour les données graphiques
            self.ligne.set_data(self.axe_freq, self.spectre_actuel)
            self.image.set_data(self.waterfall_data)
            
            # Redessiner le canvas (thread-safe car dans le thread principal)
            self.canvas.draw_idle()
            self.nouvelles_donnees = False
        
        # Planifier la prochaine mise à jour (30ms = ~33 FPS)
        self.root.after(30, self.mettre_a_jour_affichage)
    
    def quitter(self):
        """Ferme l'application proprement."""
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
