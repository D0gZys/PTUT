# IC-705 Spectrum Display

Affichage en temps réel du spectre et waterfall de l'Icom IC-705 via le protocole CI-V.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 📋 Description

**ic705_final.py** est une application Python optimisée qui affiche en temps réel :
- 📊 **Spectre RF** avec ligne de fréquence centrale
- 🌊 **Waterfall** style wfview avec colormap personnalisée
- 🎛️ **Contrôle de fréquence** via interface graphique

L'application communique avec l'IC-705 via le serveur CI-V de **wfview** (Radio Server).

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|----------------|-------------|
| 🚀 **Threading** | Réception et affichage séparés pour fluidité maximale |
| 📡 **Protocole CI-V** | Communication native avec l'IC-705 |
| 🎨 **Style wfview** | Colormap bleu → cyan → jaune → orange |
| ⚡ **Optimisé** | Buffers pré-alloués, numpy vectorisé |
| 🔄 **Temps réel** | ~15-30 FPS selon la configuration |
| 📍 **Ligne centrale** | Indicateur visuel de la fréquence de réception |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    IC705SpectrumApp                         │
│                   (Application principale)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    Queue    ┌─────────────────┐           │
│  │ CIVReceiver │ ─────────▶  │ SpectrumDisplay │           │
│  │  (Thread)   │   spectre   │   (Matplotlib)  │           │
│  └──────┬──────┘             └────────┬────────┘           │
│         │                             │                     │
│         │ callback                    │ pending_freq        │
│         ▼                             ▼                     │
│  ┌─────────────┐             ┌─────────────────┐           │
│  │ CIVProtocol │◀────────────│   Contrôles UI  │           │
│  │  (CI-V)     │  cmd_set    │ (TextBox+Button)│           │
│  └──────┬──────┘             └─────────────────┘           │
│         │                                                   │
└─────────┼───────────────────────────────────────────────────┘
          │ TCP Socket
          ▼
    ┌───────────┐         ┌─────────┐
    │  wfview   │◀───────▶│ IC-705  │
    │  (50002)  │  WiFi   │         │
    └───────────┘         └─────────┘
```

## 🔧 Prérequis

### Matériel
- **Icom IC-705** avec WiFi activé
- Ordinateur sur le même réseau

### Logiciels
- **Python 3.9+**
- **wfview** avec Radio Server activé sur le port 50002
- Connexion établie entre wfview et l'IC-705

## 📦 Installation

### 1. Cloner le projet

```bash
git clone https://github.com/D0gZys/PTUT.git
cd PTUT
```

### 2. Créer l'environnement virtuel

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# ou
venv\Scripts\activate     # Windows
```

### 3. Installer les dépendances

```bash
pip install numpy matplotlib
```

## ⚙️ Configuration

### wfview Radio Server

1. Ouvrir **wfview** et se connecter à l'IC-705
2. Aller dans **Settings → Server**
3. Activer **Radio Server** sur le port **50002**
4. Cocher **Enable CI-V**

### Configuration du programme

Modifier la classe `Config` dans `ic705_final.py` si nécessaire :

```python
@dataclass
class Config:
    HOST: str = '127.0.0.1'      # IP du serveur wfview
    PORT: int = 50002            # Port CI-V
    SPAN_KHZ: int = 50           # Largeur du span (kHz)
    NUM_POINTS: int = 200        # Résolution du spectre
    WATERFALL_DEPTH: int = 150   # Profondeur du waterfall
    RADIO_ADDR: int = 0xA4       # Adresse CI-V de l'IC-705
    CTRL_ADDR: int = 0xE0        # Adresse du contrôleur
```

## 🚀 Utilisation

### Lancer l'application

```bash
python3 ic705_final.py
```

### Interface

```
============================================================
IC-705 Spectrum Display - Version Optimisée
============================================================
✅ Connecté à 127.0.0.1:50002
✅ Fréquence initiale: 145.500000 MHz
✅ Streaming spectral activé

🎯 Affichage en temps réel... (Fermez la fenêtre pour arrêter)

  100 trames | 25.3 FPS
  200 trames | 24.8 FPS
```

### Changer de fréquence

