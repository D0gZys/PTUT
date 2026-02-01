# IC705 Qt (C/C++/Qt 6) — README technique

Ce dossier contient la version **C/C++/Qt 6/QML** du projet IC‑705 (portage progressif des scripts Python).

## Objectif de cette version

Priorité absolue : **fonctionnel** avant esthétique.

Phase 1 (fonctionnelle) :
- Connexion wfview (TCP CI‑V)
- Décodage CI‑V (fréquence, ref level, spectre)
- Conversion dBm
- Spectre et waterfall en QML/Scene Graph
- Enregistrement CSV conforme (à venir)
- Lecture CSV conforme (en cours, déjà fonctionnelle)

## Arborescence

```
ic705_qt/
  CMakeLists.txt
  README.md
  run_debug.ps1
  src/
    main.cpp
    civ_client.h/.cpp
    spectrum_model.h/.cpp
    spectrum_item.h/.cpp
    waterfall_model.h/.cpp
    waterfall_item.h/.cpp
    csv_replay.h/.cpp
  qml/
    CMakeLists.txt
    Main.qml
  assets/   (réservé)
  tests/    (réservé)
  cmake/    (réservé)
```

## Dépendances

- Qt 6.11.x (MSVC 2022)
- Visual Studio Build Tools 2022 / Visual Studio 2026 Community
- CMake 3.21+
- Windows 10/11 SDK

Composants Qt utilisés :
- Qt6::Core
- Qt6::Gui
- Qt6::Qml
- Qt6::Quick
- Qt6::QuickControls2
- Qt6::QuickDialogs2

## Build & Run (Windows / MSVC)

Depuis `ic705_qt/` :

```powershell
cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DCMAKE_PREFIX_PATH="C:\Qt\6.11.0\msvc2022_64"
cmake --build build --config Debug
.\run_debug.ps1
```

`run_debug.ps1` ajoute automatiquement `C:\Qt\6.11.0\msvc2022_64\bin` au `PATH`.

## Journal d’exécution

Un log est écrit ici :

```
ic705_qt/build/Debug/ic705_qt_run.log
```

## Architecture logicielle (résumé)

### 1) Acquisition CI‑V (Live)

**Classe** : `CivClient`

- Connexion TCP vers `127.0.0.1:50002`
- Commandes CI‑V :
  - `0x27 0x10` (Scope stream ON/OFF)
  - `0x03` (Freq)
  - `0x27 0x19` (Ref level)
- Extraction des trames : préambule `FE FE` → fin `FD`
- Décodage fréquence BCD → MHz
- Décodage ref level (BCD signé)
- Décodage spectre :
  - Les données commencent à l’offset **19**
  - Conversion brute → dBm :
    ```
    dBm = REF_LEVEL_DEFAULT - (RAW_MAX - raw) * 0.5
    ```
  - Redimensionnement à 475 points

### 2) Modèles de données

**Spectre**
- `SpectrumModel`
- Stocke un vecteur de 475 floats (dBm)
- `setSamples()` pour injecter le live ou le replay

**Waterfall**
- `WaterfallModel`
- Image `QImage` 475x200 (ARGB32)
- Ajout d’une ligne en haut (scroll)
- Colormap identique au projet Python (wfview)

### 3) Rendu QML / Scene Graph

- `SpectrumItem` : `QQuickItem` + `QSGGeometryNode` (LineStrip)
- `WaterfallItem` : `QQuickItem` + `QSGSimpleTextureNode`
- QML **sans logique métier** ; UI basique

### 4) Replay CSV

**Classe** : `CsvReplay`

- Chargement CSV format Python (`timestamp,freq_mhz,span_khz,ref_level_dbm,dbm_0..dbm_474`)
- Navigation `< / >`
- Play/Pause + vitesse
- Slider de position
- Reconstruction waterfall quand on recule

## Format CSV (rappel)

```
timestamp,freq_mhz,span_khz,ref_level_dbm,dbm_0,dbm_1,...,dbm_474
14:32:15.123456,143.049000,2.5,-77,-158.5,-157.0,...,-155.0
```

## Comportements attendus

### Live
1. Lancer `wfview`, activer CI‑V server (port 50002)
2. IC‑705 scope ON
3. Cliquer **Connecter**
4. Fréquence / ref level s’affichent
5. Spectre + waterfall passent en live dès réception des trames

### Replay CSV
1. Charger un CSV via **Parcourir**
2. Avancer/reculer ou Play/Pause
3. Waterfall suit la position et se reconstruit en arrière

## Paramètres clés

- Largeur spectre : 475 points
- Profondeur waterfall : 200 lignes
- Span par défaut : 5 kHz (fallback si pas de donnée CSV)
- Ref level par défaut : -77 dBm

## État actuel

✅ Live CI‑V (fréquence + ref level + spectre)  
✅ Spectre + waterfall Scene Graph  
✅ Replay CSV avec navigation + play + slider  
⏳ Enregistrement CSV live (à implémenter)  
⏳ Trigger pre/post (à implémenter)  
⏳ Export waterfall complet (à implémenter)  

