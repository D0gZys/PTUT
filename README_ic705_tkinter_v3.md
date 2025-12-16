# IC-705 Spectrum Display v3 - Documentation Complète

## 📋 Description Générale

**Fichier** : `ic705_tkinter_v3.py`  
**Langage** : Python 3  
**Interface** : Tkinter + Matplotlib  
**Protocole** : CI-V (Icom Communication Interface V)  

Ce programme est une application graphique permettant de visualiser en temps réel le spectre radio et le waterfall (cascade) reçus depuis un transceiver **Icom IC-705** via le serveur **wfview**. Il communique avec la radio en utilisant le protocole CI-V sur une connexion TCP.

---

## 🏗️ Architecture du Programme

### Dépendances
```python
import tkinter as tk                    # Interface graphique
from tkinter import messagebox, ttk, filedialog
import socket                            # Communication TCP
import threading                         # Réception asynchrone
import time
import numpy as np                       # Traitement des données spectre
import csv                               # Enregistrement CSV
import os
from datetime import datetime
import matplotlib                        # Graphiques
matplotlib.use('TkAgg')                  # Backend obligatoire pour macOS
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
```

### Constantes de Configuration
```python
SERVEUR_IP = "127.0.0.1"      # Adresse du serveur wfview
SERVEUR_PORT = 50002           # Port TCP CI-V de wfview
ADRESSE_RADIO = 0xA4           # Adresse CI-V de l'IC-705
ADRESSE_PC = 0xE0              # Adresse CI-V du contrôleur (PC)
FREQUENCE_DEFAUT = 7.100       # Fréquence par défaut (MHz)
SPAN_KHZ = 200                 # Largeur du span spectral (kHz)
LARGEUR_SPECTRE = 475          # Nombre de points du spectre
PROFONDEUR_WATERFALL = 100     # Nombre de lignes du waterfall
DOSSIER_CSV = "recep_csv"      # Dossier de sauvegarde des enregistrements
```

---

## 📡 Protocole CI-V

### Structure d'une Trame CI-V
```
FE FE [TO] [FROM] [CMD] [DATA...] FD
```
- `FE FE` : Préambule (début de trame)
- `TO` : Adresse destination (0xA4 pour IC-705)
- `FROM` : Adresse source (0xE0 pour PC)
- `CMD` : Code commande
- `DATA` : Données (optionnel, longueur variable)
- `FD` : Fin de trame

### Commandes CI-V Utilisées

