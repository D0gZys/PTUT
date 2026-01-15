# 🌠 IC-705 Meteor Detection System

## Projet PTUT - Détection d'Échos Météores par Analyse Spectrale

Ce projet permet la détection et l'enregistrement d'échos météores en utilisant un transceiver Icom IC-705 comme récepteur SDR. Le système analyse le spectre radio en temps réel et enregistre automatiquement les événements détectés.

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture du système](#architecture-du-système)
3. [Installation](#installation)
4. [Configuration matérielle](#configuration-matérielle)
5. [ic705_tkinter_v8.py - Application principale](#ic705_tkinter_v8py---application-principale)
6. [csv_reader.py - Visualiseur d'enregistrements](#csv_readerpy---visualiseur-denregistrements)
7. [Format des données CSV](#format-des-données-csv)
8. [Calibration dBm](#calibration-dbm)
9. [Mode Trigger](#mode-trigger)
10. [Dépannage](#dépannage)

---

## 🔭 Vue d'ensemble

### Principe de fonctionnement

Les météores entrant dans l'atmosphère créent des traînées ionisées qui réfléchissent brièvement les ondes radio. En surveillant une fréquence connue (comme une balise ou une station FM lointaine), on peut détecter ces réflexions sous forme de pics de signal soudains.

### Composants du projet

| Fichier | Description |
|---------|-------------|
| `ic705_tkinter_v8.py` | Application principale d'acquisition et d'affichage en temps réel |
| `csv_reader.py` | Lecteur et visualiseur des enregistrements CSV |
| `recep_csv/` | Dossier contenant les enregistrements organisés par date |

---

## 🏗 Architecture du système

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│   IC-705    │────▶│   wfview    │────▶│ ic705_tkinter_v8 │
│   (Radio)   │ USB │   (Proxy)   │ TCP │    (Python)      │
└─────────────┘     └─────────────┘     └──────────────────┘
                          │                      │
                     Port 50002            ┌─────┴─────┐
                                           │           │
                                      Affichage    CSV Files
                                      Temps Réel   (Triggers)
```

### Flux de données

1. **IC-705** : Envoie les données spectre via protocole CI-V sur USB
2. **wfview** : Agit comme proxy TCP, relayant les trames CI-V sur le port 50002
3. **ic705_tkinter_v8.py** : 
   - Se connecte au proxy TCP
   - Décode les trames CI-V
   - Convertit les valeurs brutes en dBm
   - Affiche le spectre et le waterfall
   - Enregistre les événements (mode Trigger ou continu)

---

## 💻 Installation

### Prérequis

- Python 3.8 ou supérieur
- wfview installé et configuré
- IC-705 connecté via USB

### Dépendances Python

```bash
pip install numpy matplotlib
```

### Création d'un environnement virtuel (recommandé)

```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

pip install numpy matplotlib
```

---

## 📻 Configuration matérielle

### Configuration de l'IC-705

1. **Activer le mode Scope** :
   - Menu → SET → Function → Scope ON

2. **Régler le SPAN du scope** :
   - Menu → SCOPE → SPAN → ±2.5 kHz (ou selon vos besoins)
   - Un span étroit donne une meilleure résolution fréquentielle

3. **Régler le niveau de référence** :
   - Menu → SCOPE → REF Level → -77 dBm (valeur calibrée)

4. **Connexion USB** :
   - Connecter l'IC-705 au PC via USB
   - Installer les drivers Icom si nécessaire

### Configuration de wfview

1. Lancer wfview
2. Se connecter à l'IC-705 via USB
3. Activer le serveur CI-V :
   - Settings → Server → Enable CI-V Server
   - Port : **50002** (par défaut)
4. Laisser wfview tourner en arrière-plan

---

## 📊 ic705_tkinter_v8.py - Application principale

### Lancement

```bash
python ic705_tkinter_v8.py
```

### Interface utilisateur

```
┌─────────────────────────────────────────────────────────────────┐
│  [Connecter]  [⏺ REC]  [☑ Trigger >] [-130] dBm   ⚪ Non connecté │
├─────────────────────────────────────────────────────────────────┤
│  Min (dBm): [====|====]  Max (dBm): [====|====]  │ Min: -158.0   │
│             -160    -60             -160    -60  │ Max: -142.3   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     GRAPHIQUE SPECTRE                           │
│            Amplitude (dBm) vs Fréquence (MHz)                   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     WATERFALL                                   │
│              Temps défilant verticalement                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Boutons et contrôles

| Contrôle | Description |
|----------|-------------|
| **Connecter/Déconnecter** | Établit ou ferme la connexion avec wfview |
| **⏺ REC / ⏹ STOP** | Démarre ou arrête l'enregistrement CSV |
| **☑ Trigger** | Active le mode trigger (enregistrement sur événement) |
| **Seuil (dBm)** | Niveau de déclenchement du trigger |
| **Slider Min** | Niveau minimum de l'échelle d'affichage (-160 à -60 dBm) |
| **Slider Max** | Niveau maximum de l'échelle d'affichage (-160 à -60 dBm) |

### Paramètres configurables (dans le code)

```python
# Connexion
SERVEUR_IP = "127.0.0.1"      # Adresse du serveur wfview
SERVEUR_PORT = 50002           # Port TCP de wfview

# Spectre
FREQUENCE_DEFAUT = 7.100       # Fréquence centrale par défaut (MHz)
SPAN_KHZ = 2.5                 # Span d'affichage (kHz)
LARGEUR_SPECTRE = 475          # Nombre de points du spectre
PROFONDEUR_WATERFALL = 100     # Nombre de lignes du waterfall

# Calibration dBm
REF_LEVEL_DEFAULT = -77        # Niveau de référence (dBm)
RAW_MAX = 160                  # Valeur brute maximale
DYNAMIC_RANGE = 80             # Plage dynamique (dB)

# Trigger
TRIGGER_PRE_LINES = 200        # Lignes AVANT le trigger
TRIGGER_POST_LINES = 200       # Lignes APRÈS le trigger

# Affichage
DBM_MIN_DEFAULT = -160         # Min par défaut (dBm)
DBM_MAX_DEFAULT = -80          # Max par défaut (dBm)
WF_CMAP = "inferno"            # Colormap du waterfall
```

### Affichage

- **Spectre** : Courbe verte montrant l'amplitude en fonction de la fréquence
- **Waterfall** : Représentation temps-fréquence avec code couleur (inferno)
- **Ligne rouge** : Fréquence centrale
- **Stats** : Min/Max du spectre en temps réel

---

## 📖 csv_reader.py - Visualiseur d'enregistrements

### Lancement

```bash
python csv_reader.py
```

### Interface utilisateur

```
┌─────────────────────────────────────────────────────────────────┐
│  [📂 Ouvrir CSV]  [🖼️ Exporter]  fichier.csv    │ 400 lignes    │
├─────────────────────────────────────────────────────────────────┤
│  [⏮][⏪] [▶ Play] [⏩][⏭]  Position: [=====|=====] 1/400  1x    │
├─────────────────────────────────────────────────────────────────┤
│  Min (dBm): [====|====]  Max (dBm): [====|====]  │ Time: 14:32:15│
├─────────────────────────────────────────────────────────────────┤
│                     GRAPHIQUE SPECTRE                           │
├─────────────────────────────────────────────────────────────────┤
│                     WATERFALL (200 lignes)                      │
│                  Timestamps sur l'axe Y                         │
└─────────────────────────────────────────────────────────────────┘
```

### Fonctionnalités

| Fonction | Description |
|----------|-------------|
| **📂 Ouvrir CSV** | Charger un fichier CSV d'enregistrement |
| **🖼️ Exporter** | Exporter le waterfall COMPLET en image PNG/JPG/PDF |
| **⏮ Début** | Aller à la première ligne |
| **⏪ -10** | Reculer de 10 lignes |
| **▶ Play/Pause** | Lecture automatique animée |
| **⏩ +10** | Avancer de 10 lignes |
| **⏭ Fin** | Aller à la dernière ligne |
| **Slider Position** | Navigation rapide dans le fichier |
| **Vitesse** | 0.25x, 0.5x, 1x, 2x, 4x, 10x |

### Export du Waterfall

Le bouton **🖼️ Exporter** génère une image contenant :
- Le waterfall **COMPLET** (toutes les lignes du CSV, pas seulement les 200 visibles)
- Colorbar avec échelle dBm
- Axes avec fréquence centrale complète
- Titre avec timestamps de début et fin
- Format : PNG (150 DPI), JPG ou PDF

---

## 📁 Format des données CSV

### Structure des dossiers

```
recep_csv/
├── 20260115/                          # Dossier du jour (YYYYMMDD)
│   ├── spectre_143052.csv             # Enregistrement continu
│   ├── trigger_-130dBm_143215_max-95dBm.csv   # Trigger
│   └── trigger_-130dBm_144532_max-88dBm.csv   # Autre trigger
├── 20260116/
│   └── ...
```

### Nommage des fichiers

| Type | Format du nom |
|------|---------------|
| **Spectre continu** | `spectre_HHMMSS.csv` |
| **Trigger** | `trigger_[seuil]dBm_HHMMSS_max[puissance_max]dBm.csv` |

Exemple : `trigger_-130dBm_143215_max-95dBm.csv`
- Seuil de déclenchement : -130 dBm
- Heure : 14:32:15
- Puissance maximale mesurée : -95 dBm

### Format du fichier CSV

```csv
timestamp,freq_mhz,span_khz,ref_level_dbm,dbm_0,dbm_1,dbm_2,...,dbm_474
14:32:15.123456,143.049000,2.5,-77,-158.5,-157.0,-156.5,...,-155.0
14:32:15.163456,143.049000,2.5,-77,-158.0,-156.5,-155.0,...,-154.5
```

| Colonne | Description |
|---------|-------------|
| `timestamp` | Horodatage HH:MM:SS.ffffff |
| `freq_mhz` | Fréquence centrale (MHz) |
| `span_khz` | Span (kHz) |
| `ref_level_dbm` | Niveau de référence (dBm) |
| `dbm_0` à `dbm_474` | 475 points de données spectrales (dBm) |

---

## 📐 Calibration dBm

### Mesures de référence

La calibration a été effectuée avec un générateur de signal :

| Signal injecté | Valeur brute (raw) |
|----------------|-------------------|
| -110 dBm | 93 |
| -90 dBm | 133 |
| -80 dBm | 153 |
| -77 dBm (REF) | 160 (maximum) |

### Formule de conversion

```
dBm = REF_LEVEL - (RAW_MAX - raw_value) × SCALE_DB_PER_POINT
```

Avec les valeurs calibrées :
- `REF_LEVEL = -77 dBm`
- `RAW_MAX = 160`
- `SCALE_DB_PER_POINT = 0.5 dB/point`

### Table de conversion

| Raw | dBm |
|-----|-----|
| 160 | -77 (REF, maximum) |
| 153 | -80.5 |
| 133 | -90.5 |
| 93 | -110.5 |
| 6 | -154 |
| 0 | -157 (plancher bruit) |

### Plancher de bruit

Avec une antenne connectée, le plancher de bruit mesuré est autour de **-157 à -160 dBm** (valeurs brutes 0-6).

---

## 🎯 Mode Trigger

### Principe

Le mode Trigger permet d'enregistrer uniquement les événements intéressants (échos météores) :

1. **Attente** : Le système surveille le niveau maximum du spectre
2. **Déclenchement** : Quand le max dépasse le seuil, l'enregistrement commence
3. **Pre-buffer** : Les 200 lignes AVANT le déclenchement sont sauvegardées
4. **Enregistrement** : Toutes les lignes pendant l'événement sont enregistrées
5. **Post-buffer** : 200 lignes APRÈS que le signal redescende sous le seuil
6. **Fermeture** : Le fichier est renommé avec la puissance max mesurée

### Configuration

```python
TRIGGER_PRE_LINES = 200    # ~8 secondes avant (à 25 fps)
TRIGGER_POST_LINES = 200   # ~8 secondes après
```

### Utilisation

1. Cocher **☑ Trigger**
2. Entrer le seuil de déclenchement (ex: **-130 dBm**)
3. Cliquer sur **⏺ REC**
4. Le système affiche "TRIGGER: attente > -130 dBm"
5. Quand un signal fort est détecté, l'enregistrement se fait automatiquement
6. Le fichier est nommé avec le seuil et la puissance max

### Choix du seuil

- **Trop bas** (ex: -150 dBm) : Beaucoup de faux positifs (bruit)
- **Trop haut** (ex: -90 dBm) : Rate les échos faibles
- **Recommandé** : 20-30 dB au-dessus du plancher de bruit
  - Plancher : -160 dBm → Seuil : **-130 à -140 dBm**

---

## 🔧 Dépannage

### Problème : "Non connecté"

**Causes possibles :**
1. wfview n'est pas lancé
2. Le serveur CI-V n'est pas activé dans wfview
3. Mauvais port (vérifier 50002)
4. L'IC-705 n'est pas connecté à wfview

**Solutions :**
```bash
# Vérifier que le port est ouvert
netstat -an | findstr 50002
```

### Problème : Pas de données spectre

**Causes possibles :**
1. Le scope n'est pas activé sur l'IC-705
2. Le streaming scope n'est pas activé

**Solution :**
- Sur l'IC-705 : Menu → SET → Function → Scope ON

### Problème : Valeurs dBm incorrectes

**Causes possibles :**
1. REF_LEVEL mal réglé sur l'IC-705
2. Calibration à refaire

**Solution :**
- Vérifier le REF_LEVEL sur l'IC-705 (doit être -77 dBm pour la calibration actuelle)
- Ou recalibrer avec un générateur de signal

### Problème : Fichiers CSV non créés

**Causes possibles :**
1. Permissions d'écriture
2. Dossier `recep_csv` inaccessible

**Solution :**
```bash
# Créer le dossier manuellement
mkdir recep_csv
```

### Problème : Interface lente/saccadée

**Causes possibles :**
1. Trop de données à afficher
2. Ordinateur trop lent

**Solutions :**
- Réduire `PROFONDEUR_WATERFALL` (ex: 50 au lieu de 100)
- Fermer les autres applications

---

## 📊 Performances

| Paramètre | Valeur typique |
|-----------|----------------|
| Fréquence de rafraîchissement | ~25 fps |
| Points par spectre | 475 |
| Résolution fréquentielle (span 2.5 kHz) | ~5.3 Hz/point |
| Taille d'un fichier trigger (400 lignes) | ~1.5 MB |
| Latence affichage | < 50 ms |

---

## 📜 Licence

Projet PTUT - Usage éducatif

---

## 👥 Auteurs

Projet réalisé dans le cadre du PTUT (Projet Tuteuré)

---

## 🔗 Références

- [Icom IC-705](https://www.icomjapan.com/lineup/products/IC-705/)
- [wfview](https://wfview.org/)
- [Protocole CI-V Icom](https://www.icomjapan.com/support/)
- [Détection d'échos météores](https://www.imo.net/radio/)
