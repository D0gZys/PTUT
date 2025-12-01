#!/usr/bin/env python3
"""
Contrôle IC-705 via CI-V - Affichage du spectre en temps réel
Active le streaming et affiche le spectre avec matplotlib
"""

import socket
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# Configuration
HOST = '127.0.0.1'  
PORT = 50002
SPAN_KHZ = 50  # Largeur du span en kHz (à ajuster selon votre config IC-705)

# Variables globales
spectrum_data = np.zeros(475)  # 475 points de données spectrales
center_freq_mhz = 143.050  # Fréquence centrale par défaut
waterfall_history = deque(maxlen=100)  # Historique pour waterfall
socket_conn = None
running = True

def decode_bcd_frequency(freq_bytes):
    """Décode la fréquence en format BCD little-endian"""
    try:
        # Inverser les bytes et convertir en chaîne BCD
        freq_bcd = ''.join([f"{b:02x}" for b in reversed(freq_bytes)])
        # Convertir en MHz
        freq_hz = int(freq_bcd)
        return freq_hz / 1000000.0
    except:
        return None

def parse_spectrum_frame(data):
    """Parse une trame de spectre CI-V"""
    global spectrum_data, center_freq_mhz
    
    # Vérifier que c'est une trame de spectre (commande 0x27)
    if len(data) < 50 or data[4] != 0x27:
        return False
    
    # Les trames longues (>100 bytes) contiennent les données spectrales
    if len(data) > 100:
        # Extraire la fréquence centrale (bytes 9-14, 6 bytes BCD)
        freq_bytes = data[9:15]
        freq = decode_bcd_frequency(freq_bytes)
        if freq:
            center_freq_mhz = freq
        
        # Extraire les données d'amplitude (à partir du byte 20)
        # Le nombre exact peut varier, on prend ce qui est disponible
        amp_start = 20
        amp_data = data[amp_start:-1]  # Exclure le 0xFD final
        
        if len(amp_data) > 0:
            # Redimensionner si nécessaire
            if len(amp_data) >= 475:
                spectrum_data = np.array(list(amp_data[:475]))
            else:
                spectrum_data[:len(amp_data)] = list(amp_data)
            return True
    
    return False

def read_civ_message(sock):
    """Lit un message CI-V complet"""
    response = bytearray()
    sock.settimeout(0.1)
    
    try:
        while True:
            byte = sock.recv(1)
            if not byte:
                break
            response.extend(byte)
            if byte[0] == 0xFD:
                break
    except socket.timeout:
        pass
    except Exception:
        pass
    
    return response

def update_plot(frame):
    """Mise à jour de l'affichage"""
    global spectrum_data, center_freq_mhz, waterfall_history, socket_conn, running
    
    if not running or socket_conn is None:
        return line, waterfall_img
    
    # Lire plusieurs messages pour trouver des données spectrales
    for _ in range(10):
        data = read_civ_message(socket_conn)
        if len(data) > 0:
            if parse_spectrum_frame(data):
                break
    
    # Mettre à jour le graphique du spectre
    freq_axis = np.linspace(
        center_freq_mhz - SPAN_KHZ/2000,
        center_freq_mhz + SPAN_KHZ/2000,
        len(spectrum_data)
    )
    line.set_data(freq_axis, spectrum_data)
    ax1.set_xlim(freq_axis[0], freq_axis[-1])
    ax1.set_title(f'Spectre IC-705 - {center_freq_mhz:.6f} MHz')
    
    # Ajouter au waterfall
    waterfall_history.append(spectrum_data.copy())
    
    # Mettre à jour le waterfall
    if len(waterfall_history) > 1:
        waterfall_array = np.array(list(waterfall_history))
        waterfall_img.set_data(waterfall_array)
        waterfall_img.set_extent([freq_axis[0], freq_axis[-1], len(waterfall_history), 0])
        waterfall_img.set_clim(0, 255)
    
    return line, waterfall_img

def on_close(event):
    """Gestion de la fermeture de la fenêtre"""
    global running, socket_conn
    running = False
    
    if socket_conn:
        try:
            # Désactiver le streaming
            cmd_off = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x00, 0xFD])
            socket_conn.send(cmd_off)
            time.sleep(0.2)
            socket_conn.close()
        except:
            pass
    
    print("\n✅ Streaming désactivé, connexion fermée.")

# ============== PROGRAMME PRINCIPAL ==============

print("="*60)
print("IC-705 Spectrum Display via CI-V")
print("="*60)
print(f"Connexion: {HOST}:{PORT}\n")

try:
    socket_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_conn.settimeout(5)
    socket_conn.connect((HOST, PORT))
    print("✅ Connecté au serveur CI-V\n")

    # Activer le streaming spectral
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x01, 0xFD])
    print(f"→ Activation du streaming spectral...")
    socket_conn.send(cmd)
    time.sleep(0.5)
    
    # Lire et ignorer la réponse initiale
    for _ in range(5):
        read_civ_message(socket_conn)
    
    print("✅ Streaming activé\n")
    print("Affichage du spectre en temps réel...")
    print("Fermez la fenêtre pour arrêter.\n")
    
    # Créer la figure matplotlib
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                    gridspec_kw={'height_ratios': [1, 2]})
    fig.canvas.mpl_connect('close_event', on_close)
    
    # Graphique du spectre (en haut)
    freq_axis = np.linspace(
        center_freq_mhz - SPAN_KHZ/2000,
        center_freq_mhz + SPAN_KHZ/2000,
        len(spectrum_data)
    )
    line, = ax1.plot(freq_axis, spectrum_data, 'c-', linewidth=0.8)
    ax1.set_xlim(freq_axis[0], freq_axis[-1])
    ax1.set_ylim(0, 260)
    ax1.set_xlabel('Fréquence (MHz)')
    ax1.set_ylabel('Amplitude')
    ax1.set_title(f'Spectre IC-705 - {center_freq_mhz:.6f} MHz')
    ax1.grid(True, alpha=0.3)
    ax1.set_facecolor('#1a1a2e')
    
    # Waterfall (en bas)
    waterfall_init = np.zeros((100, len(spectrum_data)))
    waterfall_img = ax2.imshow(waterfall_init, aspect='auto', cmap='viridis',
                               extent=[freq_axis[0], freq_axis[-1], 100, 0],
                               vmin=0, vmax=255)
    ax2.set_xlabel('Fréquence (MHz)')
    ax2.set_ylabel('Temps (trames)')
    ax2.set_title('Waterfall')
    
    # Barre de couleur
    plt.colorbar(waterfall_img, ax=ax2, label='Amplitude')
    
    plt.tight_layout()
    
    # Animation
    ani = FuncAnimation(fig, update_plot, interval=50, blit=False, cache_frame_data=False)
    
    plt.show()

except Exception as e:
    print(f"❌ Erreur: {e}")
    if socket_conn:
        socket_conn.close()
