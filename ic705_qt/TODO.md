# TODO - IC705 Qt Application (Plan d'execution)

Derniere mise a jour: 2026-02-06

## Legende priorites
- `P0` Critique: bloque la fiabilite fonctionnelle du projet.
- `P1` Haute: indispensable pour demo/jury et usage quotidien.
- `P2` Moyenne: fonctionnalites avancees utiles mais non bloquantes.
- `P3` Basse: backlog long terme.

---

## Definition of Done (globale)
Une tache est `FAITE` seulement si:
- le comportement est valide sur un cas nominal + un cas erreur,
- les logs sont explicites (pas de fail silencieux),
- pas de regression visible sur `Live` et `CSV Replay`,
- la doc technique (README/TODO) est mise a jour.

---

## P0 - Core a verrouiller

### [ ] 1) Enregistrement CSV en mode Live
Priorite: `P0`
Estimation: `2-3 jours`
Dependances: `CsvRecorder`, `CivClient`
Actions:
- connecter `CsvRecorder::pushSamples()` au flux live,
- inclure `timestamp,freqMHz,spanKHz,refLevel,samples...`,
- ouvrir/fermer proprement les fichiers,
- gerer erreur disque et dossier absent.
Fichiers: `csv_recorder.cpp`, `csv_recorder.h`, `main.cpp`

### [ ] 2) Trigger pre/post buffer (state machine)
Priorite: `P0`
Estimation: `3-4 jours`
Dependances: `#1`
Actions:
- buffer circulaire pre-trigger (ex: 200 lignes),
- post-buffer configurable (ex: 200 lignes),
- extension auto si signal persiste,
- sequence etats: `idle -> armed -> triggered -> post -> finalize`,
- renommage final avec `maxDbm`.
Fichiers: `csv_recorder.cpp`, `csv_recorder.h`

### [ ] 3) Stabilite connexion/deconnexion wfview
Priorite: `P0`
Estimation: `1-2 jours`
Dependances: `CivClient`
Actions:
- deconnexion radio pendant acquisition,
- radio eteinte/demarree en cours de session,
- reconnection propre sans fuite ni freeze,
- fermeture application pendant enregistrement.
Fichiers: `civ_client.cpp`, `main.cpp`, `csv_recorder.cpp`

### [ ] 4) Validation + erreurs claires
Priorite: `P0`
Estimation: `1-2 jours`
Dependances: aucune
Actions:
- validation stricte CSV a l'ouverture,
- messages utilisateur explicites (cause + action),
- erreurs connexion detaillees (host, timeout, auth),
- checks chemins/fichiers avant ecriture.
Fichiers: `csv_replay.cpp`, `civ_client.cpp`, `Main.qml`

### [ ] 5) Auto-reconnect + recovery enregistrement
Priorite: `P0`
Estimation: `1-2 jours`
Dependances: `#1`, `#3`
Actions:
- retry connexion (backoff simple, max tentatives),
- reprise propre apres coupure,
- gestion `.tmp` -> final en cas d'arret brutal.
Fichiers: `civ_client.cpp`, `csv_recorder.cpp`

### [ ] 6) Contrat format CSV + versioning [AJOUT IMPORTANT]
Priorite: `P0`
Estimation: `1 jour`
Dependances: `#1`
Actions:
- figer un schema CSV versionne (`format_version`),
- documenter colonnes obligatoires/options,
- gerer compatibilite future (fallback propre).
Fichiers: `README.md`, `csv_recorder.cpp`, `csv_replay.cpp`

### [ ] 7) Tests de parite Python vs Qt [AJOUT IMPORTANT]
Priorite: `P0`
Estimation: `2 jours`
Dependances: `#1`, `#2`, `#6`
Actions:
- jeu de donnees de reference (golden CSV),
- comparer min/max/avg, index max, rendu replay,
- verifier equivalence logique trigger.
Fichiers: `tests/`, scripts comparatifs

### [ ] 8) Audit thread-safety et etats [AJOUT IMPORTANT]
Priorite: `P0`
Estimation: `1-2 jours`
Dependances: `#1`, `#2`, `#3`
Actions:
- verifier signaux cross-thread (Qt::QueuedConnection),
- interdire transitions d'etats invalides,
- proteger acces concurrent aux buffers/fichiers.
Fichiers: `civ_client.cpp`, `csv_recorder.cpp`, `main.cpp`

