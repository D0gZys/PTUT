# IC-705 Spectrum Display v4 — Documentation complète

## 📌 Description générale

**Fichier** : `ic705_tkinter_v4.py`  
**Langage** : Python 3  
**GUI** : Tkinter  
**Graphiques** : Matplotlib (backend `TkAgg`)  
**Réseau** : TCP client (socket)  
**Protocole radio** : CI‑V (Icom)

Ce programme affiche en temps réel :
- un **spectre** (courbe amplitude vs fréquence),
- un **waterfall** (historique du spectre dans le temps),
- et un **panneau de log** des trames CI‑V (hex) reçues/envoyées.

Il ne se connecte pas directement à la radio : il se connecte au **serveur CI‑V de wfview** (ou un serveur équivalent) qui fait passerelle entre l’ordinateur et l’Icom IC‑705.

---

## 🧭 Objectif du README

Ce document vise à expliquer le programme **de façon suffisamment détaillée** pour qu’une personne (ou une IA) qui ne connaît pas le projet puisse :
- comprendre le rôle de chaque section/fonction,
- comprendre le flux d’exécution (threads, timers Tkinter),
- comprendre le format des données (CI‑V, spectre, CSV),
- savoir lancer, utiliser, et diagnostiquer les problèmes fréquents.

---

## 📋 Table des matières

