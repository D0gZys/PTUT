#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Version Simple et Pédagogique
========================================================
Ce programme affiche le spectre et le waterfall de l'IC-705.
Code simplifié pour faciliter la compréhension.

Auteur: Étudiant PTUT
Date: Décembre 2025
"""

import socket
import time
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
#                    PARAMÈTRES DE CONFIGURATION
# ============================================================

SERVEUR_IP = '127.0.0.1'      # Adresse IP du serveur wfview
SERVEUR_PORT = 50002           # Port TCP de wfview
LARGEUR_SPECTRE = 200          # Nombre de points affichés
PROFONDEUR_WATERFALL = 100     # Nombre de lignes du waterfall
SPAN_KHZ = 50                  # Largeur du spectre en kHz
FREQUENCE_DEFAUT = 145.000     # Fréquence par défaut en MHz

# Adresses CI-V (protocole de communication Icom)
ADRESSE_RADIO = 0xA4           # Adresse de l'IC-705
ADRESSE_PC = 0xE0              # Adresse du PC (contrôleur)


# ============================================================
#              FONCTIONS DE COMMUNICATION CI-V
# ============================================================

def connecter_au_serveur():
    """
    Se connecte au serveur wfview via TCP.
    
    Retourne:
        socket: L'objet socket connecté, ou None si échec
    """
    try:
        # Créer un socket TCP
        connexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connexion.settimeout(2)  # Timeout de 2 secondes
        
        # Se connecter au serveur
        connexion.connect((SERVEUR_IP, SERVEUR_PORT))
        print(f"Connecté au serveur {SERVEUR_IP}:{SERVEUR_PORT}")
        
        return connexion
    
    except Exception as erreur:
        print(f"Erreur de connexion: {erreur}")
        return None


def envoyer_commande(connexion, commande):
    """
    Envoie une commande CI-V à la radio.
    
    Arguments:
        connexion: Le socket TCP
        commande: Liste d'octets à envoyer
    """
    connexion.send(bytes(commande))


def activer_streaming(connexion):
    """
    Active le streaming du spectre sur l'IC-705.
    
    La commande CI-V pour activer le streaming est:
    FE FE A4 E0 1A 05 00 01 FD
    
    Décomposition:
    - FE FE     : Préambule (début de trame)
    - A4        : Adresse destination (IC-705)
    - E0        : Adresse source (PC)
    - 1A 05     : Commande "réglage streaming"
    - 00 01     : Données (01 = activer)
    - FD        : Fin de trame
    """
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x01, 0xFD]
    envoyer_commande(connexion, commande)
    print(" Streaming spectral activé")


def desactiver_streaming(connexion):
    """
    Désactive le streaming du spectre.
    Même commande que activer_streaming mais avec 00 au lieu de 01.
    """
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x00, 0xFD]
    envoyer_commande(connexion, commande)
    print(" Streaming spectral désactivé")


def demander_frequence(connexion):
    """
    Demande la fréquence actuelle à la radio.
    
    La commande CI-V est:
    FE FE A4 E0 03 FD
    
    - 03 : Commande "lire fréquence"
    """
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x03, 0xFD]
    envoyer_commande(connexion, commande)


# ============================================================
#              FONCTIONS DE DÉCODAGE CI-V
# ============================================================

def decoder_frequence_bcd(octets_frequence):
    """
    Décode une fréquence encodée en BCD little-endian.
    
    Le format BCD (Binary Coded Decimal) stocke chaque chiffre décimal
    dans un demi-octet (nibble). L'IC-705 utilise le format little-endian
    (octet de poids faible en premier).
    
    Exemple: 145.000000 MHz = 145000000 Hz
    Encodé en BCD: 00 00 00 45 01
    - 00 : unités et dizaines de Hz      (00)
    - 00 : centaines et milliers de Hz   (00)  
    - 00 : dizaines et centaines de kHz  (00)
    - 45 : unités de MHz et dizaines kHz (45 = 5 et 4)
    - 01 : centaines de MHz              (01 = 1)
    Lecture: 1-4-5-0-0-0-0-0-0 = 145000000 Hz
    
    Arguments:
        octets_frequence: 5 octets contenant la fréquence en BCD
        
    Retourne:
        float: La fréquence en MHz
    """
    frequence_hz = 0
    multiplicateur = 1
    
    # Parcourir chaque octet
    for octet in octets_frequence:
        # Extraire le nibble bas (bits 0-3)
        chiffre_bas = octet & 0x0F
        frequence_hz += chiffre_bas * multiplicateur
        multiplicateur *= 10
        
        # Extraire le nibble haut (bits 4-7)
        chiffre_haut = (octet >> 4) & 0x0F
        frequence_hz += chiffre_haut * multiplicateur
        multiplicateur *= 10
    
    # Convertir Hz en MHz
    frequence_mhz = frequence_hz / 1_000_000
    return frequence_mhz


def trouver_messages_civ(buffer):
    """
    Trouve et extrait les messages CI-V complets dans un buffer.
    
    Un message CI-V a la structure:
    FE FE [dest] [src] [cmd] [données...] FD
    
    Arguments:
        buffer: bytearray contenant les données reçues
        
    Retourne:
        liste: Liste des messages complets trouvés
    """
    messages = []
    
    while True:
        # Chercher le début d'un message (FE FE)
        try:
            debut = buffer.index(0xFE)
        except ValueError:
            break  # Pas de FE trouvé
        
        # Supprimer les octets avant le début
        if debut > 0:
            del buffer[:debut]
        
        # Vérifier qu'on a bien FE FE (double préambule)
        if len(buffer) < 2:
            break
        if buffer[1] != 0xFE:
            del buffer[:1]  # Faux positif, continuer
            continue
        
        # Chercher la fin du message (FD)
        try:
            fin = buffer.index(0xFD, 2) + 1
        except ValueError:
            break  # Message incomplet, attendre plus de données
        
        # Extraire le message complet
        message = bytes(buffer[:fin])
        messages.append(message)
        
        # Supprimer le message du buffer
        del buffer[:fin]
    
    return messages


def extraire_donnees_spectre(message):
    """
    Extrait les données d'amplitude d'un message de spectre.
    
    Structure d'un message de spectre (CMD 0x27):
    - Octets 0-3   : Préambule et adresses (FE FE xx xx)
    - Octet 4      : Commande (27)
    - Octets 5-18  : Métadonnées (fréquence, span, etc.)
    - Octets 19+   : Données d'amplitude (jusqu'à FD)
    
    Arguments:
        message: bytes du message CI-V complet
        
    Retourne:
        numpy.array: Tableau des amplitudes, ou None si invalide
    """
    # Vérifier la taille minimale
    if len(message) < 50:
        return None
    
    # Extraire les données d'amplitude (à partir de l'octet 19, avant FD)
    donnees_brutes = message[19:-1]
    
    if len(donnees_brutes) < 10:
        return None
    
    # Convertir en tableau numpy
    amplitudes = np.array(list(donnees_brutes), dtype=float)
    
    return amplitudes


def redimensionner_spectre(amplitudes, taille_cible):
    """
    Redimensionne les données du spectre à la taille voulue.
    
    L'IC-705 envoie environ 450 points, on les réduit à 200
    pour l'affichage en prenant des échantillons réguliers.
    
    Arguments:
        amplitudes: Tableau numpy des amplitudes brutes
        taille_cible: Nombre de points souhaités
        
    Retourne:
        numpy.array: Tableau redimensionné
    """
    taille_originale = len(amplitudes)
    
    if taille_originale >= taille_cible:
        # Sous-échantillonnage: prendre des points régulièrement espacés
        indices = np.linspace(0, taille_originale - 1, taille_cible, dtype=int)
        return amplitudes[indices]
    else:
        # Données insuffisantes: compléter avec des zéros
        resultat = np.zeros(taille_cible)
        resultat[:taille_originale] = amplitudes
        return resultat


# ============================================================
#              FONCTIONS D'AFFICHAGE
# ============================================================

def creer_figure(freq_centrale):
    """
    Crée la figure matplotlib avec le spectre et le waterfall.
    
    Arguments:
        freq_centrale: Fréquence centrale en MHz
    
    Retourne:
        tuple: (figure, axe_spectre, axe_waterfall, ligne_spectre, image_waterfall, axe_freq)
    """
    # Calculer l'axe des fréquences (centre ± span/2)
    demi_span = SPAN_KHZ / 2000  # Convertir kHz en MHz
    freq_min = freq_centrale - demi_span
    freq_max = freq_centrale + demi_span
    axe_freq = np.linspace(freq_min, freq_max, LARGEUR_SPECTRE)
    
    # Créer une figure avec 2 sous-graphiques
    fig, (ax_spectre, ax_waterfall) = plt.subplots(2, 1, figsize=(10, 6))
    
    # Style sombre
    fig.patch.set_facecolor('#1a1a2e')
    ax_spectre.set_facecolor('#0a0a1a')
    ax_waterfall.set_facecolor('#0a0a1a')
    
    # Configurer le spectre
    ax_spectre.set_title(f'Spectre IC-705 - {freq_centrale:.3f} MHz', color='white')
    ax_spectre.set_xlabel('Fréquence (MHz)', color='white')
    ax_spectre.set_ylabel('Amplitude', color='white')
    ax_spectre.set_xlim(freq_min, freq_max)
    ax_spectre.set_ylim(0, 200)
    ax_spectre.tick_params(colors='white')
    ax_spectre.grid(True, alpha=0.3)
    
    # Ligne verticale rouge au centre (fréquence centrale)
    ax_spectre.axvline(x=freq_centrale, color='red', linestyle='--', alpha=0.7)
    
    # Créer la ligne du spectre
    ligne, = ax_spectre.plot(axe_freq, np.zeros(LARGEUR_SPECTRE), color='yellow', linewidth=1)
    
    # Configurer le waterfall
    ax_waterfall.set_title('Waterfall', color='white')
    ax_waterfall.set_xlabel('Fréquence (MHz)', color='white')
    ax_waterfall.set_ylabel('Temps', color='white')
    ax_waterfall.tick_params(colors='white')
    
    # Créer l'image du waterfall avec l'étendue en fréquence
    donnees_vides = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
    image = ax_waterfall.imshow(
        donnees_vides,
        aspect='auto',
        cmap='viridis',
        vmin=0, vmax=200,
        origin='upper',
        extent=[freq_min, freq_max, PROFONDEUR_WATERFALL, 0]
    )
    
    plt.tight_layout()
    plt.ion()
    plt.show()
    
    return fig, ax_spectre, ax_waterfall, ligne, image, axe_freq


def mettre_a_jour_affichage(ligne, image, spectre, waterfall, axe_freq):
    """
    Met à jour l'affichage du spectre et du waterfall.
    
    Arguments:
        ligne: Objet Line2D du spectre
        image: Objet AxesImage du waterfall
        spectre: Données du spectre (tableau 1D)
        waterfall: Données du waterfall (tableau 2D)
        axe_freq: Tableau des fréquences en MHz
    """
    # Mettre à jour la ligne du spectre (fréquences en X, amplitudes en Y)
    ligne.set_data(axe_freq, spectre)
    
    # Mettre à jour l'image du waterfall
    image.set_data(waterfall)
    
    # Rafraîchir l'affichage
    plt.draw()
    plt.pause(0.001)


def faire_defiler_waterfall(waterfall, nouvelle_ligne):
    """
    Fait défiler le waterfall vers le bas et ajoute une nouvelle ligne en haut.
    
    Le waterfall est comme un historique visuel:
    - Les nouvelles données arrivent en haut
    - Les anciennes données descendent
    - Les plus anciennes disparaissent en bas
    
    Arguments:
        waterfall: Tableau 2D du waterfall
        nouvelle_ligne: Données du spectre à ajouter en haut
    """
    # Décaler toutes les lignes vers le bas (copie)
    waterfall[1:] = waterfall[:-1]
    
    # Ajouter la nouvelle ligne en haut
    waterfall[0] = nouvelle_ligne


# ============================================================
#              FONCTION PRINCIPALE
# ============================================================

def main():
    """
    Fonction principale du programme.
    
    Étapes:
    1. Se connecter au serveur wfview
    2. Activer le streaming du spectre
    3. Créer l'affichage graphique
    4. Boucle: recevoir données → mettre à jour affichage
    5. Nettoyage à la fermeture
    """
    print("=" * 50)
    print("  IC-705 Spectrum Display - Version Simple")
    print("=" * 50)
    
    # --- Étape 1: Connexion ---
    connexion = connecter_au_serveur()
    if connexion is None:
        return
    
    # --- Étape 2: Activer le streaming ---
    activer_streaming(connexion)
    time.sleep(0.5)  # Attendre que la radio soit prête
    
    # --- Étape 2b: Récupérer la fréquence initiale ---
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
    
    # --- Étape 3: Créer l'affichage ---
    fig, ax_spectre, ax_waterfall, ligne, image, axe_freq = creer_figure(freq_centrale)
    
    # Initialiser les données
    spectre_actuel = np.zeros(LARGEUR_SPECTRE)
    waterfall_donnees = np.zeros((PROFONDEUR_WATERFALL, LARGEUR_SPECTRE))
    
    # Buffer pour recevoir les données
    buffer_reception = bytearray()
    
    # Compteur de trames
    nombre_trames = 0
    
    print("\n Affichage en cours... Fermez la fenêtre pour arrêter.\n")
    
    # --- Étape 4: Boucle principale ---
    try:
        connexion.settimeout(0.1)  # Timeout court pour ne pas bloquer
        
        while plt.fignum_exists(fig.number):  # Tant que la fenêtre est ouverte
            
            # Recevoir des données du serveur
            try:
                donnees_recues = connexion.recv(4096)
                buffer_reception.extend(donnees_recues)
            except socket.timeout:
                pass  # Pas de données, ce n'est pas grave
            except Exception as erreur:
                print(f"Erreur de réception: {erreur}")
                break
            
            # Extraire les messages CI-V du buffer
            messages = trouver_messages_civ(buffer_reception)
            
            # Traiter chaque message
            for message in messages:
                if len(message) < 5:
                    continue
                
                # Identifier le type de commande (octet 4)
                commande = message[4]
                
                # Si c'est un message de spectre (commande 0x27)
                if commande == 0x27 and len(message) > 50:
                    
                    # Extraire les données d'amplitude
                    amplitudes = extraire_donnees_spectre(message)
                    
                    if amplitudes is not None:
                        # Redimensionner à la taille d'affichage
                        spectre_actuel = redimensionner_spectre(amplitudes, LARGEUR_SPECTRE)
                        
                        # Faire défiler le waterfall et ajouter la nouvelle ligne
                        faire_defiler_waterfall(waterfall_donnees, spectre_actuel)
                        
                        # Mettre à jour l'affichage
                        mettre_a_jour_affichage(ligne, image, spectre_actuel, waterfall_donnees, axe_freq)
                        
                        nombre_trames += 1
                        
                        # Afficher les stats toutes les 50 trames
                        if nombre_trames % 50 == 0:
                            print(f"   {nombre_trames} trames reçues")
            
            # Limiter la taille du buffer pour éviter les fuites mémoire
            if len(buffer_reception) > 10000:
                buffer_reception.clear()
    
    except KeyboardInterrupt:
        print("\n\n  Arrêt demandé par l'utilisateur (Ctrl+C)")
    
    # --- Étape 5: Nettoyage ---
    print("\n Nettoyage en cours...")
    desactiver_streaming(connexion)
    connexion.close()
    plt.close('all')
    
    print(f" Terminé! {nombre_trames} trames au total.")


# ============================================================
#              POINT D'ENTRÉE DU PROGRAMME
# ============================================================

if __name__ == '__main__':
    main()