---

## P1 - Demo et ergonomie essentielle

### [ ] 9) Raccourcis clavier globaux
Priorite: `P1`
Estimation: `1 jour`
Actions:
- Live: `Ctrl+C`, `Ctrl+R`, `Ctrl+T`,
- CSV: `Space`, `Left/Right`, `Home/End`, `Ctrl+J`, `Esc`.
Fichiers: `Main.qml`

### [ ] 10) Feedback visuel d'etat
Priorite: `P1`
Estimation: `1 jour`
Actions:
- indicateur REC, spinner connexion, toasts erreur/succes.
Fichiers: `Main.qml`

### [ ] 11) Tooltips sur controles
Priorite: `P1`
Estimation: `0.5 jour`
Actions:
- tooltip sur boutons/actions avec raccourcis associes.
Fichiers: `Main.qml`

### [ ] 12) Persistance preferences (QSettings)
Priorite: `P1`
Estimation: `1 jour`
Actions:
- connexion radio, trigger, gains, vitesse replay, geometrie fenetre.
Fichiers: `settings_manager.cpp/.h` (nouveau), `main.cpp`, `Main.qml`

### [ ] 13) Documentation utilisateur minimale
Priorite: `P1`
Estimation: `1-2 jours`
Actions:
- guide install, checklist diagnostic, workflow live/replay.
Fichiers: `docs/USER_MANUAL.md`, `docs/TROUBLESHOOTING.md`

### [ ] 14) Logs rotatifs et niveaux
Priorite: `P1`
Estimation: `0.5-1 jour`
Actions:
- rotation taille max + retention,
- niveaux `INFO/WARN/ERR/DEBUG` coherents.
Fichiers: `main.cpp`

---

## P2 - Fonctionnalites avancees

### [ ] 15) Export PNG/PDF
Priorite: `P2`
Estimation: `4-5 jours`
Dependances: `#6`
Etat:
- `PARTIEL`: export waterfall CSV Replay en `PNG/JPG` implemente (`CsvReplay::exportWaterfallImage`) + preview + crop zone.
- `RESTE`: export `PDF`, annotations completes (stats/markers), export cote mode Live.

### [ ] 16) Dashboard stats temps reel
Priorite: `P2`
Estimation: `2-3 jours`

### [ ] 17) Mode difference
Priorite: `P2`
Estimation: `2-3 jours`

### [ ] 18) Multi-fichiers CSV compare
Priorite: `P2`
Estimation: `4-5 jours`

### [ ] 19) Detection auto evenements
Priorite: `P2`
Estimation: `5-7 jours`

### [ ] 20) Tests unitaires Qt + CI
Priorite: `P2`
Estimation: `5-7 jours`
Actions:
- couverture cible initiale `>= 60%` sur modules core.
Fichiers: `tests/`, `.github/workflows/`

---

## P3 - Backlog
- Theme sombre/clair
- Colormaps waterfall configurables
- Mini-map waterfall
- SQLite sessions/evenements
- Mode beacon tracker
- Plugin Python scripts custom
- Visualisation 3D
- Companion mobile

---

## Etat actuel (a verifier rapidement)
Elements tres probablement deja en place:
- architecture Qt6/QML/C++,
- decodage CI-V de base,
- rendu spectre/waterfall,
- replay CSV + navigation,
- zoom waterfall + markers.

Verifier puis cocher officiellement:
- equivalence exacte avec scripts Python de reference,
- robustesse en conditions degradees (deconnexion, erreurs fichier),
- stabilite memory/thread sur sessions longues.

---

## Plan sprint recommande

### Sprint A (P0 pur, 2 semaines)
- [ ] `#1 #2 #3 #4 #5`

### Sprint B (qualite core, 1 semaine)
- [ ] `#6 #7 #8`

### Sprint C (demo/jury, 1 semaine)
- [ ] `#9 #10 #11 #12 #13 #14`

### Sprint D (avance, selon temps)
- [ ] `#15+`