1. [Vue d’ensemble](#1-vue-densemble)  
2. [Prérequis](#2-prérequis)  
3. [Installation](#3-installation)  
4. [Utilisation (workflow)](#4-utilisation-workflow)  
5. [Configuration (constantes)](#5-configuration-constantes)  
6. [Protocole CI‑V (rappels + commandes)](#6-protocole-ci-v-rappels--commandes)  
7. [Architecture interne du programme](#7-architecture-interne-du-programme)  
8. [Interface graphique (widgets + logique)](#8-interface-graphique-widgets--logique)  
9. [Enregistrement CSV (normal + trigger)](#9-enregistrement-csv-normal--trigger)  
10. [Lecture / replay CSV](#10-lecture--replay-csv)  
11. [Performance et optimisations](#11-performance-et-optimisations)  
12. [Dépannage (troubleshooting)](#12-dépannage-troubleshooting)  
13. [Changelog (v4)](#13-changelog-v4)

---

## 1. Vue d’ensemble

### Schéma de communication

```
┌──────────┐     CI‑V (WiFi/USB)      ┌─────────┐      TCP:50002       ┌─────────────────────┐
│  IC‑705  │ ◄──────────────────────► │ wfview  │ ◄──────────────────► │ ic705_tkinter_v4.py │
│  (radio) │                          │ (srv)   │    CI‑V encapsulé    │ (GUI spectre/log)   │
└──────────┘                          └─────────┘                      └─────────────────────┘
```

### Ce que fait v4 (fonctionnel)

- Connexion à un serveur TCP CI‑V (par défaut `127.0.0.1:50002`).
- Envoi de commandes CI‑V minimales :
  - activer le **streaming spectre**,
  - demander périodiquement la **fréquence**.
- Réception continue de trames CI‑V :
  - `0x27` : trames contenant des données spectre,
  - `0x03` : trames contenant la fréquence (BCD),
  - autres : loggées selon filtres.
- Affichage temps réel :
  - spectre (ligne jaune),
  - waterfall (image `imshow`).
- Outils utilisateur :
  - sliders de gain min/max (échelle de l’affichage, pas la radio),
  - enregistrement CSV (mode normal),
  - enregistrement CSV déclenché (mode **Trigger**),
  - ouverture et replay d’un CSV (mode lecture).

### Ce que v4 ne fait pas

- Le programme **ne change pas la fréquence** de la radio (il lit/affiche la fréquence).
- Le programme n’interprète pas les amplitudes en unités physiques (dBm) : ce sont des valeurs brutes (0–255 typiquement).

---

## 2. Prérequis

### Matériel / réseau
- Un **Icom IC‑705** (ou équipement compatible CI‑V spectre).
- Un PC/Mac/Linux capable d’exécuter Python.
- La radio et l’ordinateur doivent être configurés pour communiquer via **wfview** (ou équivalent).

### Logiciels
- **Python 3** (idéalement 3.9+).
- **Tkinter** (souvent inclus, mais sur Linux il faut parfois installer `python3-tk`).
- Dépendances Python :
  - `numpy`
  - `matplotlib`
- **wfview** avec **Radio Server / CI‑V TCP** activé (port 50002 par défaut dans ce projet).

---

## 3. Installation

### 3.1 Environnement Python (recommandé)

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# ou: venv\Scripts\activate  # Windows
```

### 3.2 Dépendances

```bash
pip install numpy matplotlib
```

> Remarque : Tkinter n’est pas installable via `pip` sur la plupart des OS ; il dépend du package système Python/Tk.

---

## 4. Utilisation (workflow)

### 4.1 Lancer wfview

1. Lancer **wfview** et se connecter à la radio.
2. Activer le **Radio Server** et le **CI‑V** sur un port TCP (par défaut 50002).
3. Vérifier que wfview affiche bien la connexion à la radio.

### 4.2 Lancer l’application

```bash
python3 ic705_tkinter_v4.py
```

### 4.3 Workflow typique

1. Renseigner **IP** et **Port** (si nécessaire).
2. Cliquer **🔌 Connecter** :
   - la connexion TCP s’établit,
   - le streaming spectre est demandé,
   - une demande de fréquence est envoyée.
3. Cliquer **▶ Démarrer** :
   - démarre le thread de réception,
   - démarre les boucles Tkinter (affichage + log).
4. Ajuster les sliders **Gain Min / Gain Max** pour optimiser la lisibilité.
5. (Optionnel) Cliquer **⏺ REC** :
   - mode normal : un CSV continu est créé,
   - mode Trigger : enregistre uniquement quand un signal dépasse le seuil.
6. (Optionnel) Cliquer **📂 Open CSV** pour rejouer un enregistrement (mode lecture).

---

## 5. Configuration (constantes)

Les principales constantes sont en haut de `ic705_tkinter_v4.py` :

```python
SERVEUR_IP = "127.0.0.1"
SERVEUR_PORT = 50002
ADRESSE_RADIO = 0xA4
ADRESSE_PC = 0xE0
FREQUENCE_DEFAUT = 7.100
SPAN_KHZ = 200
LARGEUR_SPECTRE = 950
PROFONDEUR_WATERFALL = 80
MAX_LOG_LINES = 200
LOG_UPDATE_INTERVAL = 300
MAX_TRAMES_PAR_UPDATE = 15
DOSSIER_CSV = "recep_csv"
```

### Interprétation

- `SERVEUR_IP` / `SERVEUR_PORT` : serveur TCP CI‑V (souvent wfview en local).
- `ADRESSE_RADIO` / `ADRESSE_PC` : adresses CI‑V usuelles (IC‑705 = `0xA4`, contrôleur = `0xE0`).
- `SPAN_KHZ` : largeur de spectre **affichée** autour de la fréquence centrale.
  - Conversion utilisée dans le code : `demi_span_mhz = SPAN_KHZ / 2000`.
  - Exemple `SPAN_KHZ=200` ⇒ axe X = `freq_centrale ± 0.1 MHz`.
- `LARGEUR_SPECTRE` : nombre de points affichés (et enregistrés en CSV). En v4 : **950** (plus détaillé, CSV plus large).
- `PROFONDEUR_WATERFALL` : nombre de lignes historiques (80 en v4 pour limiter le coût CPU/RAM).
- `LOG_UPDATE_INTERVAL` : fréquence de rafraîchissement du panneau log (ms).

---

## 6. Protocole CI‑V (rappels + commandes)

### 6.1 Format général d’une trame CI‑V

```
FE FE [TO] [FROM] [CMD] [DATA...] FD
```

- `FE FE` : préambule (début de trame)
- `TO` : destination (radio)
- `FROM` : source (PC)
- `CMD` : commande principale (1 octet)
- `DATA...` : données (longueur variable)
- `FD` : fin de trame

### 6.2 Commandes utilisées dans v4

| Commande | Code | Sens | Usage dans v4 |
|---|---:|---|---|
| Lire fréquence | `0x03` | PC→Radio | envoyée à la connexion + périodiquement |
| Réponse fréquence | `0x03` | Radio→PC | décodée (BCD) pour mettre à jour l’axe |
| Streaming ON | `0x1A 0x05 0x00 0x01` | PC→Radio | envoyée lors de `connecter()` |
| Streaming OFF | `0x1A 0x05 0x00 0x00` | PC→Radio | envoyée lors de `deconnecter()` |
| Spectre | `0x27` | Radio→PC | extraite et affichée / enregistrée |
| OK / NG | `0xFB` / `0xFA` | Radio→PC | affichées dans le log (si filtres) |

### 6.3 Fréquence encodée en BCD (fonction `decoder_frequence_bcd`)

La réponse fréquence contient 5 octets de BCD “little‑endian” (poids faibles d’abord).
La fonction :
- lit 5 octets,
- reconstruit la fréquence en Hz,
- retourne la fréquence en MHz.

### 6.4 Extraction des messages du flux TCP (fonction `trouver_messages_civ`)

Le socket renvoie un flux d’octets (pas “une trame par recv”).  
La stratégie :
1. Chercher `FE FE` (début).
2. Chercher `FD` (fin).
3. Extraire la trame complète, la retirer du buffer.
4. Répéter tant qu’il reste des trames complètes.

### 6.5 Extraction des amplitudes spectre (fonction `extraire_donnees_spectre`)

Pour la commande `0x27`, le code considère que :
- les amplitudes commencent à l’index **19** de la trame,
- et s’arrêtent juste avant `FD`.

> Important : cette “position 19” dépend du format exact des trames envoyées par votre serveur (wfview).  
> Si vous observez un spectre incohérent (valeurs quasi constantes, ou bruit “plat”), il faut souvent ajuster cet offset.

---

## 7. Architecture interne du programme

### 7.1 Organisation (haut niveau)

`ic705_tkinter_v4.py` contient :
1. Des **constantes** de configuration.
2. Des **fonctions utilitaires** (décodage CI‑V, parsing, resampling, hex).
3. Une classe principale **`IC705AppV4`** qui :
   - construit l’interface Tkinter,
   - gère la connexion TCP,
   - reçoit/parse les trames dans un thread,
   - met à jour les graphes via des timers Tkinter,
   - enregistre et rejoue des CSV.

### 7.2 Dépendances (imports) et rôle

```python
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import socket, threading, time
import numpy as np
import csv, os
from datetime import datetime
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
```

- `socket` : connexion TCP vers wfview.
- `threading` : réception asynchrone (la GUI ne doit pas bloquer).
- `numpy` : stockage/manipulation rapide du spectre + waterfall.
- `matplotlib` : rendu du spectre et du waterfall dans Tkinter.
- `csv` : enregistrement et replay.

### 7.3 Threading et synchronisation

Le programme utilise 2 “modes” d’exécution :

1) **Mode temps réel (radio)**  
- Thread secondaire : `boucle_reception()` lit le socket et met à jour les données.
- Thread principal (Tkinter) :
  - `boucle_affichage()` rafraîchit les graphes ~25 FPS (toutes les 40 ms).
  - `boucle_log()` injecte les trames du buffer de log dans le widget texte.

2) **Mode lecture CSV**  
- Pas de socket, pas de thread réception.
- Les contrôles Tkinter naviguent dans `donnees_csv` et reconstruisent l’affichage.

#### Pourquoi des `Lock` ?

Le thread réception écrit pendant que la GUI lit.
Deux verrous protègent :
- `lock_donnees` : `spectre_actuel`, `waterfall_data`, `nouvelles_donnees`
- `lock_trames` : la file `trames_a_logger` (trames à afficher)

### 7.4 Pipeline de données (temps réel)

```
socket.recv() -> buffer -> trouver_messages_civ()
    -> pour chaque msg:
         - log (timestamp/type/hex) -> trames_a_logger
         - si 0x03: nouvelle_frequence
         - si 0x27: amplitudes -> redimensionner_spectre()
                    -> spectre_actuel + waterfall_data
                    -> (optionnel) enregistrer_spectre()
GUI:
  boucle_affichage() lit spectre_actuel/waterfall_data et dessine
  boucle_log() vide trames_a_logger et les injecte dans Text
```

### 7.5 Fonctions utilitaires (détails)

#### `decoder_frequence_bcd(data: bytes) -> float`

- **Entrée** : 5 octets (BCD little‑endian) provenant d’une réponse `0x03`.
- **Sortie** : fréquence en **MHz** (float).
- **Comportement** : si `len(data) < 5`, retourne `FREQUENCE_DEFAUT`.

#### `trouver_messages_civ(buffer: bytearray) -> list[bytes]`

- **Entrée** : buffer alimenté par `socket.recv()`.
- **Sortie** : liste de trames CI‑V complètes (du `FE FE` au `FD`).
- **Effet de bord** : consomme le buffer (retire les octets extraits).

#### `extraire_donnees_spectre(msg: bytes) -> np.ndarray | None`

- **But** : extraire les amplitudes d’une trame `0x27`.
- **Retour** : `np.ndarray(dtype=float32)` ou `None` si la trame est trop courte.
- **Découpage utilisé** : `msg[19:len(msg)-1]`.

#### `redimensionner_spectre(donnees: np.ndarray, largeur_cible: int) -> np.ndarray`

- **But** : obtenir exactement `largeur_cible` points (ici `LARGEUR_SPECTRE`).
- Si la trame fournit **plus** de points : sous‑échantillonnage par indices.
- Si elle fournit **moins** de points : interpolation linéaire (`np.interp`).

#### `trame_vers_hex(msg: bytes) -> str`

- Convertit une trame binaire en hex lisible (ex : `FE FE A4 E0 03 FD`).

#### `identifier_type_trame(msg: bytes) -> str`

- Traduit `msg[4]` en libellé (ex : `SPECTRE` pour `0x27`, `Freq` pour `0x03`).

### 7.6 Classe `IC705AppV4` — variables d’état principales

Attributs importants :

- **Connexion / exécution** : `connexion`, `connecte`, `affichage_actif`, `thread_reception`
- **Fréquence** : `freq_centrale`, `nouvelle_frequence`
- **Spectre / waterfall** : `spectre_actuel`, `waterfall_data`, `nouvelles_donnees`, `lock_donnees`
- **Log CI‑V** : `trames_a_logger`, `lock_trames`, `compteur_trames_total`, `log_spectre`, `log_autres`, `log_actif`
- **Gain (visualisation)** : `gain_min`, `gain_max`
- **CSV écriture** : `enregistrement_actif`, `fichier_csv`, `writer_csv`, `nom_fichier_csv`, `nb_lignes_csv`
- **Trigger** : `trigger_actif`, `seuil_trigger`, `au_dessus_seuil`, `nb_fichiers_trigger`
- **CSV lecture** : `mode_lecture_csv`, `donnees_csv`, `index_lecture`, `lecture_en_cours`

### 7.7 Flux d’exécution détaillé

#### Démarrage

`ic705_tkinter_v4.py` instancie `IC705AppV4`, construit l’UI puis entre dans `root.mainloop()`.

#### Connexion (bouton “Connecter”)

`connecter()` :
- ouvre le socket TCP,
- envoie une commande “Streaming ON”,
- envoie une demande de fréquence `0x03`,
- tente de lire une réponse immédiate pour initialiser `freq_centrale`.

#### Temps réel (bouton “Démarrer”)

`lancer_affichage()` :
- démarre le thread `boucle_reception()` (réception/parsing),
- démarre `boucle_affichage()` (≈ 25 FPS) et `boucle_log()` via `root.after()`.

`boucle_reception()` (thread) :
- lit le flux TCP, reconstruit les trames (`trouver_messages_civ`),
- met à jour `nouvelle_frequence` (si `0x03`) et les buffers spectre/waterfall (si `0x27`),
- pousse des entrées dans `trames_a_logger` pour l’affichage du log,
- après ~2 secondes cumulées de timeouts (aucune donnée reçue) : renvoie une demande de fréquence.

`boucle_affichage()` (Tkinter) :
- applique `nouvelle_frequence` si nécessaire (axe X + labels),
- affiche `spectre_actuel` et `waterfall_data` si une nouvelle frame est prête,
- utilise le blitting si disponible, sinon `draw_idle()`.

`boucle_log()` (Tkinter) :
- vide `trames_a_logger` et appelle `ajouter_trames_batch()` (filtrage + insertion).

---

## 8. Interface graphique (widgets + logique)

### 8.1 Disposition globale

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Titre | IP | Port | [Connecter] | [Démarrer] | [REC] | Trigger > [seuil] | [Open CSV] | ... │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Gain Min [slider]  Gain Max [slider]  Plage [...]                                         │
├───────────────────────────────────────────────────────────────┬───────────────────────────┤
│ Spectre (matplotlib)                                           │ Log CI‑V (Text + filtres) │
│ Waterfall (matplotlib)                                         │ Total / Affichées         │
└───────────────────────────────────────────────────────────────┴───────────────────────────┘
```

### 8.2 Contrôles de connexion

- **IP / Port** (`entry_ip`, `entry_port`) : destination TCP.
- **🔌 Connecter** (`btn_connecter`) :
  - ouvre le socket,
  - envoie `Streaming ON`,
  - envoie une demande de fréquence,
  - met l’UI en état “connecté”.
- **▶ Démarrer** (`btn_afficher`) :
  - lance le thread de réception,
  - démarre `boucle_affichage()` et `boucle_log()`.

### 8.3 Sliders de gain

Les sliders modifient :
- l’échelle Y du spectre (`ax_spectre.set_ylim(gain_min, gain_max)`),
- l’échelle de couleurs du waterfall (`image_waterfall.set_clim(vmin, vmax)`).

Ils ne changent pas les données reçues, uniquement la visualisation.

### 8.4 Panneau de log CI‑V

Le log affiche :
- les trames reçues (avec type déduit de `msg[4]`),
- les trames envoyées (ex : “Activation streaming”, “Demande fréquence”).

Fonctions clés :
- **Filtrage** : afficher/cacher `SPECTRE (0x27)` et/ou “Autres”.
- **⏸ / ▶** : pause du log : les trames reçues ne sont plus ajoutées au widget (et ne seront donc pas “rattrapées” ensuite), mais `compteur_trames_total` continue d’augmenter côté thread réception.
- **🗑 Clear** : efface le widget texte et remet le compteur.

> Note : les trames envoyées loggées via `log_trame_envoyee()` sont écrites directement dans le widget texte (elles ne passent pas par la file `trames_a_logger`).

Optimisations :
- insertion en batch (`ajouter_trames_batch`) au lieu d’une insertion par trame en continu,
- limitation :
  - `MAX_TRAMES_PAR_UPDATE` trames max par rafraîchissement,
  - `MAX_LOG_LINES` lignes max dans le widget.

---

## 9. Enregistrement CSV (normal + trigger)

### 9.1 Dossier et nommage

Les CSV sont écrits dans `recep_csv/` (`DOSSIER_CSV`).

- Mode normal : `spectre_YYYYMMDD_HHMMSS.csv`
- Mode trigger : `trigger_YYYYMMDD_HHMMSS_mmm.csv` (un fichier par “événement”)

### 9.2 Format du CSV v4

En v4, `LARGEUR_SPECTRE = 950`, donc :
- 3 colonnes “métadonnées”,
- + 950 colonnes `val_0 ... val_949`,
⇒ **953 colonnes** au total.

Exemple (simplifié) :

```csv
timestamp,freq_mhz,span_khz,val_0,val_1,...,val_949
2025-12-17 10:51:32.123,145.050000,200,12.0,13.0,...,18.0
```

Colonnes :
- `timestamp` : horodatage local (précision ms)
- `freq_mhz` : fréquence centrale affichée au moment de l’écriture
- `span_khz` : `SPAN_KHZ` (sert à reconstruire l’axe X)
- `val_i` : amplitude du point `i` (float formaté à 1 décimale)

### 9.3 Mode normal

Quand vous cliquez **⏺ REC** (sans Trigger) :
- un fichier est créé immédiatement,
- chaque trame spectre (`0x27`) produit une ligne CSV.

### 9.4 Mode Trigger

Quand vous cochez **Trigger >** et cliquez **⏺ REC** :
- aucun fichier n’est créé tant que le signal est sous le seuil,
- à la première trame dont `max(spectre) >= seuil` :
  - un nouveau CSV `trigger_...csv` est créé,
  - les lignes sont écrites tant que le signal reste au‑dessus,
- quand `max(spectre)` repasse sous le seuil :
  - le fichier est fermé,
  - l’application repasse en attente d’un prochain événement.

Ce mode est utile pour capturer uniquement des signaux “intéressants”.

---

## 10. Lecture / replay CSV

### 10.1 Entrer en mode lecture

Le bouton **📂 Open CSV** :
1. stoppe l’affichage si nécessaire,
2. se déconnecte si nécessaire,
3. ouvre un sélecteur de fichier,
4. charge tout le fichier en mémoire dans `donnees_csv`.

Pendant le mode lecture :
- les contrôles réseau sont désactivés (IP/Port/Connect),
- une barre “📼 Lecture CSV” apparaît au-dessus du graphe.

### 10.2 Contrôles disponibles

- `⏮` : début
- `◀` : reculer de 10 lignes
- `▶ Play / ⏸ Pause` : lecture automatique
- `▶` : avancer de 10 lignes
- `⏭` : fin
- Slider position : aller à une ligne précise
- Slider vitesse (1–50) : définit le délai de lecture (≈ 200ms → 4ms)

### 10.3 Reconstruction du waterfall en lecture

À chaque position `index_lecture`, le programme reconstruit un waterfall “local” :
- prend les `PROFONDEUR_WATERFALL` dernières lignes disponibles,
- les place de haut en bas (ligne la plus récente en haut).

### 10.4 Compatibilité des CSV

Le lecteur CSV exige que chaque ligne contienne au minimum `3 + LARGEUR_SPECTRE` colonnes.

Conséquence :
- un CSV généré par v3 (ex : 475 points) **ne se charge pas** en v4 (950 points),
- un CSV généré par v4 ne se charge pas en v3.

Solutions possibles si vous devez relire d’anciens fichiers :
- temporairement modifier `LARGEUR_SPECTRE` dans le code pour correspondre au CSV,
- ou écrire un script de conversion/rééchantillonnage (hors scope de ce programme).

---

## 11. Performance et optimisations

### 11.1 Fréquences de rafraîchissement

- Affichage (spectre + waterfall) : toutes les **40 ms** (≈ 25 FPS).
- Log CI‑V : toutes les **300 ms** (réduit le coût CPU du widget `Text`).

### 11.2 Blitting Matplotlib

Le dessin utilise le **blitting** quand possible :
- on sauvegarde un “background” (`copy_from_bbox`),
- à chaque frame on restaure le background puis on redessine seulement :
  - la ligne du spectre,
  - l’image du waterfall.

Si le blitting échoue (selon backend/OS), le programme repasse en mode `draw_idle()`.

### 11.3 Tailles de buffers

- `waterfall_data` : `80 x 950` floats (mise à jour par glissement + insertion).
- `trames_a_logger` : limité à ~100 éléments en attente côté thread réception.
- widget log : limité à ~`MAX_LOG_LINES` lignes (avec purge).

---

## 12. Dépannage (troubleshooting)

### 12.1 “Impossible de se connecter”

Vérifier :
- wfview tourne et le **Radio Server** est activé,
- l’IP/port dans l’UI correspondent,
- aucun pare‑feu ne bloque le port,
- la radio est bien connectée dans wfview.

### 12.2 Connecté mais pas de spectre

Causes fréquentes :
- le streaming n’est pas activé côté serveur,
- le serveur n’envoie pas `0x27` (configuration wfview),
- l’offset d’extraction (`idx_start = 19`) ne correspond pas à vos trames.

Pour diagnostiquer :
- activer le log “Spectre (0x27)” et observer si des trames `SPECTRE` arrivent,
- vérifier que la taille des trames `0x27` est importante (>> 50 octets).

### 12.3 Problèmes Matplotlib/Tkinter

Sur Linux, si Tkinter manque :
- installer `python3-tk` (package système).

Si Matplotlib n’affiche rien :
- vérifier que `matplotlib.use('TkAgg')` est bien exécuté (c’est forcé dans v4),
- vérifier que vous lancez le script avec la même version de Python que celle où `matplotlib` est installée.

### 12.4 Le CSV ne s’ouvre pas

Vérifier :
- que le fichier a bien `3 + LARGEUR_SPECTRE` colonnes (v4 = 953),
- qu’il n’est pas corrompu,
- que les valeurs numériques utilisent bien le séparateur `.` (point), pas `,`.

---

## 13. Changelog (v4)

Par rapport aux versions précédentes (ex : v3), v4 met l’accent sur :
- **résolution spectre augmentée** (`LARGEUR_SPECTRE = 950`),
- **waterfall moins profond** (performance),
- panneau log optimisé (batch, limites, filtres, pause),
- affichage optimisé via **blitting**.