## Prochaine étape recommandée

- Enregistrement CSV live conforme au format Python
- Trigger pre/post buffer
- Export waterfall complet (comme `csv_reader.py`)

## CI-V details (frames, offsets, schema)

This section documents the CI-V framing as used by the current project (via wfview).

### Generic CI-V frame layout

```
FE FE [ADDR_RADIO] [ADDR_PC] [CMD] [SUBCMD?] [PAYLOAD...] FD
```

- Preamble: `FE FE`
- End: `FD`
- ADDR_RADIO: `0xA4` (IC-705)
- ADDR_PC: `0xE0`
- CMD: main command byte
- SUBCMD: optional depending on command

### Commands used

| Function | CMD | SUBCMD | Payload |
|----------|-----|--------|---------|
| Scope stream ON | `0x27` | `0x10` | `01` |
| Scope stream OFF | `0x27` | `0x10` | `00` |
| Request frequency | `0x03` | - | - |
| Read ref level | `0x27` | `0x19` | - |

### Frequency decode (CMD 0x03)

- Format: 5 bytes BCD (LSB first)
- Each byte contains 2 BCD digits
- Convert Hz to MHz

Pseudo:
```
factors = [1, 100, 10000, 1000000, 100000000]
freq_hz = sum(low * factor + high * factor * 10)
freq_mhz = freq_hz / 1_000_000
```

### Ref level decode (CMD 0x27 / SUB 0x19)

Expected format:
```
FE FE E0 A4 27 19 [LOW] [HIGH] FD
```

- LOW: 2 BCD digits (e.g. 0x10 => 10)
- HIGH bit0: sign (1 = negative)

Example:
```
LOW = 0x10  => 10
HIGH bit0 = 1  => -10 dBm
```

### Spectrum frame (CMD 0x27, scope data)

- Scope data is carried in CMD `0x27` frames (sub-cmd other than 0x19).
- In the wfview stream, spectrum bytes start at offset **19**.
- Following bytes are raw amplitude points (0..160 typical).

Schema:
```
FE FE E0 A4 27 ?? [.... 19 bytes header ....] [RAW_0 ... RAW_N] FD
```

#### dBm conversion (current calibration)

```
REF_LEVEL_DEFAULT = -77
RAW_MAX = 160
SCALE = 0.5 dB/point

dBm = REF_LEVEL_DEFAULT - (RAW_MAX - raw) * SCALE
```

#### Resampling

The number of points per frame can vary with scope settings and wfview output.  
We always resample to **475 points** for display/CSV.

### Note

Offsets (especially **19**) match the current wfview stream.  
If firmware or scope mode changes, this offset might need adjustment.

## CI-V offset map (ASCII)

The following is an *approximate* byte map of the CI-V frames as consumed by this project.
It is intentionally pragmatic (what we parse today), not a full CI-V spec.

### Generic frame

```
 0    1    2           3        4        5        ...             n-1
FE | FE | ADDR_RADIO | ADDR_PC | CMD    | SUBCMD? | PAYLOAD ... | FD
```

### Frequency response (CMD 0x03)

We decode 5 BCD bytes starting at `msg[5]`:

```
FE FE E0 A4 03  [b0] [b1] [b2] [b3] [b4]  FD
           ^5   ^6   ^7   ^8   ^9   ^10
```

### Ref level response (CMD 0x27 / SUB 0x19)

We decode 2 bytes at `msg[6]` and `msg[7]`:

```
FE FE E0 A4 27 19  [LOW] [HIGH]  FD
              ^5   ^6    ^7
```

### Spectrum payload (CMD 0x27, scope data)

In the current wfview stream, the raw bins start at offset **19**:

```
FE FE E0 A4 27 ??  [ .... header bytes .... ]  [RAW_0 ... RAW_{N-1}]  FD
0  1  2  3  4  5              6..18                 19..(end-1)       end
                                            ^ start index used by this project
```

Important:
- the header (bytes 6..18) is treated as opaque for now
- the number of RAW bins varies, we resample to 475

## Live troubleshooting

If the UI connects but you never get live spectrum frames (demo keeps moving), validate in this order:

1) wfview
   - CI-V server enabled
   - Port is `50002`
   - wfview is connected to the IC-705 via USB

2) IC-705
   - Scope enabled (Scope ON)
   - Span set to something supported by your workflow (e.g. 2.5 kHz / 5 kHz)

3) This app
   - Click **Connecter**: status should become "Connected"
   - Frequency should update from 0.000 to the radio center frequency

If it still does not go live:
- Check `ic705_qt/build/Debug/ic705_qt_run.log` for socket errors.
- Verify the TCP port is open on localhost:
  ```powershell
  netstat -an | findstr 50002
  ```
- If frequency updates but spectrum doesn't: the stream may be connected but scope data is not being sent.
