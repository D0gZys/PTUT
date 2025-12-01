# PTUT - Contrôle IC-705 via Python & Spectrogramme

Projet de contrôle à distance de l'Icom IC-705 via WiFi en utilisant Python et wfview.

## 📋 Description

Ce projet comprend :
- **Contrôle de l'IC-705** via protocole rigctld (Hamlib) et CI-V natif
- **Spectrogramme audio** avec `waterfall_compact.py` qui enregistre le flux audio de wfview et génère un CSV contenant le spectrogramme

## 🚀 Installation

### Prérequis
- Python 3.9+
- wfview configuré et connecté à l'IC-705
- L'IC-705 en mode point d'accès WiFi

### Installation des dépendances

```bash
# Créer l'environnement virtuel
python3 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Installer les packages
pip install --upgrade pip
pip install numpy sounddevice matplotlib pyserial
```

## 📡 Contrôle IC-705

### Méthode 1 : rigctld (Hamlib) - Recommandé ⚡

```bash
venv/bin/python ic705_final.py
```

Protocole simple avec commandes texte. Récupère la fréquence instantanément.

### Méthode 2 : CI-V hexadécimal - Contrôle bas niveau 🔧

```bash
venv/bin/python ic705_civ_multi.py
```

Protocole CI-V natif avec commandes hexadécimales pures (`FE FE A4 E0 03 FD`).

### Exemples de commandes CI-V

- **Lire la fréquence** : `FE FE A4 E0 03 FD`
- **Définir 145.000 MHz** : `FE FE A4 E0 05 00 00 00 45 01 FD`
- **Lire le mode** : `FE FE A4 E0 04 FD`

## 📊 Spectrogramme Audio

## Utilisation de base

Lancer un enregistrement de 30 secondes et écrire `waterfall_compact.csv` :

```bash
python waterfall_compact.py --duration 30
```

Enregistrement continu (Ctrl+C pour arrêter) avec visualisation en temps réel :

```bash
python waterfall_compact.py --device "BlackHole 2ch" --duration 0 --live-plot
```

## Acquisition live avec sauvegarde automatique

Pour lancer directement l’acquisition live (visualisation temps réel) et sauvegarder automatiquement un CSV dans le dossier `csv` lorsque vous quittez :

```bash
python waterfall_compact.py --live --device "BlackHole 2ch"
```

Un fichier nommé `csv/waterfall_YYYYMMDD-HHMMSS.csv` est créé à l’arrêt. Vous pouvez ajuster le dossier de sauvegarde avec `--save-dir` ou spécifier un nom précis via `--outfile`.

### Exemple avec recentrage fréquentiel

Le mode live peut également être centré sur une fréquence donnée tout en enregistrant le CSV :

```bash
python waterfall_compact.py --device "BlackHole 2ch" --duration 0 --live-plot --center-freq 145000000 --span-hz 20000000
```

Ici, la visualisation est recentrée autour de 145 MHz avec une bande de 20 MHz, et les données sont toujours sauvegardées automatiquement dans `csv/`.

## Choisir le périphérique audio

Lister les entrées reconnues (repérez « BlackHole 2ch » si vous l’utilisez) :

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Exemple pour sélectionner explicitement BlackHole :

```bash
python waterfall_compact.py --device "BlackHole 2ch" --duration 0 --live-plot
# ou via l’index (par ex. 3)
python waterfall_compact.py --device 3 --duration 60
```

Au démarrage, le script affiche le périphérique réellement ouvert :

```
Input device: BlackHole 2ch (index=3, max_channels=2, default_rate=44100.0)
```

## Options principales

- `--duration` : durée en secondes (`0` ou négatif = en continu).
- `--outfile` : chemin du CSV de sortie (défaut : `waterfall_compact.csv`, ou fichier horodaté dans `csv/` en mode live).
- `--save-dir` : dossier de sauvegarde automatique lorsque `--live`/`--live-plot` est actif (défaut : `csv`).
- `--samplerate`, `--nfft`, `--hop`, `--amplitude-floor` : paramètres FFT.
- `--live-plot` : active l’affichage temps réel (nécessite `matplotlib`).
- `--live` : active `--live-plot` et crée un CSV automatique dans `--save-dir` à l’arrêt.
- `--plot-frames` : nombre de trames conservées pour la fenêtre glissante de la visualisation.

## Nettoyage / fin de session

Si vous utilisez un virtualenv :

```bash
deactivate
```

Les fichiers générés sont simplement les CSV (et éventuellement des copies que vous faites). Aucune rotation automatique n’est appliquée dans la version compacte.

## 🔧 Configuration wfview

### Pour rigctld (port 4532)
1. Settings → External Control → Cocher "Enable RigCtld"
2. Port : 4532
3. Save Settings

### Pour CI-V (port 50002)  
1. Settings → Radio Server → Cocher "Enable"
2. Civ Port : 50002
3. Save Settings + Redémarrer wfview

## 🛠️ Diagnostic

Test de connectivité des ports :
```bash
venv/bin/python diagnostic_wfview.py
```

## 📁 Fichiers du projet

| Fichier | Description |
|---------|-------------|
| `ic705_final.py` | Contrôle via rigctld - Simple et rapide |
| `ic705_civ_multi.py` | Contrôle via CI-V hexadécimal |
| `ic705_control.py` | Version complète série/réseau |
| `waterfall_compact.py` | Spectrogramme audio temps réel |
| `diagnostic_wfview.py` | Test des ports wfview |

## 👤 Auteur

Projet réalisé dans le cadre d'un PTUT



