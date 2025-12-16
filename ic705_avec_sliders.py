#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Version avec Sliders de Gain
======================================================
Version améliorée avec deux sliders pour ajuster le gain min/max
affiché sur le spectre et le waterfall.

Auteur: Étudiant PTUT
Date: Décembre 2025
"""

import socket
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

# ============================================================
#                    PARAMÈTRES DE CONFIGURATION
# ============================================================

SERVEUR_IP = '127.0.0.1'
SERVEUR_PORT = 50002
LARGEUR_SPECTRE = 200
PROFONDEUR_WATERFALL = 100
SPAN_KHZ = 50
FREQUENCE_DEFAUT = 145.000

# Gain par défaut
GAIN_MIN_DEFAUT = 0
GAIN_MAX_DEFAUT = 200

# Adresses CI-V
ADRESSE_RADIO = 0xA4
ADRESSE_PC = 0xE0


# ============================================================
#              FONCTIONS DE COMMUNICATION CI-V
# ============================================================

def connecter_au_serveur():
    """Se connecte au serveur wfview via TCP."""
    try:
        connexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connexion.settimeout(2)
        connexion.connect((SERVEUR_IP, SERVEUR_PORT))
        print(f"Connecté au serveur {SERVEUR_IP}:{SERVEUR_PORT}")
        return connexion
    except Exception as erreur:
        print(f"Erreur de connexion: {erreur}")
        return None


def envoyer_commande(connexion, commande):
    """Envoie une commande CI-V à la radio."""
    connexion.send(bytes(commande))


def activer_streaming(connexion):
    """Active le streaming du spectre."""
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x01, 0xFD]
    envoyer_commande(connexion, commande)
    print("Streaming spectral activé")


def desactiver_streaming(connexion):
    """Désactive le streaming du spectre."""
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x00, 0xFD]
    envoyer_commande(connexion, commande)
    print("Streaming spectral désactivé")


def demander_frequence(connexion):
    """Demande la fréquence actuelle à la radio."""
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x03, 0xFD]
    envoyer_commande(connexion, commande)


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
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
    """Trouve et extrait les messages CI-V complets dans un buffer."""
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
        message = bytes(buffer[:fin])
        messages.append(message)
        del buffer[:fin]
    return messages


def extraire_donnees_spectre(message):
    """Extrait les données d'amplitude d'un message de spectre."""
    if len(message) < 50:
        return None
    donnees_brutes = message[19:-1]
    if len(donnees_brutes) < 10:
        return None
    return np.array(list(donnees_brutes), dtype=float)


def redimensionner_spectre(amplitudes, taille_cible):
    """Redimensionne les données du spectre à la taille voulue."""
    taille_originale = len(amplitudes)
    if taille_originale >= taille_cible:
        indices = np.linspace(0, taille_originale - 1, taille_cible, dtype=int)
        return amplitudes[indices]
    else:
        resultat = np.zeros(taille_cible)
        resultat[:taille_originale] = amplitudes
        return resultat


# ============================================================
#              FONCTIONS D'AFFICHAGE AVEC SLIDERS
# ============================================================

def creer_figure_avec_sliders(freq_centrale):
    """
    Crée la figure avec spectre, waterfall et sliders de gain.
    
    Arguments:
        freq_centrale: Fréquence centrale en MHz
    
    Retourne:
        dict: Dictionnaire contenant tous les éléments graphiques
    """
    # Calculer l'axe des fréquences
    demi_span = SPAN_KHZ / 2000
    freq_min = freq_centrale - demi_span
    freq_max = freq_centrale + demi_span
    axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
    
    # Créer la figure avec espace pour les sliders
    fig = plt.figure(figsize=(11, 8))
    fig.patch.set_facecolor('#1a1a2e')
    
    # Créer les axes pour les graphiques (laisser de la place en bas pour les sliders)
    ax_spectre = fig.add_axes([0.1, 0.55, 0.8, 0.35])      # [left, bottom, width, height]
    ax_waterfall = fig.add_axes([0.1, 0.15, 0.8, 0.35])
    
    # Style sombre
    ax_spectre.set_facecolor('#0a0a1a')
    ax_waterfall.set_facecolor('#0a0a1a')
    
    # === Spectre ===
    ax_spectre.set_title(f'Spectre IC-705 - {freq_centrale:.3f} MHz', color='white')
    ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
    ax_spectre.set_ylabel('Amplitude', color='white')
    ax_spectre.set_xlim(freq_min, freq_max)
    ax_spectre.set_ylim(GAIN_MIN_DEFAUT, GAIN_MAX_DEFAUT)
    ax_spectre.tick_params(colors='white')
    ax_spectre.grid(True, alpha=0.3)
    ax_spectre.axvline(x=freq_centrale, color='red', linestyle='--', alpha=0.7)
    ligne, = ax_spectre.plot(axe_freq, np.zeros(LARGEUR_SPECTRE), color='yellow', linewidth=1)
    
    # === Waterfall ===
    ax_waterfall.set_xlabel('Fréquence (MHz)', color='white')
    ax_waterfall.set_ylabel('Temps', color='white')
    ax_waterfall.tick_params(colors='white')
    
    donnees_vides = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
    image = ax_waterfall.imshow(
        donnees_vides,
        aspect='auto',
        cmap='viridis',
        vmin=GAIN_MIN_DEFAUT,
        vmax=GAIN_MAX_DEFAUT,
        origin='upper',
        extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
    )
    
    # === Sliders de gain ===
    # Créer les axes pour les sliders
    ax_slider_min = fig.add_axes([0.15, 0.06, 0.3, 0.02])
    ax_slider_max = fig.add_axes([0.55, 0.06, 0.3, 0.02])
    
    # Style des sliders
    ax_slider_min.set_facecolor('#2a2a4e')
    ax_slider_max.set_facecolor('#2a2a4e')
    
    # Créer les sliders
    slider_min = Slider(
        ax_slider_min,
        'Gain Min',
        0, 150,                    # Plage de valeurs
        valinit=GAIN_MIN_DEFAUT,   # Valeur initiale
        valstep=5,                 # Pas de 5
        color='#4a90d9'
    )
    
    slider_max = Slider(
        ax_slider_max,
        'Gain Max',
        50, 255,                   # Plage de valeurs
        valinit=GAIN_MAX_DEFAUT,   # Valeur initiale
        valstep=5,                 # Pas de 5
        color='#d94a4a'
    )
    
    # Personnaliser les couleurs du texte des sliders
    slider_min.label.set_color('white')
    slider_max.label.set_color('white')
    slider_min.valtext.set_color('white')
    slider_max.valtext.set_color('white')
    
    plt.ion()
    plt.show()
    
    # Retourner tous les éléments dans un dictionnaire
    return {
        'fig': fig,
        'ax_spectre': ax_spectre,
        'ax_waterfall': ax_waterfall,
        'ligne': ligne,
        'image': image,
        'axe_freq': axe_freq,
        'slider_min': slider_min,
        'slider_max': slider_max,
        'gain_min': GAIN_MIN_DEFAUT,
        'gain_max': GAIN_MAX_DEFAUT
    }


def mettre_a_jour_gains(elements):
    """
    Met à jour les limites d'affichage selon les valeurs des sliders.
    
    Arguments:
        elements: Dictionnaire des éléments graphiques
    """
    gain_min = elements['slider_min'].val
    gain_max = elements['slider_max'].val
    
    # S'assurer que min < max
    if gain_min >= gain_max:
        gain_min = gain_max - 10
    
    # Mettre à jour le spectre (axe Y)
    elements['ax_spectre'].set_ylim(gain_min, gain_max)
    
    # Mettre à jour le waterfall (échelle de couleurs)
    elements['image'].set_clim(vmin=gain_min, vmax=gain_max)
    
    # Sauvegarder les nouvelles valeurs
    elements['gain_min'] = gain_min
    elements['gain_max'] = gain_max


def mettre_a_jour_affichage(elements, spectre, waterfall):
    """
    Met à jour l'affichage du spectre et du waterfall.
    
    Arguments:
        elements: Dictionnaire des éléments graphiques
        spectre: Données du spectre (tableau 1D)
        waterfall: Données du waterfall (tableau 2D)
    """
    # Mettre à jour les gains depuis les sliders
    mettre_a_jour_gains(elements)
    
    # Mettre à jour les données
    elements['ligne'].set_data(elements['axe_freq'], spectre)
    elements['image'].set_data(waterfall)
    
    # Rafraîchir
    plt.draw()
    plt.pause(0.001)


def faire_defiler_waterfall(waterfall, nouvelle_ligne):
    """Fait défiler le waterfall vers le bas et ajoute une nouvelle ligne en haut."""
    waterfall[1:] = waterfall[:-1]
    waterfall[0] = nouvelle_ligne


# ============================================================
#              FONCTION PRINCIPALE
# ============================================================

def main():
    """Fonction principale du programme."""
    print("=" * 55)
    print("  IC-705 Spectrum Display - Version avec Sliders")
    print("=" * 55)
    
    # --- Connexion ---
    connexion = connecter_au_serveur()
    if connexion is None:
        return
    
    # --- Activer le streaming ---
    activer_streaming(connexion)
    time.sleep(0.5)
    
    # --- Récupérer la fréquence initiale ---
    demander_frequence(connexion)
    time.sleep(0.2)
    freq_centrale = FREQUENCE_DEFAUT
    try:
        reponse = connexion.recv(1024)
        for i in range(len(reponse) - 10):
            if reponse[i] == 0xFE and reponse[i+1] == 0xFE and reponse[i+4] == 0x03:
                freq_centrale = decoder_frequence_bcd(reponse[i+5:i+10])
                print(f"Fréquence: {freq_centrale:.3f} MHz")
                break
    except:
        pass
    
    # --- Créer l'affichage avec sliders ---
    elements = creer_figure_avec_sliders(freq_centrale)
    
    # Initialiser les données
    spectre_actuel = np.zeros(LARGEUR_SPECTRE)
    waterfall_donnees = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
    buffer_reception = bytearray()
    nombre_trames = 0
    
    print("\n Utilisez les sliders pour ajuster le gain affiché")
    print(" Fermez la fenêtre pour arrêter.\n")
    
    # --- Boucle principale ---
    try:
        connexion.settimeout(0.1)
        
        while plt.fignum_exists(elements['fig'].number):
            
            # Recevoir des données
            try:
                donnees_recues = connexion.recv(4096)
                buffer_reception.extend(donnees_recues)
            except socket.timeout:
                pass
            except Exception as erreur:
                print(f"Erreur de réception: {erreur}")
                break
            
            # Extraire les messages CI-V
            messages = trouver_messages_civ(buffer_reception)
            
            # Traiter chaque message
            for message in messages:
                if len(message) < 5:
                    continue
                
                commande = message[4]
                
                # Message de spectre
                if commande == 0x27 and len(message) > 50:
                    amplitudes = extraire_donnees_spectre(message)
                    
                    if amplitudes is not None:
                        spectre_actuel = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        faire_defiler_waterfall(waterfall_donnees, spectre_actuel)
                        mettre_a_jour_affichage(elements, spectre_actuel, waterfall_donnees)
                        
                        nombre_trames += 1
                        if nombre_trames % 50 == 0:
                            print(f"   {nombre_trames} trames | Gain: {elements['gain_min']:.0f} - {elements['gain_max']:.0f}")
            
            # Limiter la taille du buffer
            if len(buffer_reception) > 10000:
                buffer_reception.clear()
    
    except KeyboardInterrupt:
        print("\n\n Arrêt demandé par l'utilisateur")
    
    # --- Nettoyage ---
    print("\n Nettoyage en cours...")
    desactiver_streaming(connexion)
    connexion.close()
    plt.close('all')
    
    print(f" Terminé! {nombre_trames} trames au total.")


# ============================================================
#              POINT D'ENTRÉE
# ============================================================

if __name__ == '__main__':
    main()
