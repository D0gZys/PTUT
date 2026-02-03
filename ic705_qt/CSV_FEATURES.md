# Améliorations Mode CSV - Documentation

## 🎯 Fonctionnalités implémentées

### 1️⃣ Liste des fichiers récents (Sidebar)

**Emplacement :** Panneau gauche du mode CSV

**Fonctionnalités :**
- ✅ Scan automatique du dossier `recep_csv/` au démarrage
- ✅ Affichage hiérarchique par date (dossiers YYYYMMDD)
- ✅ Métadonnées affichées pour chaque fichier :
  - Nom du fichier
  - Date et heure de création
  - Nombre de lignes
  - Fréquence centrale (MHz)
  - Puissance max (dBm) si trigger
- ✅ Double-click pour charger un fichier
- ✅ Highlight du fichier actuellement ouvert (bordure bleue)
- ✅ Barre de recherche (filtre par nom)
- ✅ Bouton "🔄 Actualiser" pour rescanner

**Code backend :** `csv_manager.cpp::scanRecentFiles()`

**Usage :**
```qml
// Actualiser la liste
refreshRecentFiles()

// Double-click sur un fichier pour le charger automatiquement
```

---

### 2️⃣ Jump to Max

**Emplacement :** Bouton "🎯 Jump to Max" dans la barre de contrôle CSV

**Fonctionnalités :**
- ✅ Recherche du signal le plus fort dans tout le fichier CSV
- ✅ Navigation automatique vers cette position
- ✅ Feedback console avec l'index trouvé

**Code backend :** `csv_replay.cpp::findMaxSignalIndex()`

**Algorithme :**
```cpp
for chaque frame dans le CSV:
    calculer max(samples)
    si max > global_max:
        global_max = max
        index_max = i
return index_max
```

**Usage :**
- Cliquer sur "🎯 Jump to Max"
- Le curseur se positionne automatiquement sur le pic le plus fort

**Cas d'usage :**
- Trouver rapidement le météore le plus intense dans un enregistrement
- Aller directement au signal d'intérêt

---

### 3️⃣ Marqueurs multiples

**Emplacement :** 
- Bouton "📍 Add Marker" dans la barre de contrôle
- Liste des marqueurs affichée sous les contrôles

**Fonctionnalités :**
- ✅ Ajout de marqueurs à la position actuelle
- ✅ Capture automatique des données :
  - ID unique
  - Timestamp
  - Fréquence centrale
  - Max dBm à cette position
- ✅ Affichage compact des marqueurs (scrollable)
- ✅ Suppression individuelle (bouton ×)
- ✅ Clear All pour supprimer tous les marqueurs

**Code backend :** `csv_replay.cpp::getCurrentMaxDbm()`

**Structure d'un marqueur :**
```javascript
{
    id: 1,
    index: 142,
    timestamp: "14:32:15.123456",
    freq: 144.500,
    maxDbm: -95.3
}
```

**Usage :**
1. Naviguer vers une position intéressante
2. Cliquer sur "📍 Add Marker"
3. Le marqueur apparaît dans la liste
4. Répéter pour comparer plusieurs événements

**Cas d'usage :**
- Comparer plusieurs pics de signal
- Marquer les météores détectés
- Prendre des notes sur des événements
- Exporter une liste d'événements

---

### 4️⃣ Export Rapport

**Emplacement :** Bouton "📊 Export" dans la barre de contrôle CSV

**Fonctionnalités :**
- ✅ Dialogue de configuration d'export
- ✅ Choix du format :
  - PNG (haute résolution)
  - PDF (document complet)
  - JPG (compressé)
- ✅ Sélection du contenu :
  - ☑ Spectre actuel
  - ☑ Waterfall complet
  - ☑ Statistiques
  - ☑ Marqueurs (si présents)

**Code backend :** `csv_manager.cpp::exportReport()` ⚠️ À finaliser