1. Entrer la fréquence en MHz dans la zone de texte (ex: `145.500`)
2. Appuyer sur **Entrée** ou cliquer sur **Appliquer**
3. L'IC-705 change de fréquence et l'affichage se met à jour

## 📁 Structure des fichiers

```
PTUT/
├── ic705_final.py          # 🎯 Application principale (optimisée)
├── ic705_spectrum_live.py  # Version précédente
├── ic705_spectrum_optimized.py
├── waterfall_compact.py    # Spectrogramme audio
├── README.md              
└── venv/                   # Environnement virtuel
```

## 🔬 Protocole CI-V

### Format des messages

```
┌────┬────┬──────┬──────┬─────┬──────────┬────┐
│ FE │ FE │ TO   │ FROM │ CMD │ DATA     │ FD │
└────┴────┴──────┴──────┴─────┴──────────┴────┘
       │     │      │      │       │
       │     │      │      │       └─ Données (optionnel)
       │     │      │      └─ Commande (0x03=freq, 0x27=spectre...)
       │     │      └─ Adresse source (0xE0=PC)
       │     └─ Adresse destination (0xA4=IC-705)
       └─ Préambule
```

### Commandes utilisées

| Commande | Code | Description |
|----------|------|-------------|
| Lire fréquence | `0x03` | Retourne 5 bytes BCD |
| Écrire fréquence | `0x05` | Envoie 5 bytes BCD |
| Streaming ON | `0x1A 0x05 0x00 0x01` | Active le spectre |
| Streaming OFF | `0x1A 0x05 0x00 0x00` | Désactive le spectre |
| Données spectre | `0x27` | Trame de ~475 bytes |

### Encodage BCD de la fréquence

La fréquence est encodée en **BCD little-endian** sur 5 bytes :

```
Exemple: 145.500000 MHz = 145500000 Hz

Hz:  1  4  5  5  0  0  0  0  0  0
     │  │  │  │  │  │  │  │  │  │
BCD: [00][00][50][55][41] (little-endian)
```

## 🎨 Personnalisation

### Colormap du waterfall

Modifier `WFVIEW_COLORS` pour changer les couleurs :

```python
WFVIEW_COLORS = [
    (0.0, 0.0, 0.15),    # Bleu très foncé (bruit)
    (0.0, 0.0, 0.4),     # Bleu foncé
    (0.0, 0.6, 0.9),     # Bleu clair
    (0.0, 0.85, 1.0),    # Cyan
    (1.0, 0.9, 0.0),     # Jaune
    (1.0, 0.3, 0.0),     # Orange
]
```

### Couleur du spectre

```python
self.line, = self.ax1.plot(..., color='#FFFF00', ...)  # Jaune
```

### Ligne de fréquence centrale

```python
self.center_line = self.ax1.axvline(..., color="#FF0000", ...)  # Rouge
```

## 🐛 Dépannage

### Erreur de connexion

```
❌ Erreur connexion: Connection refused
```

**Solutions :**
1. Vérifier que wfview est lancé et connecté à l'IC-705
2. Vérifier que le Radio Server est activé (port 50002)
3. Vérifier l'IP dans `Config.HOST`

### Pas de spectre affiché

```
✅ Streaming spectral activé
(mais pas de données)
```

**Solutions :**
1. Sur l'IC-705, activer le scope : **MENU → SET → Function → Scope**
2. Vérifier que le scope est visible sur wfview

### FPS faible

**Solutions :**
1. Réduire `NUM_POINTS` (ex: 100)
2. Réduire `WATERFALL_DEPTH` (ex: 100)
3. Fermer les autres applications

## 📊 Performances

| Configuration | FPS moyen |
|--------------|-----------|
| NUM_POINTS=200, DEPTH=150 | ~20-25 FPS |
| NUM_POINTS=100, DEPTH=100 | ~30-40 FPS |
| NUM_POINTS=300, DEPTH=200 | ~10-15 FPS |

## 📜 Licence

MIT License - Voir [LICENSE](LICENSE)

## 👤 Auteur

**Thomas Gibelin** - [@D0gZys](https://github.com/D0gZys)

## 🙏 Remerciements

- [wfview](https://wfview.org/) - Logiciel de contrôle radio
- [Icom](https://www.icomjapan.com/) - Protocole CI-V
- Communauté radioamateur



