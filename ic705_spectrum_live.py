#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Version Temps Réel
Logique simple: Recevoir → Afficher → Recevoir → Afficher
"""

import socket
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.widgets import TextBox, Button
from matplotlib.colors import LinearSegmentedColormap
from collections import deque

# ============== COLORMAP STYLE WFVIEW ==============
# Créer une colormap similaire à wfview: bleu foncé → bleu → cyan → jaune → orange
wfview_colors = [
    (0.0, 0.0, 0.2),      # Bleu très foncé (bruit)
    (0.0, 0.0, 0.5),      # Bleu foncé
    (0.0, 0.2, 0.8),      # Bleu
    (0.0, 0.5, 1.0),      # Bleu clair
    (0.0, 0.8, 1.0),      # Cyan
    (0.2, 1.0, 0.8),      # Cyan-vert
    (0.5, 1.0, 0.5),      # Vert clair
    (0.8, 1.0, 0.2),      # Jaune-vert
    (1.0, 1.0, 0.0),      # Jaune
    (1.0, 0.8, 0.0),      # Orange
    (1.0, 0.5, 0.0),      # Orange foncé
]
wfview_cmap = LinearSegmentedColormap.from_list('wfview', wfview_colors, N=256)

# ============== CONFIGURATION ==============
HOST = '127.0.0.1'
PORT = 50002
SPAN_KHZ = 50  # Largeur du span en kHz
NUM_POINTS = 200  # Nombre de points à afficher
WATERFALL_DEPTH = 150  # Profondeur du waterfall (comme wfview)

# ============== VARIABLES GLOBALES ==============
center_freq_mhz = 143.050
waterfall_history = deque(maxlen=WATERFALL_DEPTH)

# ============== FONCTIONS ==============

def decode_bcd_frequency(freq_bytes):
    """Décode la fréquence BCD little-endian"""
    try:
        reversed_bytes = list(reversed(freq_bytes))
        freq_str = ''
        for byte in reversed_bytes:
            high_digit = (byte >> 4) & 0x0F
            low_digit = byte & 0x0F
            freq_str += f"{high_digit}{low_digit}"
        return int(freq_str) / 1000000.0
    except:
        return None

def read_one_message(sock):
    """Lit UN SEUL message CI-V complet"""
    response = bytearray()
    
    try:
        # Attendre le début du message (FE FE)
        while True:
            byte = sock.recv(1)
            if not byte:
                return None
            if byte[0] == 0xFE:
                response.append(byte[0])
                byte2 = sock.recv(1)
                if byte2 and byte2[0] == 0xFE:
                    response.append(byte2[0])
                    break
        
        # Lire jusqu'à FD
        while True:
            byte = sock.recv(1)
            if not byte:
                break
            response.append(byte[0])
            if byte[0] == 0xFD:
                break
                
    except socket.timeout:
        return None
    except Exception:
        return None
    
    return response

def get_frequency_fast(sock):
    """Récupère la fréquence rapidement"""
    global center_freq_mhz
    
    sock.settimeout(0.5)  # Timeout court
    
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
    sock.send(cmd)
    
    # Lire quelques messages rapidement
    for _ in range(5):
        msg = read_one_message(sock)
        if msg and len(msg) == 11 and msg[4] == 0x03:
            freq = decode_bcd_frequency(msg[5:10])
            if freq and freq > 0:
                center_freq_mhz = freq
                return freq
    return center_freq_mhz

def request_frequency(sock):
    """Envoie une demande de fréquence (non bloquante)"""
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
    try:
        sock.send(cmd)
    except:
        pass

def encode_bcd_frequency(freq_mhz):
    """Encode une fréquence en BCD little-endian (5 bytes)"""
    # Convertir MHz en Hz
    freq_hz = int(freq_mhz * 1000000)
    # Formater en 10 chiffres
    freq_str = f"{freq_hz:010d}"
    
    # Convertir en BCD (2 chiffres par byte, little-endian)
    bcd_bytes = []
    for i in range(4, -1, -1):  # 5 bytes, du poids faible au poids fort
        idx = i * 2
        high = int(freq_str[idx])
        low = int(freq_str[idx + 1])
        bcd_bytes.append((high << 4) | low)
    
    return bytes(bcd_bytes)

def set_frequency(sock, freq_mhz):
    """Envoie une commande pour changer la fréquence de l'IC-705"""
    global center_freq_mhz
    
    try:
        freq_bcd = encode_bcd_frequency(freq_mhz)
        # Commande CI-V: FE FE A4 E0 05 [5 bytes BCD] FD
        cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x05]) + freq_bcd + bytes([0xFD])
        sock.send(cmd)
        center_freq_mhz = freq_mhz
        print(f"→ Fréquence changée: {freq_mhz:.6f} MHz")
        return True
    except Exception as e:
        print(f"Erreur changement fréquence: {e}")
        return False

