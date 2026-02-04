# TODO - IC705 Qt Application

## Légende
- 🔴 **CRITIQUE** : Bloquant, à faire immédiatement
- 🟠 **HAUTE** : Important, à faire rapidement (1-2 semaines)
- 🟡 **MOYENNE** : Amélioration significative (1 mois)
- 🟢 **BASSE** : Nice to have, quand le temps le permet
- ✅ **FAIT** : Terminé

---

## 🔴 CRITIQUE - Fonctionnalités Core Manquantes

### [ ] 1. Enregistrement CSV en mode Live
**Criticité** : 🔴 CRITIQUE  
**Estimation** : 2-3 jours  
**Dépendances** : CsvRecorder, CivClient  
**Description** :
- Connecter `CsvRecorder::pushSamples()` aux données Live
- Récupérer `freqMHz`, `spanKHz`, `refLevel` du CivClient
- Ouvrir fichier CSV avec nomenclature correcte
- Écrire header + frames en temps réel
- Gérer fermeture propre du fichier

**Fichiers** : `csv_recorder.cpp`, `main.cpp`

### [ ] 2. Système Trigger avec Pre/Post Buffer
**Criticité** : 🔴 CRITIQUE  
**Estimation** : 3-4 jours  
**Dépendances** : CsvRecorder  
**Description** :
- Implémenter buffer circulaire (QQueue) pour pre-buffer
- Détection seuil configurable (dBm max > threshold)
- État : idle → pre-buffering → triggered → post-buffering → finalize
- Enregistrement pré-buffer (200 lignes par défaut)
- Enregistrement post-buffer (200 lignes par défaut)
- Extension auto si signal persiste
- Fichier temporaire → renommage final avec maxDbm

**Fichiers** : `csv_recorder.cpp`, `csv_recorder.h`

### [ ] 3. Tests de Stabilité Connexion/Déconnexion
**Criticité** : 🔴 CRITIQUE  
**Estimation** : 1-2 jours  
**Description** :
- Tester déconnexion wfview pendant acquisition
- Reconnexion automatique (optionnel : timer retry)
- Vérifier gestion mémoire (pas de fuites)
- Tester comportement si IC-705 éteint
- Validation fermeture fichiers en cas de crash

**Fichiers** : `civ_client.cpp`, `csv_recorder.cpp`

---

## 🟠 HAUTE - Améliorations UX Essentielles

### [ ] 4. Raccourcis Clavier Globaux
**Criticité** : 🟠 HAUTE  
**Estimation** : 1 jour  
**Description** :
```
Mode Live:
- Ctrl+C : Connecter/Déconnecter
- Ctrl+R : Toggle Recording
- Ctrl+T : Toggle Trigger
- Ctrl+S : Screenshot

Mode CSV:
- Space : Play/Pause
- ← / → : Frame précédent/suivant
- Home/End : Début/Fin
- Ctrl+M : Add Marker
- Ctrl+J : Jump to Max
- Ctrl+Z : Reset Zoom
- Esc : Exit Zoom (✅ déjà fait)
```

**Fichiers** : `Main.qml`

### [ ] 5. Feedback Visuel d'État
**Criticité** : 🟠 HAUTE  
**Estimation** : 1 jour  
**Description** :
- LED animée pendant REC (rouge pulsant)
- Spinner lors connexion TCP
- Barre de progression chargement CSV
- Toast notifications (succès/erreur/info)
- Indicateur FPS/latence

**Fichiers** : `Main.qml`, nouveaux composants QML

### [ ] 6. Tooltips sur tous les Contrôles
**Criticité** : 🟠 HAUTE  
**Estimation** : 2-3 heures  
**Description** :
- Ajouter `ToolTip.text` sur tous les boutons
- Inclure raccourci clavier si applicable
- Delay: 500ms, timeout: 3000ms

**Fichiers** : `Main.qml`

