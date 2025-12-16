#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Interface Tkinter
============================================
Interface graphique avec boutons pour contrôler
la connexion et l'affichage du spectre.

Auteur: Étudiant PTUT
Date: Décembre 2025
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
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
        self.root.geometry("400x300")
        self.root.configure(bg='#1a1a2e')
        
        # Variables d'état
        self.connexion = None
        self.connecte = False
        self.affichage_actif = False
        self.freq_centrale = FREQUENCE_DEFAUT
        self.thread_affichage = None
        
        # Créer l'interface
        self.creer_interface()
    
    def creer_interface(self):
        """Crée les widgets de l'interface."""
        
        # === Titre ===
        titre = tk.Label(
            self.root,
            text="IC-705 Spectrum Display",
            font=("Helvetica", 18, "bold"),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        titre.pack(pady=20)
        
        # === Frame pour les paramètres de connexion ===
        frame_connexion = tk.Frame(self.root, bg='#1a1a2e')
        frame_connexion.pack(pady=10)
        
        # IP
        tk.Label(frame_connexion, text="IP:", fg='white', bg='#1a1a2e').grid(row=0, column=0, padx=5)
        self.entry_ip = tk.Entry(frame_connexion, width=15)
        self.entry_ip.insert(0, SERVEUR_IP)
        self.entry_ip.grid(row=0, column=1, padx=5)
        
        # Port
        tk.Label(frame_connexion, text="Port:", fg='white', bg='#1a1a2e').grid(row=0, column=2, padx=5)
        self.entry_port = tk.Entry(frame_connexion, width=8)
        self.entry_port.insert(0, str(SERVEUR_PORT))
        self.entry_port.grid(row=0, column=3, padx=5)
        
        # === Status ===
        self.label_status = tk.Label(
            self.root,
            text="⚪ Non connecté",
            font=("Helvetica", 12),
            fg='#ff6666',
            bg='#1a1a2e'
        )
        self.label_status.pack(pady=15)
        
        # === Fréquence ===
        self.label_freq = tk.Label(
            self.root,
            text="Fréquence: ---",
            font=("Helvetica", 11),
            fg='#aaaaaa',
            bg='#1a1a2e'
        )
        self.label_freq.pack(pady=5)
        
        # === Frame pour les boutons ===
        frame_boutons = tk.Frame(self.root, bg='#1a1a2e')
        frame_boutons.pack(pady=20)
        
        # Bouton Connecter
        self.btn_connecter = tk.Button(
            frame_boutons,
            text="🔌 Connecter",
            font=("Helvetica", 12),
            width=15,
            bg='#2a4a6e',
            fg='white',
            activebackground='#3a5a8e',
            command=self.toggle_connexion
        )
        self.btn_connecter.grid(row=0, column=0, padx=10)
        
        # Bouton Afficher
        self.btn_afficher = tk.Button(
            frame_boutons,
            text="📊 Afficher Spectre",
            font=("Helvetica", 12),
            width=15,
            bg='#4a4a4a',
            fg='#888888',
            state='disabled',
            command=self.toggle_affichage
        )
        self.btn_afficher.grid(row=0, column=1, padx=10)
        
        # === Bouton Quitter ===
        btn_quitter = tk.Button(
            self.root,
            text="Quitter",
            font=("Helvetica", 10),
            bg='#6e2a2a',
            fg='white',
            command=self.quitter
        )
        btn_quitter.pack(pady=10)
        
        # Gestion de la fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.quitter)
    
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
                        break
            except:
                pass
            
            # Mise à jour interface
            self.connecte = True
            self.label_status.config(text="🟢 Connecté", fg='#00ff88')
            self.label_freq.config(text=f"Fréquence: {self.freq_centrale:.3f} MHz")
            self.btn_connecter.config(text="🔌 Déconnecter", bg='#6e4a2a')
            self.btn_afficher.config(state='normal', bg='#2a6e4a', fg='white')
            
        except Exception as e:
            messagebox.showerror("Erreur de connexion", f"Impossible de se connecter:\n{e}")
            if self.connexion:
                self.connexion.close()
                self.connexion = None
    
    def deconnecter(self):
        """Déconnecte du serveur."""
        # Arrêter l'affichage d'abord
        if self.affichage_actif:
            self.arreter_affichage()
        
        if self.connexion:
            try:
                # Désactiver le streaming
                cmd = bytes([0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x00, 0xFD])
                self.connexion.send(cmd)
                time.sleep(0.1)
                self.connexion.close()
            except:
                pass
            self.connexion = None
        
        self.connecte = False
        self.label_status.config(text="⚪ Non connecté", fg='#ff6666')
        self.label_freq.config(text="Fréquence: ---")
        self.btn_connecter.config(text="🔌 Connecter", bg='#2a4a6e')
        self.btn_afficher.config(state='disabled', bg='#4a4a4a', fg='#888888')
    
    def toggle_affichage(self):
        """Lance ou arrête l'affichage."""
        if not self.affichage_actif:
            self.lancer_affichage()
        else:
            self.arreter_affichage()
    
    def lancer_affichage(self):
        """Lance l'affichage du spectre dans une nouvelle fenêtre."""
        self.affichage_actif = True
        self.btn_afficher.config(text="⏹ Arrêter", bg='#6e2a2a')
        
        # Lancer dans un thread séparé
        self.thread_affichage = threading.Thread(target=self.boucle_affichage, daemon=True)
        self.thread_affichage.start()
    
    def arreter_affichage(self):
        """Arrête l'affichage."""
        self.affichage_actif = False
        self.btn_afficher.config(text="📊 Afficher Spectre", bg='#2a6e4a')
        plt.close('all')
    
    def boucle_affichage(self):
        """Boucle d'affichage du spectre (exécutée dans un thread)."""
        
        # Calculer l'axe des fréquences
        demi_span = SPAN_KHZ / 2000
        freq_min = self.freq_centrale - demi_span
        freq_max = self.freq_centrale + demi_span
        axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
        
        # Créer la figure matplotlib
        fig, (ax_spectre, ax_waterfall) = plt.subplots(2, 1, figsize=(10, 6))
        fig.patch.set_facecolor('#1a1a2e')
        ax_spectre.set_facecolor('#0a0a1a')
        ax_waterfall.set_facecolor('#0a0a1a')
        
        # Configurer le spectre
        ax_spectre.set_title(f'Spectre IC-705 - {self.freq_centrale:.3f} MHz', color='white')
        ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
        ax_spectre.set_ylabel('Amplitude', color='white')
        ax_spectre.set_xlim(freq_min, freq_max)
        ax_spectre.set_ylim(0, 200)
        ax_spectre.tick_params(colors='white')
        ax_spectre.grid(True, alpha=0.3)
        ax_spectre.axvline(x=self.freq_centrale, color='red', linestyle='--', alpha=0.7)
        ligne, = ax_spectre.plot(axe_freq, np.zeros(LARGEUR_SPECTRE), color='yellow', linewidth=1)
        
        # Configurer le waterfall
        ax_waterfall.set_xlabel('Fréquence (MHz)', color='white')
        ax_waterfall.set_ylabel('Temps', color='white')
        ax_waterfall.tick_params(colors='white')
        
        waterfall_data = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
        image = ax_waterfall.imshow(
            waterfall_data, aspect='auto', cmap='viridis',
            vmin=0, vmax=200, origin='upper',
            extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
        )
        
        plt.tight_layout()
        plt.ion()
        plt.show()
        
        # Buffer de réception
        buffer = bytearray()
        self.connexion.settimeout(0.1)
        
        # Boucle principale
        while self.affichage_actif and plt.fignum_exists(fig.number):
            try:
                data = self.connexion.recv(4096)
                buffer.extend(data)
            except socket.timeout:
                pass
            except:
                break
            
            # Parser les messages
            messages = trouver_messages_civ(buffer)
            
            for msg in messages:
                if len(msg) >= 5 and msg[4] == 0x27 and len(msg) > 50:
                    amplitudes = extraire_donnees_spectre(msg)
                    if amplitudes is not None:
                        spectre = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        
                        # Scroll waterfall
                        waterfall_data[1:] = waterfall_data[:-1]
                        waterfall_data[0] = spectre
                        
                        # Mettre à jour
                        ligne.set_ydata(spectre)
                        image.set_data(waterfall_data)
                        
                        plt.draw()
                        plt.pause(0.001)
            
            if len(buffer) > 10000:
                buffer.clear()
        
        # Fermer proprement
        self.affichage_actif = False
        self.root.after(0, lambda: self.btn_afficher.config(text="📊 Afficher Spectre", bg='#2a6e4a'))
    
    def quitter(self):
        """Ferme l'application proprement."""
        self.arreter_affichage()
        self.deconnecter()
        self.root.destroy()


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == '__main__':
    root = tk.Tk()
    app = IC705App(root)
    root.mainloop()