| Code | Nom | Direction | Description |
|------|-----|-----------|-------------|
| `0x03` | Freq | PC→Radio | Demande la fréquence courante |
| `0x03` | Freq | Radio→PC | Réponse avec fréquence en BCD (5 octets) |
| `0x27` | Spectre | Radio→PC | Données spectre (~475 octets d'amplitude) |
| `0x1A 0x05 0x00 0x01` | Config | PC→Radio | Active le streaming spectre |
| `0x1A 0x05 0x00 0x00` | Config | PC→Radio | Désactive le streaming spectre |
| `0xFB` | OK | Radio→PC | Acquittement positif |
| `0xFA` | NG | Radio→PC | Acquittement négatif (erreur) |

### Décodage Fréquence BCD
La fréquence est encodée en BCD inversé sur 5 octets :
```
Octet 0: Hz (unités, dizaines)
Octet 1: Hz (centaines), kHz (unités)
Octet 2: kHz (dizaines, centaines)
Octet 3: MHz (unités, dizaines)
Octet 4: MHz (centaines), 10MHz
```
Exemple : `00 50 45 14 00` = 145.050000 MHz

---

## 🖥️ Interface Graphique

### Disposition
```
┌─────────────────────────────────────────────────────────────────────┐
│ [Titre] [IP] [Port] [Connecter] [Démarrer] [REC] [Trigger>__] [CSV] │
├─────────────────────────────────────────────────────────────────────┤
│ [Gain Min: ────] [Gain Max: ────] Plage: [20-120]                   │
├─────────────────────────────────────────────────────────────────────┤
│ [Barre de lecture CSV - si mode lecture actif]                      │
├────────────────────────────────────────────────┬────────────────────┤
│                                                │  Trames CI-V       │
│         SPECTRE (graphique ligne)              │  Reçues            │
│                                                │                    │
│         Fréquence centrale en rouge            │  [□ Spectre]       │
│                                                │  [☑ Autres]        │
├────────────────────────────────────────────────┤  [⏸] [🗑 Clear]   │
│                                                │                    │
│         WATERFALL (image colorée)              │  HH:MM:SS.mmm      │
│                                                │  [TYPE] FE FE...   │
│         Temps ↓                                │                    │
│                                                │                    │
└────────────────────────────────────────────────┴────────────────────┘
```

### Widgets Principaux

| Widget | Type | Description |
|--------|------|-------------|
| `entry_ip` | Entry | Adresse IP du serveur wfview |
| `entry_port` | Entry | Port TCP (défaut: 50002) |
| `btn_connecter` | Button | Connexion/Déconnexion |
| `btn_afficher` | Button | Démarrer/Arrêter l'affichage |
| `btn_enregistrer` | Button | Démarrer/Arrêter l'enregistrement CSV |
| `cb_trigger` | Checkbutton | Active le mode trigger |
| `entry_seuil` | Entry | Seuil du trigger (amplitude) |
| `btn_ouvrir_csv` | Button | Ouvrir un fichier CSV enregistré |
| `slider_min` | Scale | Gain minimum (0-150) |
| `slider_max` | Scale | Gain maximum (50-255) |
| `text_log` | Text | Affichage des trames CI-V en hex |

---

## 🔧 Fonctions Principales

### Décodage CI-V

#### `decoder_frequence_bcd(data)`
Convertit 5 octets BCD en fréquence MHz.
```python
# Entrée: bytes([0x00, 0x50, 0x45, 0x14, 0x00])
# Sortie: 145.05 (MHz)
```

#### `trouver_messages_civ(buffer)`
Parse un buffer et extrait tous les messages CI-V complets.
- Cherche le préambule `FE FE`
- Cherche la fin `FD`
- Retourne liste de messages, nettoie le buffer

#### `extraire_donnees_spectre(msg)`
Extrait les amplitudes d'une trame spectre (commande 0x27).
- Les données commencent à l'octet 14
- Retourne un array numpy de float32

#### `redimensionner_spectre(donnees, largeur_cible)`
Interpole le spectre à la largeur souhaitée (475 points).

#### `identifier_type_trame(msg)`
Retourne le nom de la commande CI-V (Freq, SPECTRE, OK, NG, etc.)

---

## 📊 Classe IC705App

### Variables d'État
```python
self.connexion          # Socket TCP
self.connecte           # Bool: état connexion
self.affichage_actif    # Bool: réception en cours
self.freq_centrale      # Float: fréquence centrale (MHz)
self.spectre_actuel     # np.array: dernières amplitudes
self.waterfall_data     # np.array 2D: historique pour waterfall
self.nouvelles_donnees  # Bool: flag mise à jour graphique
self.nouvelle_frequence # Float: fréquence reçue (thread-safe)
```

### Variables Enregistrement CSV
```python
self.enregistrement_actif   # Bool
self.fichier_csv            # File handle
self.writer_csv             # csv.writer
self.nom_fichier_csv        # String: chemin fichier
self.nb_lignes_csv          # Int: compteur lignes
```

### Variables Trigger
```python
self.trigger_actif      # tk.BooleanVar
self.seuil_trigger      # Float: seuil d'amplitude
self.au_dessus_seuil    # Bool: état courant
self.nb_fichiers_trigger # Int: compteur fichiers créés
```

### Variables Lecture CSV
```python
self.mode_lecture_csv   # Bool
self.donnees_csv        # List[dict]: données chargées
self.index_lecture      # Int: position courante
self.lecture_en_cours   # Bool: lecture automatique
```

---

## 🔄 Flux d'Exécution

### 1. Connexion
```
[Connecter] → connecter()
    ├── Ouvre socket TCP vers wfview
    ├── Envoie: FE FE A4 E0 1A 05 00 01 FD (active streaming)
    ├── Envoie: FE FE A4 E0 03 FD (demande fréquence)
    └── Met à jour interface
```

### 2. Démarrage Affichage
```
[Démarrer] → lancer_affichage()
    ├── Démarre thread: boucle_reception()
    ├── Démarre timer: mettre_a_jour_affichage() (30ms)
    └── Démarre timer: mettre_a_jour_log() (200ms)
```

### 3. Boucle de Réception (Thread Secondaire)
```python
boucle_reception():
    while affichage_actif:
        data = socket.recv(4096)
        messages = trouver_messages_civ(buffer)
        
        for msg in messages:
            # Log dans file d'attente
            trames_a_logger.append(...)
            
            # Si commande 0x03 (fréquence)
            if msg[4] == 0x03:
                nouvelle_frequence = decoder_frequence_bcd(msg[5:10])
            
            # Si commande 0x27 (spectre)
            if msg[4] == 0x27:
                spectre = extraire_donnees_spectre(msg)
                waterfall_data = roll(waterfall_data)
                waterfall_data[0] = spectre
                
                if enregistrement_actif:
                    enregistrer_spectre(spectre)
        
        # Toutes les 2 secondes, demander la fréquence
        if compteur >= 20:
            socket.send([FE FE A4 E0 03 FD])
```

### 4. Mise à Jour Affichage (Thread Principal)
```python
mettre_a_jour_affichage():  # Appelé toutes les 30ms
    if nouvelle_frequence changed:
        mettre_a_jour_axe_freq()
        label_freq.config(text=...)
    
    if nouvelles_donnees:
        ligne.set_data(axe_freq, spectre_actuel)
        image.set_data(waterfall_data)
        canvas.draw_idle()
```

---

## 💾 Enregistrement CSV

### Format du Fichier
```csv
timestamp,freq_mhz,span_khz,val_0,val_1,...,val_474
2025-12-16 14:30:52.123,145.050000,200,45.2,46.1,...
```

### Mode Normal
- Un seul fichier `spectre_YYYYMMDD_HHMMSS.csv`
- Enregistre toutes les trames spectre reçues

### Mode Trigger
- Crée un nouveau fichier `trigger_YYYYMMDD_HHMMSS_mmm.csv` à chaque passage au-dessus du seuil
- Arrête l'enregistrement quand le signal repasse en-dessous
- Permet de capturer uniquement les signaux intéressants

```python
enregistrer_spectre(spectre):
    if trigger_actif:
        max_signal = np.max(spectre)
        
        if max_signal >= seuil_trigger:
            if not au_dessus_seuil:
                creer_nouveau_csv_trigger()  # Nouveau fichier
            ecrire_ligne_csv(spectre)
        else:
            if au_dessus_seuil:
                fermer_csv_trigger()  # Fermer fichier
    else:
        ecrire_ligne_csv(spectre)  # Mode normal
```

---

## 📂 Lecture CSV

### Chargement
```python
ouvrir_csv():
    donnees_csv = []
    for row in csv_reader:
        donnees_csv.append({
            'timestamp': row[0],
            'freq': float(row[1]),
            'span': int(row[2]),
            'spectre': np.array(row[3:478])
        })
```

### Navigation
- **Slider** : Position dans le fichier
- **⏮ ◀ ▶ ⏭** : Navigation rapide
- **▶ Play** : Lecture automatique
- **Vitesse** : 1-50x (délai 200ms à 4ms)

### Reconstruction Waterfall
```python
charger_donnees_csv():
    # Prend les 100 dernières lignes pour le waterfall
    start_idx = max(0, index_lecture - PROFONDEUR_WATERFALL + 1)
    for i in range(start_idx, index_lecture + 1):
        waterfall_data[i] = donnees_csv[i]['spectre']
```

---

## ⚠️ Points Techniques Importants

### Thread Safety
- La réception socket est dans un **thread secondaire**
- Les variables partagées (`spectre_actuel`, `waterfall_data`, `nouvelle_frequence`) sont modifiées par le thread
- La mise à jour GUI utilise `root.after()` pour rester dans le **thread principal**
- File d'attente `trames_a_logger` protégée par `threading.Lock()`

### Compatibilité macOS
- `matplotlib.use('TkAgg')` **obligatoire** avant tout import matplotlib
- Les boutons utilisent `highlightbackground` au lieu de `bg/fg` (bug macOS)
- Pas de `plt.show()` depuis un thread (crash NSWindow)

### Performance
- Graphiques mis à jour à 30ms (~33 FPS)
- Log des trames mis à jour à 200ms (5 FPS)
- Maximum 10 trames loggées par update
- Buffer de log limité à 200 lignes

---

## 🚀 Utilisation

### Prérequis
1. **wfview** installé et connecté à l'IC-705
2. Serveur CI-V de wfview activé sur port 50002
3. Python 3 avec: `numpy`, `matplotlib`, `tkinter`

### Lancement
```bash
python3 ic705_tkinter_v3.py
```

### Workflow Typique
1. Lancer wfview et connecter l'IC-705
2. Lancer `ic705_tkinter_v3.py`
3. Cliquer **Connecter**
4. Cliquer **Démarrer**
5. Ajuster les gains avec les sliders
6. (Optionnel) Cliquer **REC** pour enregistrer
7. (Optionnel) Cocher **Trigger** et définir un seuil

---

## 📁 Structure des Fichiers Générés

```
recep_csv/
├── spectre_20251216_143052.csv      # Enregistrement normal
├── trigger_20251216_143105_123.csv  # Trigger #1
├── trigger_20251216_143112_456.csv  # Trigger #2
└── ...
```

---

## 🔗 Connexions et Dépendances

```
┌─────────────┐     USB/WiFi      ┌─────────────┐
│   IC-705    │ ←───────────────→ │   wfview    │
└─────────────┘                   └──────┬──────┘
                                         │ TCP:50002
                                         │ CI-V
                                  ┌──────┴──────┐
                                  │ ic705_tkinter│
                                  │    _v3.py   │
                                  └─────────────┘
```

---

## 📝 Changelog

### Version 3
- Panneau de log des trames CI-V en hexadécimal
- Enregistrement CSV avec timestamps précis
- Mode Trigger pour enregistrement conditionnel
- Lecture et replay des fichiers CSV
- Mise à jour automatique de la fréquence centrale
- Interface optimisée pour macOS

---

## 👤 Auteur

Projet PTUT - IUT  
Développé pour l'étude du protocole CI-V Icom et la visualisation spectrale.