### [ ] 7. Sauvegarde Préférences Utilisateur (QSettings)
**Criticité** : 🟠 HAUTE  
**Estimation** : 1 jour  
**Description** :
Persister :
- Dernière connexion radio (IP, user, password, MAC, name)
- Seuil trigger habituel
- Gain min/max préférés
- Vitesse replay par défaut
- Position/taille fenêtre
- Dernier dossier CSV ouvert

**Fichiers** : Nouveau `settings_manager.cpp/.h`, `main.cpp`

### [ ] 8. Validation & Messages d'Erreur Clairs
**Criticité** : 🟠 HAUTE  
**Estimation** : 1 jour  
**Description** :
- Valider format CSV à l'ouverture
- Messages d'erreur explicites (pas de crash silencieux)
- Dialog d'erreur si connexion échoue (avec cause)
- Warning si port 50002 occupé
- Vérification existence dossier recep_csv

**Fichiers** : `csv_replay.cpp`, `civ_client.cpp`, `Main.qml`

---

## 🟡 MOYENNE - Fonctionnalités Avancées

### [ ] 9. Export PDF/PNG Complet
**Criticité** : 🟡 MOYENNE  
**Estimation** : 4-5 jours  
**Description** :
- Export waterfall en PNG/JPEG haute résolution
- Génération rapport PDF :
  - Métadonnées session (date, freq, durée)
  - Waterfall full-res
  - Snapshots spectre (marqueurs)
  - Statistiques (max, min, moyenne)
  - Annotations/commentaires
- Dialog options export (format, résolution, contenu)

**Fichiers** : Nouveau `export_manager.cpp/.h`, `Main.qml`

### [ ] 10. Dashboard Statistiques Temps Réel
**Criticité** : 🟡 MOYENNE  
**Estimation** : 2-3 jours  
**Description** :
Panel affichant :
- FPS acquisition actuel
- Signal moyen / médian / max
- SNR instantané (estimation)
- Taux de trigger (events/heure)
- Durée session
- Nombre frames enregistrées
- Sparkline historique signal max
- Histogramme distribution amplitude

**Fichiers** : Nouveau `stats_model.cpp/.h`, `Main.qml`

### [ ] 11. Curseurs Interactifs sur Spectre
**Criticité** : 🟡 MOYENNE  
**Estimation** : 2 jours  
**Description** :
- Clic pour placer curseur vertical
- Affichage fréquence + dBm au curseur
- Support 2 curseurs : mesure delta (Δf, ΔdBm)
- Drag curseur pour déplacer
- Annotation fréquences favorites

**Fichiers** : `spectrum_item.cpp`, `Main.qml`

### [ ] 12. Mode Difference (Détection Améliorée)
**Criticité** : 🟡 MOYENNE  
**Estimation** : 2-3 jours  
**Description** :
- Calcul référence = moyenne N dernières frames
- Affichage diff = Current - Reference
- Met en évidence uniquement les variations (météores)
- Toggle "Show Difference" dans UI
- Seuil trigger sur diff

**Fichiers** : Nouveau `difference_processor.cpp/.h`, `spectrum_model.cpp`

### [ ] 13. Comparaison Multi-Fichiers CSV
**Criticité** : 🟡 MOYENNE  
**Estimation** : 4-5 jours  
**Description** :
- Charger 2-4 CSV simultanément
- Affichage synchronisé (alignement temporel)
- Overlay spectre (couleurs différentes)
- Switch rapide entre fichiers
- Export rapport comparatif

**Fichiers** : Refactoring `csv_replay.cpp`, nouveau `csv_comparator.cpp/.h`

### [ ] 14. Détection Automatique Événements
**Criticité** : 🟡 MOYENNE  
**Estimation** : 5-7 jours  
**Description** :
Algorithmes :
- Peak detection (scipy.signal.find_peaks équivalent)
- Critères : amplitude min, durée min, isolation
- Labeling automatique
- Timeline avec événements annotés
- Filtrage par intensité/durée
- Quick jump entre événements détectés
- Export liste événements (JSON/CSV)