def check_frequency_response(msg):
    """Vérifie si un message contient une réponse de fréquence et la décode"""
    global center_freq_mhz
    
    if msg and len(msg) == 11 and msg[4] == 0x03:
        freq = decode_bcd_frequency(msg[5:10])
        if freq and freq > 0:
            center_freq_mhz = freq
            return True
    return False

def wait_for_spectrum_frame(sock):
    """Attend et retourne UNE trame de spectre, vérifie aussi les réponses de fréquence"""
    while True:
        msg = read_one_message(sock)
        if msg is None:
            return None
        
        # Vérifier si c'est une réponse de fréquence
        check_frequency_response(msg)
        
        # Vérifier si c'est une trame de spectre (commande 0x27, > 100 bytes)
        if len(msg) > 100 and msg[4] == 0x27:
            return msg

def extract_spectrum_data(msg):
    """Extrait les données d'amplitude d'une trame de spectre"""
    if msg is None or len(msg) < 50:
        return None
    
    # Données d'amplitude à partir du byte 19
    amp_data = msg[19:-1]  # Exclure le FD final
    
    if len(amp_data) < 10:
        return None
    
    # Sous-échantillonner pour NUM_POINTS
    raw_len = len(amp_data)
    if raw_len >= NUM_POINTS:
        indices = np.linspace(0, raw_len - 1, NUM_POINTS, dtype=int)
        return np.array([amp_data[i] for i in indices])
    else:
        result = np.zeros(NUM_POINTS)
        result[:raw_len] = list(amp_data)
        return result

# ============== PROGRAMME PRINCIPAL ==============

print("=" * 60)
print("IC-705 Spectrum Display - Temps Réel")
print("=" * 60)
print(f"Connexion: {HOST}:{PORT}")
print()