**Format du rapport :**
```
┌─────────────────────────────────────┐
│ IC705 Meteor Detection Report      │
│ File: trigger_...csv                │
│ Date: 2026-01-15 14:32:15          │
├─────────────────────────────────────┤
│                                     │
│     [WATERFALL COMPLET]             │
│     (toutes les lignes)             │
│                                     │
├─────────────────────────────────────┤
│     [SPECTRE À POSITION]            │
│                                     │
├─────────────────────────────────────┤
│ Statistiques:                       │
│   - Durée: 15m 32s                 │
│   - Fréquence: 144.500 MHz         │
│   - Max dBm: -88.5                 │
│   - Nb marqueurs: 3                │
│                                     │
│ Marqueurs:                          │
│   #1: 14:32:15 | -95.3 dBm        │
│   #2: 14:35:42 | -88.5 dBm        │
│   #3: 14:38:10 | -102.1 dBm       │
└─────────────────────────────────────┘
```

**Usage :**
1. Cliquer sur "📊 Export"
2. Choisir le format et le contenu
3. Valider
4. Le rapport est généré

**Note :** La génération d'image nécessite QPainter/QImage (TODO)

---

## 🔧 Architecture technique

### Fichiers modifiés

1. **qml/Main.qml**
   - Ajout sidebar liste fichiers
   - Boutons Jump/Marker/Export
   - Affichage marqueurs
   - Fonctions JS

2. **src/csv_replay.h/cpp**
   - `getCurrentMaxDbm()` : max de la frame actuelle
   - `findMaxSignalIndex()` : recherche globale du max

3. **src/csv_manager.h/cpp** (NOUVEAU)
   - `scanRecentFiles()` : scan dossier CSV
   - `exportReport()` : génération rapport (TODO)

4. **src/main.cpp**
   - Exposition `csvManager` au QML

5. **CMakeLists.txt**
   - Ajout csv_manager au build

---

## 🚀 Pour compiler

```powershell
cd ic705_qt
cmake --build build --config Debug
.\run_debug.ps1
```

---

## 📋 TODO / Améliorations futures

### Export (Prioritaire)
- [ ] Implémenter `exportReport()` avec QPainter
- [ ] Génération PNG du waterfall complet
- [ ] Génération PDF multi-pages
- [ ] Colorbar sur l'export
- [ ] Annotations automatiques (pics détectés)

### Liste fichiers
- [ ] Filtrage par date (range picker)
- [ ] Filtrage par puissance min (ex: > -100 dBm)
- [ ] Tri personnalisé (date/nom/puissance)
- [ ] Preview thumbnail du waterfall
- [ ] Statistiques globales (nb triggers, durée totale)

### Marqueurs
- [ ] Click sur waterfall pour placer marqueur
- [ ] Drag&drop pour déplacer marqueur
- [ ] Annotation texte libre sur marqueur
- [ ] Export liste marqueurs en CSV
- [ ] Import marqueurs depuis fichier

### Général
- [ ] Raccourcis clavier (M pour marker, J pour jump)
- [ ] Undo/Redo pour marqueurs
- [ ] Sauvegarde auto des marqueurs (fichier .markers)
- [ ] Mode comparaison (2 CSV côte à côte)

---

## 🐛 Bugs connus

Aucun pour le moment.

---

## 💡 Utilisation recommandée

### Workflow typique d'analyse :

1. **Ouvrir l'application** → Mode CSV
2. **Liste fichiers** → Double-click sur un trigger
3. **Jump to Max** → Aller au signal le plus fort
4. **Add Marker** → Marquer cet événement
5. **Navigation** → Chercher d'autres pics
6. **Add Marker** → Marquer autres événements
7. **Export** → Générer rapport pour documentation

### Exemple : Analyse session météores

```
09:00 - Lancement acquisition (mode Trigger, seuil -130 dBm)
12:30 - Fin acquisition → 15 triggers enregistrés

Analyse :
1. Charger chaque trigger
2. Jump to Max pour chaque
3. Noter puissance et durée avec marqueurs
4. Export rapport PDF avec tous les marqueurs
5. Rapport final : 15 météores détectés, max -82 dBm
```

---

## 📞 Support

En cas de problème :
1. Vérifier les logs : `ic705_qt/build/Debug/ic705_qt_run.log`
2. Console output dans le terminal
3. Vérifier que `recep_csv/` existe et contient des fichiers

