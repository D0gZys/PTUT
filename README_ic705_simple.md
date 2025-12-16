# README - ic705_simple.py

## Documentation Complète et Pédagogique

Ce document décrit en détail le programme `ic705_simple.py`, un afficheur de spectre pour la radio Icom IC-705. L'objectif est de permettre à toute personne (humain ou IA) de comprendre parfaitement le fonctionnement du programme.

---

## 📋 Table des Matières

1. [Vue d'Ensemble](#1-vue-densemble)
2. [Architecture du Programme](#2-architecture-du-programme)
3. [Protocole CI-V Icom](#3-protocole-ci-v-icom)
4. [Constantes et Configuration](#4-constantes-et-configuration)
5. [Fonctions de Communication CI-V](#5-fonctions-de-communication-ci-v)
6. [Fonctions de Décodage CI-V](#6-fonctions-de-décodage-ci-v)
7. [Fonctions d'Affichage](#7-fonctions-daffichage)
8. [Fonction Principale](#8-fonction-principale)
9. [Flux d'Exécution Complet](#9-flux-dexécution-complet)
10. [Exemples de Trames CI-V Détaillés](#10-exemples-de-trames-ci-v-détaillés)

---

## 1. Vue d'Ensemble

### Objectif du Programme
Ce programme affiche en temps réel le spectre radio et le waterfall (cascade) de l'IC-705.
Il se connecte au logiciel **wfview** qui sert de passerelle TCP vers la radio.

### Dépendances
```python
import socket      # Communication réseau TCP
import time        # Gestion des délais
import numpy as np # Calculs sur tableaux
import matplotlib.pyplot as plt  # Affichage graphique
```

### Schéma de Communication
```
┌──────────┐      USB/WiFi      ┌─────────┐      TCP:50002      ┌────────────┐
│  IC-705  │ ◄──────────────► │ wfview  │ ◄─────────────────► │ ic705_simple.py │
│  (Radio) │    CI-V natif     │(serveur)│    CI-V sur TCP     │  (ce programme) │
└──────────┘                   └─────────┘                     └────────────┘
```

---

## 2. Architecture du Programme

### Organisation des Sections
```
ic705_simple.py
│
├── PARAMÈTRES DE CONFIGURATION (lignes 18-30)
│   └── Constantes globales
│
├── FONCTIONS DE COMMUNICATION CI-V (lignes 35-105)
│   ├── connecter_au_serveur()
│   ├── envoyer_commande()
│   ├── activer_streaming()
│   ├── desactiver_streaming()
│   └── demander_frequence()
│
├── FONCTIONS DE DÉCODAGE CI-V (lignes 110-237)
│   ├── decoder_frequence_bcd()
│   ├── trouver_messages_civ()
│   ├── extraire_donnees_spectre()
│   └── redimensionner_spectre()
│
├── FONCTIONS D'AFFICHAGE (lignes 242-330)
│   ├── creer_figure()
│   ├── mettre_a_jour_affichage()
│   └── faire_defiler_waterfall()
│
├── FONCTION PRINCIPALE (lignes 335-480)
│   └── main()
│
└── POINT D'ENTRÉE (lignes 485-490)
    └── if __name__ == '__main__'
```

---

## 3. Protocole CI-V Icom

### Qu'est-ce que CI-V ?
CI-V (Communication Interface V) est le protocole de communication propriétaire d'Icom pour contrôler ses radios. C'est un protocole série à base de trames d'octets.

### Structure Générale d'une Trame CI-V

```
┌──────────────────────────────────────────────────────────────────────┐
│                     TRAME CI-V GÉNÉRIQUE                             │
├──────┬──────┬──────┬──────┬──────┬─────────────────┬──────┐
│ 0xFE │ 0xFE │ DEST │ SRC  │ CMD  │   DONNÉES...    │ 0xFD │
├──────┴──────┴──────┴──────┴──────┴─────────────────┴──────┤
│ Préambule  │Adresses│Commande│    Variable      │  Fin   │
└──────────────────────────────────────────────────────────────────────┘
```

### Détail de Chaque Champ

| Position | Valeur | Nom | Description |
|----------|--------|-----|-------------|
| 0 | `0xFE` | Préambule 1 | Premier octet de début de trame |
| 1 | `0xFE` | Préambule 2 | Second octet de début (toujours doublé) |
| 2 | `0x00-0xFF` | Destination | Adresse de la radio destinataire |
| 3 | `0x00-0xFF` | Source | Adresse de l'émetteur (PC) |
| 4 | `0x00-0xFF` | Commande | Code de la commande |
| 5+ | Variable | Données | Dépend de la commande (peut être vide) |
| Dernier | `0xFD` | Terminateur | Marque la fin de la trame |

### Adresses Utilisées dans ce Programme

| Adresse | Hexadécimal | Signification |
|---------|-------------|---------------|
| IC-705 | `0xA4` | Adresse par défaut de l'IC-705 |
| PC | `0xE0` | Adresse conventionnelle du contrôleur |

### Commandes CI-V Utilisées

| Code | Hexadécimal | Fonction |
|------|-------------|----------|
| Lire fréquence | `0x03` | Demander la fréquence actuelle |
| Streaming | `0x1A 0x05` | Contrôler le streaming du spectre |
| Spectre | `0x27` | Données du spectre (émis par la radio) |

---

## 3.1 Liste Complète des Commandes Hexadécimales

### Commandes Envoyées par le Programme (PC → Radio)

| Commande | Hex | Trame Complète | Description |
|----------|-----|----------------|-------------|
| **Lire Fréquence** | `03` | `FE FE A4 E0 03 FD` | Demande la fréquence VFO actuelle |
| **Activer Streaming** | `1A 05` | `FE FE A4 E0 1A 05 00 01 FD` | Active l'envoi continu du spectre |
| **Désactiver Streaming** | `1A 05` | `FE FE A4 E0 1A 05 00 00 FD` | Arrête l'envoi du spectre |

### Commandes Reçues par le Programme (Radio → PC)

| Commande | Hex | Structure | Description |
|----------|-----|-----------|-------------|
| **Réponse Fréquence** | `03` | `FE FE E0 A4 03 [5 octets BCD] FD` | Fréquence actuelle en BCD |
| **Données Spectre** | `27` | `FE FE E0 A4 27 [métadonnées] [amplitudes] FD` | Trame spectre (~475 octets) |

### Détail de Chaque Commande

#### `0x03` - Lire/Réponse Fréquence

**Envoi (requête)** :
```
FE FE A4 E0 03 FD
     │  │  └── Commande: lire fréquence
     │  └───── Source: PC (0xE0)
     └──────── Destination: IC-705 (0xA4)
```

**Réception (réponse)** :
```
FE FE E0 A4 03 XX XX XX XX XX FD
     │  │  │  └──────────────── 5 octets fréquence BCD (little-endian)
     │  │  └─────────────────── Commande: réponse fréquence
     │  └────────────────────── Source: IC-705 (0xA4)
     └───────────────────────── Destination: PC (0xE0)
```

#### `0x1A 0x05` - Contrôle Streaming Spectre

**Activer** :
```
FE FE A4 E0 1A 05 00 01 FD
           │  │  │  └── 01 = ACTIVER
           │  │  └───── Paramètre (toujours 00)
           │  └──────── Sous-commande: streaming
           └─────────── Commande principale: paramètres
```

**Désactiver** :
```
FE FE A4 E0 1A 05 00 00 FD
                     └── 00 = DÉSACTIVER
```

#### `0x27` - Données Spectre (reçu uniquement)

```
FE FE E0 A4 27 [Freq 5B] [Span 2B] [Meta 7B] [Amplitudes ~450B] FD
           │   │         │         │         └── Valeurs 0-255
           │   │         │         └──────────── Paramètres divers
           │   │         └────────────────────── Largeur de bande
           │   └──────────────────────────────── Fréquence centrale BCD
           └──────────────────────────────────── Commande spectre
```

### Tableau Récapitulatif des Octets Importants

| Octet | Valeur | Signification |
|-------|--------|---------------|
| `0xFE` | 254 | Préambule (début de trame) |
| `0xFD` | 253 | Terminateur (fin de trame) |
| `0xA4` | 164 | Adresse IC-705 |
| `0xE0` | 224 | Adresse PC/Contrôleur |
| `0x03` | 3 | Commande: Fréquence |
| `0x1A` | 26 | Commande: Paramètres |
| `0x05` | 5 | Sous-commande: Streaming |
| `0x27` | 39 | Commande: Spectre |
| `0x00` | 0 | Valeur OFF / Paramètre |
| `0x01` | 1 | Valeur ON |

### Autres Commandes CI-V (non utilisées dans ce programme)

Pour référence, voici d'autres commandes CI-V courantes :

| Commande | Hex | Description |
|----------|-----|-------------|
| Écrire fréquence | `0x05` | Changer la fréquence |
| Lire mode | `0x04` | Obtenir le mode (USB, LSB, FM...) |
| Écrire mode | `0x06` | Changer le mode |
| PTT ON | `0x1C 0x00 0x01` | Activer l'émission |
| PTT OFF | `0x1C 0x00 0x00` | Arrêter l'émission |
| Lire S-mètre | `0x15 0x02` | Obtenir la force du signal |
| Lire puissance | `0x15 0x11` | Obtenir la puissance de sortie |

---

## 4. Constantes et Configuration

### Tableau des Constantes

```python
# Réseau
SERVEUR_IP = '127.0.0.1'      # Adresse localhost (wfview sur le même PC)
SERVEUR_PORT = 50002           # Port TCP standard de wfview

# Affichage
LARGEUR_SPECTRE = 200          # 200 points sur l'axe X du graphique
PROFONDEUR_WATERFALL = 100     # 100 lignes historiques dans le waterfall
SPAN_KHZ = 50                  # 50 kHz de largeur de bande affichée
FREQUENCE_DEFAUT = 145.000     # Si fréquence non récupérée: 145 MHz

# Protocole CI-V
ADRESSE_RADIO = 0xA4           # Adresse IC-705 (0xA4 = 164 en décimal)
ADRESSE_PC = 0xE0              # Adresse PC (0xE0 = 224 en décimal)
```

### Signification du Span
Le **span** définit la largeur de bande affichée. Avec `SPAN_KHZ = 50` :
- Fréquence centrale : 145.000 MHz
- Fréquence minimale : 145.000 - 0.025 = 144.975 MHz
- Fréquence maximale : 145.000 + 0.025 = 145.025 MHz

---

## 5. Fonctions de Communication CI-V

### 5.1 `connecter_au_serveur()`

**But** : Établir une connexion TCP avec le serveur wfview.

**Paramètres** : Aucun

**Retourne** : 
- `socket` : Objet socket connecté si succès
- `None` : Si échec de connexion

**Fonctionnement** :
```
1. Créer un socket TCP (AF_INET = IPv4, SOCK_STREAM = TCP)
2. Définir un timeout de 2 secondes
3. Se connecter à SERVEUR_IP:SERVEUR_PORT
4. Retourner le socket ou None
```

**Code Source** :
```python
def connecter_au_serveur():
    try:
        connexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connexion.settimeout(2)
        connexion.connect((SERVEUR_IP, SERVEUR_PORT))
        print(f"Connecté au serveur {SERVEUR_IP}:{SERVEUR_PORT}")
        return connexion
    except Exception as erreur:
        print(f"Erreur de connexion: {erreur}")
        return None
```

---

### 5.2 `envoyer_commande(connexion, commande)`

**But** : Envoyer une trame CI-V au serveur.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `connexion` | `socket` | Socket TCP connecté |
| `commande` | `list[int]` | Liste d'octets de la trame CI-V |

**Retourne** : Rien (`None`)

**Code Source** :
```python
def envoyer_commande(connexion, commande):
    connexion.send(bytes(commande))
```

**Exemple d'utilisation** :
```python
commande = [0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD]
envoyer_commande(connexion, commande)
```

---

### 5.3 `activer_streaming(connexion)`

**But** : Activer le flux continu de données spectrales de l'IC-705.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `connexion` | `socket` | Socket TCP connecté |

**Retourne** : Rien (`None`)

**Trame Envoyée** :
```
FE FE A4 E0 1A 05 00 01 FD
```

**Décomposition Octet par Octet** :

| Position | Octet | Hex | Signification |
|----------|-------|-----|---------------|
| 0 | `FE` | 0xFE | Préambule (début de trame) |
| 1 | `FE` | 0xFE | Préambule (toujours doublé) |
| 2 | `A4` | 0xA4 | Destination = IC-705 |
| 3 | `E0` | 0xE0 | Source = PC |
| 4 | `1A` | 0x1A | Commande principale (paramètres) |
| 5 | `05` | 0x05 | Sous-commande (streaming spectre) |
| 6 | `00` | 0x00 | Paramètre 1 (fixe) |
| 7 | `01` | 0x01 | **Valeur: 01 = ACTIVER** |
| 8 | `FD` | 0xFD | Terminateur (fin de trame) |

**Code Source** :
```python
def activer_streaming(connexion):
    commande = [0xFE, 0xFE, ADRESSE_RADIO, ADRESSE_PC, 0x1A, 0x05, 0x00, 0x01, 0xFD]
    envoyer_commande(connexion, commande)
    print(" Streaming spectral activé")
```

---

### 5.4 `desactiver_streaming(connexion)`

**But** : Arrêter le flux de données spectrales.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `connexion` | `socket` | Socket TCP connecté |

**Retourne** : Rien (`None`)

**Trame Envoyée** :
```
FE FE A4 E0 1A 05 00 00 FD
```

**Seule différence avec activer_streaming** :

| Position | Activer | Désactiver | Différence |
|----------|---------|------------|------------|
| 7 | `0x01` | `0x00` | **01 = ON, 00 = OFF** |

---

### 5.5 `demander_frequence(connexion)`

**But** : Demander à la radio sa fréquence d'émission/réception actuelle.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `connexion` | `socket` | Socket TCP connecté |

**Retourne** : Rien (`None`) - La réponse arrive séparément

**Trame Envoyée** :
```
FE FE A4 E0 03 FD
```

**Décomposition** :

| Position | Octet | Signification |
|----------|-------|---------------|
| 0 | `FE` | Préambule |
| 1 | `FE` | Préambule |
| 2 | `A4` | Destination = IC-705 |
| 3 | `E0` | Source = PC |
| 4 | `03` | **Commande: Lire fréquence** |
| 5 | `FD` | Terminateur |

**Réponse Attendue de la Radio** :
```
FE FE E0 A4 03 [5 octets fréquence BCD] FD
```

Exemple si la radio est sur 145.000 MHz :
```
FE FE E0 A4 03 00 00 00 45 01 FD
```

---

## 6. Fonctions de Décodage CI-V

### 6.1 `decoder_frequence_bcd(octets_frequence)`

**But** : Convertir une fréquence encodée en BCD en valeur MHz.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `octets_frequence` | `bytes` | 5 octets contenant la fréquence BCD |

**Retourne** : `float` - Fréquence en MHz

#### Explication du Format BCD (Binary Coded Decimal)

Le BCD stocke chaque chiffre décimal dans un demi-octet (4 bits = nibble).
L'IC-705 utilise le format **little-endian** (poids faible en premier).

**Exemple : 145.000000 MHz = 145 000 000 Hz**

Les 5 octets BCD pour 145 000 000 Hz :
```
Octet 0: 00  →  chiffres:  0 et 0  (unités et dizaines de Hz)
Octet 1: 00  →  chiffres:  0 et 0  (centaines et milliers de Hz)
Octet 2: 00  →  chiffres:  0 et 0  (dizaines et centaines de kHz)
Octet 3: 45  →  chiffres:  5 et 4  (unités et dizaines de MHz)
Octet 4: 01  →  chiffres:  1 et 0  (centaines de MHz)
```

**Lecture pas à pas** (little-endian) :
```
Octet 0 (00): nibble bas = 0, nibble haut = 0  → 0×1 + 0×10 = 0
Octet 1 (00): nibble bas = 0, nibble haut = 0  → 0×100 + 0×1000 = 0
Octet 2 (00): nibble bas = 0, nibble haut = 0  → 0×10000 + 0×100000 = 0
Octet 3 (45): nibble bas = 5, nibble haut = 4  → 5×1000000 + 4×10000000 = 45000000
Octet 4 (01): nibble bas = 1, nibble haut = 0  → 1×100000000 + 0×1000000000 = 100000000

Total: 0 + 0 + 0 + 45000000 + 100000000 = 145000000 Hz = 145.000000 MHz
```

**Code Source** :
```python
def decoder_frequence_bcd(octets_frequence):
    frequence_hz = 0
    multiplicateur = 1
    
    for octet in octets_frequence:
        # Nibble bas (bits 0-3)
        chiffre_bas = octet & 0x0F          # Masque pour garder les 4 bits bas
        frequence_hz += chiffre_bas * multiplicateur
        multiplicateur *= 10
        
        # Nibble haut (bits 4-7)
        chiffre_haut = (octet >> 4) & 0x0F  # Décaler de 4 et masquer
        frequence_hz += chiffre_haut * multiplicateur
        multiplicateur *= 10
    
    frequence_mhz = frequence_hz / 1_000_000
    return frequence_mhz
```

#### Autres Exemples de Décodage

**Exemple 1 : 7.074 MHz** (fréquence FT8)
```
7 074 000 Hz en BCD:
Octets: 00 40 07 07 00
       │  │  │  │  └─ 0×10^8 + 0×10^9 = 0
       │  │  │  └──── 7×10^6 + 0×10^7 = 7000000
       │  │  └─────── 0×10^4 + 7×10^5 = 70000
       │  └────────── 4×10^2 + 0×10^3 = 400
       └───────────── 0×10^0 + 0×10^1 = 0
                      Total: 7074000 Hz = 7.074 MHz
```

**Exemple 2 : 433.500 MHz** (UHF)
```
433 500 000 Hz en BCD:
Octets: 00 00 50 33 04
       │  │  │  │  └─ 4×10^8 + 0×10^9 = 400000000
       │  │  │  └──── 3×10^6 + 3×10^7 = 33000000
       │  │  └─────── 5×10^4 + 0×10^5 = 50000
       │  └────────── 0×10^2 + 0×10^3 = 0
       └───────────── 0×10^0 + 0×10^1 = 0
                      Total: 433500000 Hz = 433.500 MHz
```

---

### 6.2 `trouver_messages_civ(buffer)`

**But** : Extraire les messages CI-V complets d'un buffer de réception.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `buffer` | `bytearray` | Buffer contenant les octets reçus |

**Retourne** : `list[bytes]` - Liste des messages CI-V complets

**Problème Résolu** :
Les données arrivent en paquets TCP arbitraires. Un message CI-V peut être :
- Complet dans un paquet
- Réparti sur plusieurs paquets
- Plusieurs messages dans un seul paquet

**Algorithme** :
```
1. Chercher le préambule FE FE
2. Vérifier que c'est bien un double FE (pas juste FE isolé)
3. Chercher le terminateur FD
4. Extraire le message complet
5. Supprimer du buffer
6. Répéter jusqu'à épuisement
```

**Illustration du Parsing** :
```
Buffer reçu (dump hexadécimal):
┌────────────────────────────────────────────────────────────┐
│ 00 00 FE FE E0 A4 03 00 00 00 45 01 FD FE FE E0 A4 27 ... │
└────────────────────────────────────────────────────────────┘
         ↑                              ↑  ↑
         │                              │  └─ Début message 2
         │                              └──── Fin message 1 (FD)
         └───────────────────────────────── Début message 1 (FE FE)

Après extraction:
Message 1: FE FE E0 A4 03 00 00 00 45 01 FD  (réponse fréquence)
Message 2: FE FE E0 A4 27 ... FD              (données spectre)
```

**Code Source** :
```python
def trouver_messages_civ(buffer):
    messages = []
    
    while True:
        # Chercher FE
        try:
            debut = buffer.index(0xFE)
        except ValueError:
            break  # Pas de FE
        
        # Supprimer déchets avant
        if debut > 0:
            del buffer[:debut]
        
        # Vérifier double FE
        if len(buffer) < 2:
            break
        if buffer[1] != 0xFE:
            del buffer[:1]  # Faux positif
            continue
        
        # Chercher FD (terminateur)
        try:
            fin = buffer.index(0xFD, 2) + 1
        except ValueError:
            break  # Message incomplet
        
        # Extraire et supprimer
        message = bytes(buffer[:fin])
        messages.append(message)
        del buffer[:fin]
    
    return messages
```

---

### 6.3 `extraire_donnees_spectre(message)`

**But** : Extraire les valeurs d'amplitude d'un message de spectre.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `message` | `bytes` | Message CI-V de spectre (commande 0x27) |

**Retourne** : 
- `numpy.array` - Tableau des amplitudes (valeurs 0-255)
- `None` - Si message invalide

**Structure d'un Message de Spectre (0x27)** :
```
Position    Contenu                Taille
─────────────────────────────────────────────
[0-1]       FE FE                  2 octets (préambule)
[2]         Destination            1 octet
[3]         Source                 1 octet
[4]         Commande (0x27)        1 octet
[5-18]      Métadonnées            14 octets (fréq, span, etc.)
[19...N-1]  Données d'amplitude    ~450-475 octets
[N]         FD                     1 octet (terminateur)
─────────────────────────────────────────────
Total: environ 470-495 octets
```

**Détail des Métadonnées (octets 5-18)** :
```
Octets 5-9    : Fréquence centrale (BCD, 5 octets)
Octets 10-11  : Span (largeur de bande)
Octets 12-13  : Fréquence de référence
Octets 14-18  : Autres paramètres (mode, etc.)
```

**Code Source** :
```python
def extraire_donnees_spectre(message):
    if len(message) < 50:
        return None
    
    # Amplitudes = tout après les métadonnées, avant FD
    donnees_brutes = message[19:-1]
    
    if len(donnees_brutes) < 10:
        return None
    
    amplitudes = np.array(list(donnees_brutes), dtype=float)
    return amplitudes
```

---

### 6.4 `redimensionner_spectre(amplitudes, taille_cible)`

**But** : Adapter le nombre de points du spectre pour l'affichage.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `amplitudes` | `numpy.array` | Tableau brut (~450 points) |
| `taille_cible` | `int` | Nombre de points souhaités (200) |

**Retourne** : `numpy.array` - Tableau redimensionné

**Méthode** : Sous-échantillonnage par sélection de points équidistants.

**Exemple** :
```
Entrée: 450 points (indices 0 à 449)
Sortie: 200 points

Indices sélectionnés = linspace(0, 449, 200)
                     = [0, 2.25, 4.5, 6.75, ..., 449]
                     → arrondi: [0, 2, 5, 7, ..., 449]
```

**Code Source** :
```python
def redimensionner_spectre(amplitudes, taille_cible):
    taille_originale = len(amplitudes)
    
    if taille_originale >= taille_cible:
        indices = np.linspace(0, taille_originale - 1, taille_cible, dtype=int)
        return amplitudes[indices]
    else:
        resultat = np.zeros(taille_cible)
        resultat[:taille_originale] = amplitudes
        return resultat
```

---

## 7. Fonctions d'Affichage

### 7.1 `creer_figure(freq_centrale)`

**But** : Créer la fenêtre graphique avec les deux graphiques.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `freq_centrale` | `float` | Fréquence centrale en MHz |

**Retourne** : `tuple` contenant :
| Index | Nom | Type | Description |
|-------|-----|------|-------------|
| 0 | `fig` | `Figure` | Fenêtre matplotlib |
| 1 | `ax_spectre` | `Axes` | Zone du graphique spectre |
| 2 | `ax_waterfall` | `Axes` | Zone du graphique waterfall |
| 3 | `ligne` | `Line2D` | Ligne du spectre (courbe) |
| 4 | `image` | `AxesImage` | Image du waterfall |
| 5 | `axe_freq` | `numpy.array` | Valeurs de l'axe X (fréquences) |

**Disposition de la Figure** :
```
┌────────────────────────────────────────────┐
│         Spectre IC-705 - 145.000 MHz       │
├────────────────────────────────────────────┤
│          ▲                                 │
│  Amplitude│      ~~~~~/\~~~~               │
│          │    ~~            ~~             │
│          │  ~~                ~~           │
│          └──────────┼──────────► Fréquence │
│              144.975│145.025 MHz           │
│                     │(ligne rouge)         │
├────────────────────────────────────────────┤
│                 Waterfall                  │
├────────────────────────────────────────────┤
│  Temps ▼  ████████████████████████         │
│          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓         │
│          ░░░░░░░░░░░░░░░░░░░░░░░░         │
│              (couleurs = amplitude)        │
└────────────────────────────────────────────┘
```

**Calcul de l'Axe des Fréquences** :
```python
demi_span = SPAN_KHZ / 2000          # 50/2000 = 0.025 MHz
freq_min = freq_centrale - demi_span  # 145.000 - 0.025 = 144.975
freq_max = freq_centrale + demi_span  # 145.000 + 0.025 = 145.025
axe_freq = np.linspace(freq_min, freq_max, 200)  # 200 points
```

---

### 7.2 `mettre_a_jour_affichage(ligne, image, spectre, waterfall, axe_freq)`

**But** : Mettre à jour les graphiques avec les nouvelles données.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `ligne` | `Line2D` | Ligne du spectre |
| `image` | `AxesImage` | Image du waterfall |
| `spectre` | `numpy.array` | Nouvelles amplitudes (1D, 200 points) |
| `waterfall` | `numpy.array` | Matrice complète (2D, 100×200) |
| `axe_freq` | `numpy.array` | Fréquences pour l'axe X |

**Retourne** : Rien (`None`)

**Code Source** :
```python
def mettre_a_jour_affichage(ligne, image, spectre, waterfall, axe_freq):
    ligne.set_data(axe_freq, spectre)  # MAJ courbe
    image.set_data(waterfall)           # MAJ image
    plt.draw()                          # Redessiner
    plt.pause(0.001)                    # Pause pour affichage
```

---

### 7.3 `faire_defiler_waterfall(waterfall, nouvelle_ligne)`

**But** : Faire défiler le waterfall et ajouter une nouvelle ligne.

**Paramètres** :
| Nom | Type | Description |
|-----|------|-------------|
| `waterfall` | `numpy.array` | Matrice 2D (100×200) |
| `nouvelle_ligne` | `numpy.array` | Spectre actuel (1D, 200 points) |

**Retourne** : Rien (`None`) - Modifie `waterfall` en place

**Principe du Défilement** :
```
AVANT:                          APRÈS:
Ligne 0: [A A A A A]           Ligne 0: [N N N N N]  ← Nouvelle
Ligne 1: [B B B B B]           Ligne 1: [A A A A A]  ← Ancien 0
Ligne 2: [C C C C C]           Ligne 2: [B B B B B]  ← Ancien 1
...                            ...
Ligne 99: [Z Z Z Z Z]          Ligne 99: [Y Y Y Y Y] ← Ancien 98
                                         ↓
                               [Z Z Z Z Z] est perdu
```

**Code Source** :
```python
def faire_defiler_waterfall(waterfall, nouvelle_ligne):
    waterfall[1:] = waterfall[:-1]  # Décaler vers le bas
    waterfall[0] = nouvelle_ligne   # Nouvelle ligne en haut
```

---

## 8. Fonction Principale

### 8.1 `main()`

**But** : Orchestrer l'exécution complète du programme.

**Paramètres** : Aucun

**Retourne** : Rien (`None`)

**Étapes d'Exécution** :

```
┌─────────────────────────────────────────┐
│         ÉTAPE 1: CONNEXION              │
├─────────────────────────────────────────┤
│ → Appel: connecter_au_serveur()         │
│ ← Retour: socket ou None                │
│ • Si None → arrêt du programme          │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│     ÉTAPE 2: ACTIVER LE STREAMING       │
├─────────────────────────────────────────┤
│ → Appel: activer_streaming(connexion)   │
│ • Envoie: FE FE A4 E0 1A 05 00 01 FD    │
│ • Attente: 0.5 seconde                  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│    ÉTAPE 2b: RÉCUPÉRER LA FRÉQUENCE     │
├─────────────────────────────────────────┤
│ → Appel: demander_frequence(connexion)  │
│ • Envoie: FE FE A4 E0 03 FD             │
│ • Reçoit: FE FE E0 A4 03 [freq] FD      │
│ → Appel: decoder_frequence_bcd()        │
│ ← freq_centrale ou FREQUENCE_DEFAUT     │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│       ÉTAPE 3: CRÉER L'AFFICHAGE        │
├─────────────────────────────────────────┤
│ → Appel: creer_figure(freq_centrale)    │
│ ← (fig, ax_spectre, ax_waterfall,       │
│    ligne, image, axe_freq)              │
│ • Initialise spectre et waterfall à 0   │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│        ÉTAPE 4: BOUCLE PRINCIPALE       │
├─────────────────────────────────────────┤
│ TANT QUE fenêtre ouverte:               │
│   │                                     │
│   ├─► Recevoir données TCP (timeout 0.1)│
│   │   └─► Ajouter au buffer             │
│   │                                     │
│   ├─► trouver_messages_civ(buffer)      │
│   │   └─► Liste de messages             │
│   │                                     │
│   └─► Pour chaque message:              │
│       │                                 │
│       ├─ Si commande == 0x27 (spectre): │
│       │   ├─► extraire_donnees_spectre()│
│       │   ├─► redimensionner_spectre()  │
│       │   ├─► faire_defiler_waterfall() │
│       │   └─► mettre_a_jour_affichage() │
│       │                                 │
│       └─ Sinon: ignorer le message      │
└─────────────────────────────────────────┘
                    │
                    ▼ (fenêtre fermée ou Ctrl+C)
┌─────────────────────────────────────────┐
│         ÉTAPE 5: NETTOYAGE              │
├─────────────────────────────────────────┤
│ → Appel: desactiver_streaming(connexion)│
│ • Envoie: FE FE A4 E0 1A 05 00 00 FD    │
│ → connexion.close()                     │
│ → plt.close('all')                      │
│ • Affiche le nombre total de trames     │
└─────────────────────────────────────────┘
```

---

## 9. Flux d'Exécution Complet

### Diagramme Temporel

```
Temps │
      │  PROGRAMME                 WFVIEW                  IC-705
──────┼──────────────────────────────────────────────────────────────
  0ms │  Démarrage
      │       │
 10ms │       ├──TCP Connect──────►│
      │       │◄─────Connexion OK──│
      │       │                    │
 50ms │       ├──FE FE A4 E0 1A 05 00 01 FD──►│────USB────►│
      │       │        (activer streaming)     │            │
      │       │                                │            │
100ms │       ├──FE FE A4 E0 03 FD────────────►│────────────►│
      │       │      (demande fréquence)       │            │
      │       │                                │            │
150ms │       │◄──FE FE E0 A4 03 [BCD] FD─────│◄───────────│
      │       │      (réponse fréquence)       │            │
      │       │                                │            │
200ms │  Créer figure matplotlib               │            │
      │       │                                │            │
      │  ┌────┴────────────────────────────────┴────────────┤
      │  │             BOUCLE PRINCIPALE                    │
      │  │                                                  │
250ms │  │   │◄──FE FE E0 A4 27 [...] FD─────│◄───────────│
      │  │   │       (données spectre #1)     │            │
      │  │   ├── Extraire amplitudes          │            │
      │  │   ├── Redimensionner               │            │
      │  │   ├── Mettre à jour graphiques     │            │
      │  │   │                                │            │
280ms │  │   │◄──FE FE E0 A4 27 [...] FD─────│◄───────────│
      │  │   │       (données spectre #2)     │            │
      │  │   │... (répéter ~30 fois/sec)...   │            │
      │  │                                                  │
      │  └────┬────────────────────────────────┬────────────┤
      │       │    (fermeture fenêtre)         │            │
      │       │                                │            │
      │       ├──FE FE A4 E0 1A 05 00 00 FD──►│────────────►│
      │       │      (désactiver streaming)    │            │
      │       │                                │            │
      │  Fermeture socket et fin programme     │            │
──────┴────────────────────────────────────────────────────────────
```

---

## 10. Exemples de Trames CI-V Détaillés

### 10.1 Trame d'Activation du Streaming

**Hexadécimal** : `FE FE A4 E0 1A 05 00 01 FD`

**Représentation Binaire** :
```
Octet │ Hex  │ Binaire    │ Décimal │ Signification
──────┼──────┼────────────┼─────────┼─────────────────
  0   │ FE   │ 1111 1110  │   254   │ Préambule
  1   │ FE   │ 1111 1110  │   254   │ Préambule
  2   │ A4   │ 1010 0100  │   164   │ Adresse IC-705
  3   │ E0   │ 1110 0000  │   224   │ Adresse PC
  4   │ 1A   │ 0001 1010  │    26   │ Cmd: Paramètres
  5   │ 05   │ 0000 0101  │     5   │ Sub: Streaming
  6   │ 00   │ 0000 0000  │     0   │ Paramètre fixe
  7   │ 01   │ 0000 0001  │     1   │ Valeur: ACTIVER
  8   │ FD   │ 1111 1101  │   253   │ Terminateur
```

---

### 10.2 Trame de Demande de Fréquence

**Hexadécimal** : `FE FE A4 E0 03 FD`

```
Octet │ Hex  │ Signification
──────┼──────┼───────────────────────────────────
  0   │ FE   │ Préambule
  1   │ FE   │ Préambule
  2   │ A4   │ Destination: IC-705
  3   │ E0   │ Source: PC
  4   │ 03   │ Commande: LIRE FRÉQUENCE
  5   │ FD   │ Terminateur
```

---

### 10.3 Trame de Réponse Fréquence (145.000 MHz)

**Hexadécimal** : `FE FE E0 A4 03 00 00 00 45 01 FD`

```
Octet │ Hex  │ Signification
──────┼──────┼───────────────────────────────────
  0   │ FE   │ Préambule
  1   │ FE   │ Préambule
  2   │ E0   │ Destination: PC (réponse inversée!)
  3   │ A4   │ Source: IC-705
  4   │ 03   │ Commande: LIRE FRÉQUENCE
  5   │ 00   │ Fréquence BCD octet 0 (Hz: 00)
  6   │ 00   │ Fréquence BCD octet 1 (kHz: 00)
  7   │ 00   │ Fréquence BCD octet 2 (kHz: 00)
  8   │ 45   │ Fréquence BCD octet 3 (MHz: 45)
  9   │ 01   │ Fréquence BCD octet 4 (MHz: 01)
 10   │ FD   │ Terminateur

Décodage BCD:
  00 → 0×1 + 0×10 = 0
  00 → 0×100 + 0×1000 = 0
  00 → 0×10000 + 0×100000 = 0
  45 → 5×1000000 + 4×10000000 = 45000000
  01 → 1×100000000 = 100000000
  
  Total = 145000000 Hz = 145.000 MHz
```

---

### 10.4 Trame de Réponse Fréquence (7.074 MHz - FT8)

**Hexadécimal** : `FE FE E0 A4 03 00 40 07 07 00 FD`

```
Octet │ Hex  │ Décodage BCD
──────┼──────┼────────────────────────────────────
  5   │ 00   │ 0×1 + 0×10 = 0
  6   │ 40   │ 0×100 + 4×1000 = 4000
  7   │ 07   │ 7×10000 + 0×100000 = 70000
  8   │ 07   │ 7×1000000 + 0×10000000 = 7000000
  9   │ 00   │ 0×100000000 = 0

Total = 0 + 4000 + 70000 + 7000000 + 0 = 7074000 Hz = 7.074 MHz
```

---

### 10.5 Trame de Spectre (0x27)

**Structure Générale** :
```
FE FE E0 A4 27 [14 octets métadonnées] [~450 octets amplitudes] FD
```

**Exemple Complet** (trame partielle pour illustration) :
```
FE FE E0 A4 27                        ← Entête (5 octets)
   00 00 00 45 01                     ← Fréq centrale BCD: 145.000 MHz
   32 00                              ← Span: 50 kHz (0x0032 = 50)
   xx xx xx xx xx xx xx               ← Autres métadonnées (7 octets)
   50 52 54 58 5A 5C 5E ...           ← Amplitudes (valeurs 0-255)
   ... (environ 450 octets) ...
   48 46 44 42 40
FD                                    ← Terminateur
```

**Décodage des Amplitudes** :
```
Valeur │ Hex  │ Signification
───────┼──────┼────────────────────────────
  80   │ 50   │ Amplitude faible (bruit)
  90   │ 5A   │ Signal faible
 120   │ 78   │ Signal moyen
 180   │ B4   │ Signal fort
 220   │ DC   │ Signal très fort
```

**Visualisation** :
```
Amplitude │
    255   │
    200   │      ▄▄
    150   │     ████
    100   │    ██████         ▄
     50   │  ████████████████████
      0   │──────────────────────── Fréquence
          144.975            145.025 MHz
```

---

## Annexe A : Résumé des Fonctions

| Fonction | Paramètres | Retour | Description |
|----------|------------|--------|-------------|
| `connecter_au_serveur()` | Aucun | `socket` ou `None` | Connexion TCP |
| `envoyer_commande(cnx, cmd)` | socket, list[int] | None | Envoie trame CI-V |
| `activer_streaming(cnx)` | socket | None | Active spectre |
| `desactiver_streaming(cnx)` | socket | None | Désactive spectre |
| `demander_frequence(cnx)` | socket | None | Demande fréquence |
| `decoder_frequence_bcd(octets)` | bytes(5) | float MHz | Décode BCD |
| `trouver_messages_civ(buf)` | bytearray | list[bytes] | Parse buffer |
| `extraire_donnees_spectre(msg)` | bytes | np.array ou None | Extrait amplitudes |
| `redimensionner_spectre(amp, n)` | np.array, int | np.array | Redimensionne |
| `creer_figure(freq)` | float MHz | tuple(6) | Crée graphiques |
| `mettre_a_jour_affichage(...)` | 5 params | None | MAJ graphiques |
| `faire_defiler_waterfall(wf, ln)` | np.array, np.array | None | Défilement |
| `main()` | Aucun | None | Programme principal |

---

## Annexe B : Glossaire

| Terme | Définition |
|-------|------------|
| **CI-V** | Communication Interface V - Protocole Icom |
| **BCD** | Binary Coded Decimal - Encodage numérique |
| **Little-Endian** | Octet de poids faible en premier |
| **Span** | Largeur de bande affichée |
| **Waterfall** | Affichage historique du spectre (cascade) |
| **Nibble** | Demi-octet (4 bits) |
| **wfview** | Logiciel passerelle TCP/IP vers IC-705 |
| **Préambule** | Octets de début de trame (FE FE) |
| **Terminateur** | Octet de fin de trame (FD) |

---

## Annexe C : Dépannage

| Problème | Cause Probable | Solution |
|----------|----------------|----------|
| "Erreur de connexion" | wfview pas lancé | Lancer wfview et activer le serveur |
| Pas de spectre | Streaming pas activé | Vérifier la trame d'activation |
| Fréquence erronée | Mauvais décodage BCD | Vérifier l'ordre little-endian |
| Affichage lent | Trop de données | Réduire LARGEUR_SPECTRE |
| Fenêtre noire | Pas de données | Vérifier connexion radio |

---

**Document généré le 16 décembre 2025**
**Version : 1.0**
**Programme : ic705_simple.py**