**Fichiers** : Nouveau `event_detector.cpp/.h`, `Main.qml`

### [ ] 15. Base de Données SQLite Locale
**Criticité** : 🟡 MOYENNE  
**Estimation** : 5-6 jours  
**Description** :
Schema :
```sql
sessions (id, date, freq_mhz, duration_sec, trigger_count)
events (id, session_id, timestamp, max_dbm, duration_ms, classification)
markers (id, session_id, timestamp, freq_mhz, note)
```
Fonctionnalités :
- Browser sessions historiques
- Recherche avancée (date, freq, intensité)
- Graphiques tendances (météores/mois)
- Export stats annuelles

**Fichiers** : Nouveau `database_manager.cpp/.h`, `Main.qml`

---

## 🟢 BASSE - Polish & Nice to Have

### [ ] 16. Thème Sombre/Clair Switchable
**Criticité** : 🟢 BASSE  
**Estimation** : 1 jour  
**Description** :
- Toggle dark/light mode
- Palette de couleurs cohérente
- Détection thème système Windows (optionnel)
- Persistance préférence (QSettings)

**Fichiers** : `Main.qml`, nouveau `Theme.qml`

### [ ] 17. Waterfall Colormap Personnalisable
**Criticité** : 🟢 BASSE  
**Estimation** : 2-3 jours  
**Description** :
Options :
- WFView (actuel, défaut)
- Viridis (scientifique)
- Turbo (haute contraste)
- Grayscale (impression)
- Custom (éditeur gradient)

**Fichiers** : `waterfall_model.cpp`, `Main.qml`

### [ ] 18. Mini-carte Waterfall (Overview)
**Criticité** : 🟢 BASSE  
**Estimation** : 2 jours  
**Description** :
- Aperçu miniature du waterfall complet
- Rectangle de sélection (zone visible)
- Clic pour jump rapide
- Mode "Bird's eye view"

**Fichiers** : Nouveau composant QML

### [ ] 19. Spectrogramme 3D (Mode Analyse)
**Criticité** : 🟢 BASSE  
**Estimation** : 7-10 jours  
**Description** :
- Visualisation 3D : freq × temps × amplitude
- Rotation/zoom interactif
- Utiliser Qt3D ou QtDataVisualization
- Export 3D (obj, stl)

**Fichiers** : Nouveau module 3D

### [ ] 20. Plugin Python pour Scripts Custom
**Criticité** : 🟢 BASSE  
**Estimation** : 5-7 jours  
**Description** :
- Embed Python interpreter (PyQt/PySide)
- API callback : on_trigger, on_frame, etc.
- Accès aux données en temps réel
- Script editor intégré

**Fichiers** : Nouveau module Python integration

### [ ] 21. Mode Beacon Tracker
**Criticité** : 🟢 BASSE  
**Estimation** : 3-4 jours  
**Description** :
- Liste fréquences balises (configurable)
- Auto-tune IC-705 en séquence
- Détection présence/absence
- Log intensité signal (suivi propagation)

**Fichiers** : Nouveau `beacon_tracker.cpp/.h`

### [ ] 22. Mobile Companion App
**Criticité** : 🟢 BASSE  
**Estimation** : 15-20 jours  
**Description** :
- App Android/iOS (Qt for Mobile)
- Monitoring à distance
- Notifications push (trigger détecté)
- Galerie enregistrements
- Contrôle remote (start/stop REC)

**Fichiers** : Nouveau projet ic705_mobile/

---

## 🛠️ Améliorations Techniques

### [ ] 23. Optimisation Performance
**Criticité** : 🟡 MOYENNE  
**Estimation** : 3-4 jours  
**Description** :
- Profiling CPU/GPU (QElapsedTimer)
- Thread pool pour traitement parallèle
- Cache disque pour CSV (mmap)
- Lazy loading gros CSV (>10k lignes)
- Compression waterfall en mémoire