try:
    # Connexion
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    sock.connect((HOST, PORT))
    print("✅ Connecté au serveur CI-V")
    
    # Récupérer la fréquence (rapide)
    print("→ Récupération de la fréquence...")
    get_frequency_fast(sock)
    print(f"✅ Fréquence: {center_freq_mhz:.6f} MHz")
    
    # Activer le streaming (sans attente)
    print("→ Activation du streaming spectral...")
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x01, 0xFD])
    sock.send(cmd)
    
    # Pas de sleep - on démarre directement
    print("✅ Streaming activé")
    print()
    print("Affichage en temps réel... (Ctrl+C pour arrêter)")
    print()
    
    # Timeout normal pour la boucle
    sock.settimeout(1.0)
    
    # Créer la figure
    plt.ion()  # Mode interactif
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7))
    
    # Axe des fréquences
    freq_axis = np.linspace(
        center_freq_mhz - SPAN_KHZ/2000,
        center_freq_mhz + SPAN_KHZ/2000,
        NUM_POINTS
    )
    
    # Initialiser le graphe du spectre (style wfview: fond noir, ligne jaune)
    spectrum_data = np.zeros(NUM_POINTS)
    line, = ax1.plot(freq_axis, spectrum_data, color='#FFFF00', linewidth=1)  # Jaune comme wfview
    ax1.set_xlim(freq_axis[0], freq_axis[-1])
    ax1.set_ylim(0, 160)  # Échelle similaire à wfview (0-150)
    ax1.set_xlabel('Fréquence (MHz)')
    ax1.set_ylabel('Amplitude')
    ax1.set_title(f'Spectre IC-705 - {center_freq_mhz:.6f} MHz')
    ax1.grid(True, alpha=0.3, color='#444444')
    ax1.set_facecolor('#000022')  # Fond bleu très foncé comme wfview
    # Désactiver l'offset scientifique
    ax1.ticklabel_format(useOffset=False, style='plain')
    ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
    
    # Initialiser le waterfall avec interpolation pour un aspect lissé
    # Comme wfview: nouvelles données en haut, défilement vers le bas
    waterfall_data = np.zeros((WATERFALL_DEPTH, NUM_POINTS))
    waterfall_img = ax2.imshow(waterfall_data, aspect='auto', cmap=wfview_cmap,
                               extent=[freq_axis[0], freq_axis[-1], WATERFALL_DEPTH, 0],
                               vmin=0, vmax=255,
                               interpolation='bilinear',
                               origin='upper')  # Origine en haut comme wfview
    ax2.set_xlabel('Fréquence (MHz)')
    ax2.set_ylabel('Temps')
    ax2.set_title('Waterfall')
    # Désactiver l'offset scientifique
    ax2.ticklabel_format(useOffset=False, style='plain')
    ax2.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
    plt.colorbar(waterfall_img, ax=ax2, label='Amplitude')
    
    # Ajuster la mise en page pour faire de la place pour les contrôles
    plt.subplots_adjust(bottom=0.15)
    
    # ============== ZONE DE TEXTE POUR LA FRÉQUENCE ==============
    # Zone de saisie de fréquence
    freq_box_ax = plt.axes([0.15, 0.02, 0.2, 0.04])
    freq_textbox = TextBox(freq_box_ax, 'Fréquence (MHz): ', initial=f'{center_freq_mhz:.6f}')
    
    # Variable pour stocker la nouvelle fréquence à appliquer
    new_freq_to_set = [None]  # Liste pour pouvoir modifier dans le callback
    
    def on_freq_submit(text):
        """Callback quand l'utilisateur valide une nouvelle fréquence"""
        try:
            new_freq = float(text)
            if 0.1 < new_freq < 500:  # Plage valide pour IC-705
                new_freq_to_set[0] = new_freq
                print(f"→ Nouvelle fréquence demandée: {new_freq:.6f} MHz")
            else:
                print("⚠️ Fréquence hors plage (0.1 - 500 MHz)")
        except ValueError:
            print("⚠️ Format invalide. Utilisez un nombre décimal (ex: 145.500)")
    
    freq_textbox.on_submit(on_freq_submit)
    
    # Bouton pour appliquer la fréquence
    btn_ax = plt.axes([0.4, 0.02, 0.1, 0.04])
    btn_apply = Button(btn_ax, 'Appliquer')
    
    def on_apply_click(event):
        """Applique la fréquence saisie"""
        try:
            new_freq = float(freq_textbox.text)
            if 0.1 < new_freq < 500:
                new_freq_to_set[0] = new_freq
        except:
            pass
    
    btn_apply.on_clicked(on_apply_click)
    
    plt.show(block=False)
    
    # ============== BOUCLE PRINCIPALE ==============
    # Logique: RECEVOIR → AFFICHER → RECEVOIR → AFFICHER
    # + Demande de fréquence toutes les 10 trames
    
    frame_count = 0
    last_freq = center_freq_mhz
    
    while plt.fignum_exists(fig.number):
        # Vérifier si une nouvelle fréquence doit être appliquée
        if new_freq_to_set[0] is not None:
            set_frequency(sock, new_freq_to_set[0])
            new_freq_to_set[0] = None
            # Mettre à jour la zone de texte
            freq_textbox.set_val(f'{center_freq_mhz:.6f}')
        
        # Demander la fréquence toutes les 10 trames
        if frame_count % 10 == 0:
            request_frequency(sock)
        
        # 1. RECEVOIR une trame de spectre
        msg = wait_for_spectrum_frame(sock)
        
        if msg is None:
            continue
        
        # 2. EXTRAIRE les données
        new_data = extract_spectrum_data(msg)
        
        if new_data is None:
            continue
        
        # 3. METTRE À JOUR L'AXE DES FRÉQUENCES si la fréquence a changé
        if abs(center_freq_mhz - last_freq) > 0.0001:
            last_freq = center_freq_mhz
            freq_axis = np.linspace(
                center_freq_mhz - SPAN_KHZ/2000,
                center_freq_mhz + SPAN_KHZ/2000,
                NUM_POINTS
            )
            # Mettre à jour la ligne avec les nouvelles coordonnées X
            line.set_xdata(freq_axis)
            ax1.set_xlim(freq_axis[0], freq_axis[-1])
            ax1.set_title(f'Spectre IC-705 - {center_freq_mhz:.6f} MHz')
            # Mettre à jour l'extent du waterfall
            waterfall_img.set_extent([freq_axis[0], freq_axis[-1], WATERFALL_DEPTH, 0])
            ax2.set_xlim(freq_axis[0], freq_axis[-1])
        
        # 4. AFFICHER immédiatement
        # Mettre à jour le spectre
        line.set_ydata(new_data)
        
        # Mettre à jour le waterfall (nouvelles données en haut, défilement vers le bas)
        waterfall_history.appendleft(new_data.copy())  # Ajouter en haut
        if len(waterfall_history) > 0:
            waterfall_array = np.array(list(waterfall_history))
            # Padding en bas si pas assez de lignes
            if len(waterfall_array) < WATERFALL_DEPTH:
                padding = np.zeros((WATERFALL_DEPTH - len(waterfall_array), NUM_POINTS))
                waterfall_array = np.vstack([waterfall_array, padding])
            waterfall_img.set_data(waterfall_array)
        
        # Forcer le rafraîchissement
        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        
        frame_count += 1
        if frame_count % 50 == 0:
            print(f"  {frame_count} trames reçues...")
    
    print("\n✅ Fenêtre fermée")

except KeyboardInterrupt:
    print("\n\n⚠️  Interruption utilisateur")

except Exception as e:
    print(f"\n❌ Erreur: {e}")

finally:
    # Désactiver le streaming et fermer
    try:
        cmd_off = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x00, 0xFD])
        sock.send(cmd_off)
        time.sleep(0.2)
        sock.close()
        print("✅ Connexion fermée proprement")
    except:
        pass
    
    plt.close('all')
