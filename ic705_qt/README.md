# IC705 Qt (C/C++/Qt 6) - README technique

Version C/C++/Qt6/QML du projet IC-705 (portage progressif des scripts Python).
Priorite absolue: fonctionnement avant esthetique.

## Objectifs (Phase 1)
- Connexion wfview (TCP CI-V)
- Decodage CI-V (frequence, ref level, spectre)
- Conversion dBm
- Spectre et waterfall en QML / Scene Graph
- Enregistrement CSV conforme (a venir)
- Lecture CSV conforme (fonctionnelle)

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
  assets/   (reserve)
  tests/    (reserve)
  cmake/    (reserve)
```

## Dependances
- Qt 6.11.x (MSVC 2022)
- Visual Studio Build Tools 2022 / Visual Studio 2026 Community
- CMake 3.21+
- Windows 10/11 SDK

Modules Qt utilises:
- Qt6::Core
- Qt6::Gui
- Qt6::Qml
- Qt6::Quick
- Qt6::QuickControls2
- Qt6::QuickDialogs2

## Build & Run (Windows / MSVC)
Depuis `ic705_qt/`:
```powershell
cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DCMAKE_PREFIX_PATH="C:\Qt\6.11.0\msvc2022_64"
cmake --build build --config Debug
.\run_debug.ps1
```

`run_debug.ps1` ajoute `C:\Qt\6.11.0\msvc2022_64\bin` au `PATH`.

## Log d execution
```
ic705_qt/build/Debug/ic705_qt_run.log
```

## UI - Separation Live / CSV
L application QML est organisee en deux onglets independants:
- Live: acquisition directe CI-V
- CSV: lecture et navigation d un fichier CSV

### Live (UI)
- Bouton Connecter / Deconnecter
- Etat (status, frequence, ref level)
- Controle REC + trigger
- Spectre (QSGGeometryNode)
- Waterfall (texture GPU)

### CSV (UI)
- Bouton Selectionner CSV
- Navigation (debut/fin, prev/next)
- Play/Pause, vitesse, slider de position
- Spectre et waterfall
- Panneau lateral: Info, Gain min/max, Markers, Export

## CSV - Format attendu
```
timestamp,freq_mhz,span_khz,ref_level_dbm,dbm_0,dbm_1,...,dbm_474
14:32:15.123456,143.049000,2.5,-77,-158.5,-157.0,...,-155.0
```

## Export metadata JSON (Replay)
Le mode CSV Replay permet d exporter un fichier metadata (`.json`) sans modifier le CSV source.

Schema actuel (`schema_version = ic705_qt_metadata_v1`):
- `generated_utc`
- `source_csv`
- `capture`: `frames`, `source_points_per_frame`, `replay_points_per_frame`, `resampled_for_replay`, `timestamp_start`, `timestamp_end`
- `frequency_mhz`: `start`, `end`, `min`, `max`, `avg`
- `span_khz`: `start`, `end`, `min`, `max`, `avg`
- `ref_level_dbm`: `start`, `end`, `min`, `max`, `avg`
- `dbm_samples`: `min`, `max`, `avg`

## Architecture logicielle (resume)

### 1) Acquisition CI-V (Live)
Classe: `CivClient`
- Connexion TCP vers `127.0.0.1:50002`
- Commandes CI-V:
  - `0x27 0x10` (Scope stream ON/OFF)
  - `0x03` (Freq)
  - `0x27 0x19` (Ref level)
- Extraction des trames: preambule `FE FE` -> fin `FD`
- Decodage frequence BCD -> MHz
- Decodage ref level (BCD signe)
- Decodage spectre:
  - Donnees a l offset 19 (stream wfview)
  - Conversion brute -> dBm:
    ```
    dBm = REF_LEVEL_DEFAULT - (RAW_MAX - raw) * 0.5
    ```
  - Redimensionnement a 475 points

### 2) Modeles
Spectre:
- `SpectrumModel`
- 475 floats (dBm)
- `setSamples()` injecte live ou replay

Waterfall:
- `WaterfallModel`
- Image 475x200 (ARGB32)
- Ajout d une ligne en haut (scroll)
- Colormap identique au projet Python

### 3) Rendu QML / Scene Graph
- `SpectrumItem`: `QQuickItem` + `QSGGeometryNode` (LineStrip)
- `WaterfallItem`: `QQuickItem` + `QSGSimpleTextureNode`
- QML: UI uniquement, pas de logique metier

### 4) Replay CSV
Classe: `CsvReplay`
- Chargement CSV format Python
- Navigation < / >
- Play/Pause + vitesse
- Slider de position
- Reconstruction waterfall si on recule

## Parametres clefs
- Largeur spectre: 475 points
- Profondeur waterfall: 200 lignes
- Span par defaut: 5 kHz (fallback si CSV)
- Ref level par defaut: -77 dBm

## Etat actuel
- OK Live CI-V (frequence + ref level + spectre)
- OK Spectre + waterfall Scene Graph
- OK Replay CSV avec navigation + play + slider
- TODO Enregistrement CSV live
- TODO Trigger pre/post buffer
- TODO Export waterfall complet

## CI-V details (frames / offsets)

Generic frame:
```
FE FE [ADDR_RADIO] [ADDR_PC] [CMD] [SUBCMD?] [PAYLOAD...] FD
```

Commandes utilisees:
| Fonction | CMD | SUBCMD | Payload |
|----------|-----|--------|---------|
| Scope stream ON | 0x27 | 0x10 | 01 |
| Scope stream OFF | 0x27 | 0x10 | 00 |
| Request frequency | 0x03 | - | - |
| Read ref level | 0x27 | 0x19 | - |

Frequence (CMD 0x03):
- 5 bytes BCD (LSB first)
- conversion Hz -> MHz

Ref level (CMD 0x27 / SUB 0x19):
```
FE FE E0 A4 27 19 [LOW] [HIGH] FD
```
- LOW: 2 digits BCD
- HIGH bit0: signe

Spectrum payload:
- RAW bins a partir de l offset 19 (stream wfview)
- resample vers 475 points

## Troubleshooting Live
Si le live ne passe pas:
1) wfview: CI-V server ON, port 50002
2) IC-705: scope ON
3) App: Connecter, frequence update

Log:
```
ic705_qt/build/Debug/ic705_qt_run.log
```

Check port:
```powershell
netstat -an | findstr 50002
```

## Prochaines etapes
- CSV recorder conforme Python
- Trigger pre/post buffer
- Export waterfall complet