**Fichiers** : Multiples

### [ ] 24. Auto-Reconnect & Recovery
**Criticité** : 🟠 HAUTE  
**Estimation** : 1-2 jours  
**Description** :
- Retry connexion TCP si échec (timeout 5s, 3 tentatives)
- Recovery fichier CSV en cas de crash
- Sauvegarde auto toutes les 5 minutes (mode REC)
- Fichiers .tmp → renommage final

**Fichiers** : `civ_client.cpp`, `csv_recorder.cpp`

### [ ] 25. Tests Unitaires
**Criticité** : 🟡 MOYENNE  
**Estimation** : 5-7 jours  
**Description** :
- Framework : Qt Test
- Tests : CivClient, CsvReplay, CsvRecorder
- Mocks pour IC705Client
- Coverage > 70%
- CI/CD GitHub Actions (optionnel)

**Fichiers** : Nouveau dossier tests/

### [ ] 26. Documentation Utilisateur
**Criticité** : 🟠 HAUTE  
**Estimation** : 2-3 jours  
**Description** :
- Manuel utilisateur (PDF)
- Screenshots/vidéos tutoriels
- FAQ troubleshooting
- Documentation protocole CI-V
- Guide installation

**Fichiers** : `docs/USER_MANUAL.md`, `docs/TROUBLESHOOTING.md`

### [ ] 27. Logs Rotatifs
**Criticité** : 🟢 BASSE  
**Estimation** : 0.5 jour  
**Description** :
- Log rotation (max 10 MB, 5 fichiers)
- Niveaux : DEBUG, INFO, WARNING, ERROR
- Log timestamp avec millisecondes
- Compression anciens logs (.gz)

**Fichiers** : `main.cpp`

---

## 📊 Résumé Priorités

### Sprint 1 (2 semaines) - CRITIQUE
- [ ] #1 : Enregistrement CSV Live
- [ ] #2 : Trigger Pre/Post Buffer
- [ ] #3 : Tests Stabilité

### Sprint 2 (1 semaine) - UX Essentiels
- [ ] #4 : Raccourcis Clavier
- [ ] #5 : Feedback Visuel
- [ ] #6 : Tooltips
- [ ] #7 : QSettings

### Sprint 3 (2 semaines) - Fonctionnalités Avancées
- [ ] #8 : Validation/Erreurs
- [ ] #9 : Export PDF/PNG
- [ ] #10 : Dashboard Stats
- [ ] #24 : Auto-Reconnect

### Sprint 4 (2-3 semaines) - Analyse & Comparaison
- [ ] #11 : Curseurs Spectre
- [ ] #12 : Mode Difference
- [ ] #13 : Multi-Fichiers
- [ ] #14 : Détection Auto Événements

### Backlog - Quand le temps le permet
- [ ] #15-#27 : Fonctionnalités basses priorité

---

## ✅ Déjà Terminé

- [x] Architecture Qt6/QML/C++
- [x] Connexion TCP CI-V (via wfview)
- [x] Décodage trames (freq, ref level, spectre)
- [x] Conversion dBm calibrée
- [x] Rendu GPU spectre (Scene Graph)
- [x] Rendu GPU waterfall (Texture)
- [x] Replay CSV complet
- [x] Navigation CSV (play/pause/slider)
- [x] Liste fichiers récents avec métadonnées
- [x] Jump to Max
- [x] Marqueurs multiples
- [x] Zoom interactif waterfall
- [x] Escape pour sortir du zoom

---

## 📝 Notes

- **Priorité académique PTUT** : Focus #1, #2, #3, #8, #26 avant remise
- **Priorité démo/jury** : Ajouter #4, #5, #6 pour présentation
- **Priorité publication** : Ajouter #9, #10, #14, #15 pour usage réel

---

**Dernière mise à jour** : 2026-02-04
