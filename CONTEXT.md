# MWPS — Contexte projet
_Mis à jour : 2026-06-18 (session 14 — PWA : bloc "Volume PC moyen · Mois en cours")_

---

## Ce qu'est le projet

**MWPS (Mon WinPharma Stats)** — pipeline de KPIs quotidiens pour les opérateurs d'une pharmacie.

- **Backend Python** sur serveur Windows : lit les exports Winpharma (XLS + TXT), calcule les KPIs, pousse vers Google Sheets via Service Account.
- **PWA** hébergée sur GitHub Pages (`afgto79/mwps`) : dashboard par opérateur, lecture via API publique Google Sheets.
- **Déclenchement** : script AHK compilé lancé par une tâche planifiée Windows.

**Opérateurs actifs** : DP (1), CD (2), CC (8). FM (7) et PM (9) : `actif=FALSE` (ne participent pas aux challenges pour l'instant).

---

## Architecture

```
Winpharma
  └─ exports XLS + TXT (990 PCA, 991 PCR, tbdb)
       └─ AHK (compilé) → main.py
            ├─ parser_xls.py   → PMHO, nb_ventes
            ├─ parser_txt.py   → nb_PCA, nb_PCR
            ├─ aggregator.py   → calcul taux_acceptation
            ├─ sheets_push.py  → feuille `data`
            └─ sheets_flags.py → feuille `flags` (records, streaks)

Google Sheets (ID: 1BsxJb2phBCdcO0GC8ErufjWDYGvY1QQevRr_xDTbnFU)
  ├─ data      : date | operateur_id | nom | nb_ventes | PMHO | nb_PCA | nb_PCR | taux
  ├─ flags     : records, streaks, best_team, progression, traj_ratio_PMHO, traj_ratio_PCA
  ├─ targets   : cibles mensuelles par opérateur (PMHO, taux_PCA, nb_propositions_j)
  └─ operators : id | initials | nom | color | actif  ← source de vérité pour les opérateurs

PWA (GitHub Pages)
  └─ index.html + config.js + service-worker.js (cache mwps-v11)
```

---

## Repos Git

- Backend Python : `afgto79/mwps-backend`
- PWA opérateur : `afgto79/mwps` → `https://afgto79.github.io/mwps/?op=X`
- Dashboard manager : `afgto79/mwps-backend` → `https://afgto79.github.io/mwps-backend/`

---

## Ce qui est fait

### Backend
- [x] Parsers XLS et TXT Winpharma
- [x] Agrégateur KPIs (PMHO, taux_acceptation, nb_PCA/PCR)
- [x] Push Google Sheets avec idempotence (skip si date+opérateur déjà présent)
- [x] Normalisation dates dans idempotence : serial Excel ET format français DD/MM/YYYY (`sheets_push.py`)
- [x] Calcul flags : records perso, streaks, best_team, progression
- [x] Calcul traj_ratio_PMHO et traj_ratio_PCA (feuille flags, colonnes Q et R)
- [x] Normalisation dates dans flags : serial Excel ET format français DD/MM/YYYY (`sheets_flags.py`)
- [x] `sous_cible_3j = False` si l'opérateur n'a pas travaillé aujourd'hui (congé ≠ alerte)
- [x] Boucle multi-XLS : `scan_xls_dir` → traite tous les fichiers XLS disponibles, pas seulement J-1
- [x] J-1 = dernier fichier disponible avant J (pas forcément la veille exacte)
- [x] `compute_and_push_flags` appelé une seule fois après tous les pushs (lit l'historique complet)
- [x] Déploiement serveur via dossier TRANSFERT (copie manuelle)
- [x] AHK compilé + tâche planifiée Windows opérationnelle
- [x] `watchdog.py` : fallback à 01h00 — screenshot avant relance AHK, relance auto, screenshot après si échec, email dans tous les cas (succès ou échec). Capture via PowerShell natif (pas de dépendance externe). Gmail app password stocké dans le script.
- [x] `mailer.py` : rapport email automatique après chaque run `main.py` — screenshot + log complet dans le corps, log succès/échec dans `logs/mail.log`. Sujet : `MWPS — Run JJ/MM/YYYY — OK / PARTIEL`. Testé et fonctionnel (session 13).
- [x] Fix quota 429 Sheets (session 13) : backoff retry `5s → 15s` (`sheets_client.py`), délai `30s` entre `push_data` et `compute_and_push_flags` (`main.py`). Isolement exception flags pour tracker `flags_ok` séparément.
- [x] AHK v5 : `SetThreadExecutionState` anti-veille au démarrage/fin, Sleep 3000 avant popup remplacement XLS
- [x] Lecture opérateurs actifs depuis feuille Sheets `operators` au démarrage (fallback operators.json)
- [x] Fix date TXT : utilise `data_date` (date XLS J) pour filtrer PCA/PCR
- [x] `build_j1_with_fallback` (`parser_xls.py`) : si un opérateur est absent du XLS J-1 direct (ex. dimanche), cherche en fallback le XLS du même mois le plus récent le contenant. Si aucun (première apparition du mois), utilise baseline 0. Intégré dans `main.py` avant `compute_pmho` / `compute_nb_ventes_j`.
- [x] Idempotence étendue (`sheets_push.py`) : si une ligne (date, op) existe avec PMHO **et** nb_ventes vides (run précédent raté), la ligne est **écrasée** via `values().update()` au lieu d'être skippée.
- [x] Passage de mois (`main.py`) : si J-1 est du mois précédent → `xls_j1_path = None` → baseline 0 — évite delta négatif le 1er de chaque mois.
- [x] Déduplication `all_data` (`sheets_flags.py`) : `_normalize_date_str()` dans le filtre `historical` — exclut correctement les lignes du jour même en DD/MM/YYYY.
- [x] `annee_mois` normalisé (`sheets_flags.py`) : `_normalize_year_month()` dans `targets_map` — gère YYYYMM compact et YYYY-MM.
- [x] `_traj_ratio` corrigé (`sheets_flags.py`) : `avg / cible` au lieu de `avg * jo / (cible * n)` — barres trajectoire reflètent la performance réelle dès le jour 1.
- [x] `operators.json` : `"9 MARCAGGI PAULE"` dans `ignore` — doit correspondre à la chaîne exacte du XLS (ID + nom), pas juste l'ID.

### PWA opérateur (afgto79/mwps)
- [x] Dashboard par opérateur (`?op=X`)
- [x] KPI gauche : PMHO + barre trajectoire mensuelle glissante
- [x] KPI droite : **Volume PC** (nb_PCA+nb_PCR / cible_nb_propositions_j) format "X/Y" — barre + coaching
- [x] Barre **Propositions acceptées** : taux_acceptation vs cible_taux_PCA — messages coaching aléatoires (3 cas : atteint / proche / loin)
- [x] Streak pill distingue PCA vs PMHO explicitement
- [x] Popups gamification précisent PCA ou PMHO
- [x] Section équipe → PMHO mensuel moyen, barres proportionnelles au leader
- [x] Onglet historique : PMHO 365j + "Nombre de Propositions — 365 jours" (PCA+PCR)
- [x] Alerte dates manquantes (30j) — congés non comptés (ligne existe avec ventes=0)
- [x] Confettis + popup motivation (records, streaks, best team)
- [x] `normalizeDate` gère serial Excel ET DD/MM/YYYY (format Sheets)
- [x] `normalizeYearMonth` gère YYYYMM compact ET serial Excel
- [x] `flagRow` = dernier flag ≤ todayStr (évite alertes d'un jour de congé plus récent)
- [x] SW cache v12
- [x] Opérateurs chargés dynamiquement depuis feuille `operators`
- [x] `fmtDate` heure locale (plus UTC) — label "Hier" correct entre 22h et minuit.
- [x] Bloc **Volume PC moyen · Mois en cours** (session 14) : classement équipe mensuel PCA+PCR. Valeur = `(PCA+PCR cumulés) / jours_travaillés` (1 décimale, `/j`). Barre = `cumul / cible_mensuelle` (`cible_nb_propositions_j × jours_ouvres_mois` depuis `targets`). Couleur = taux `PCA/(PCA+PCR)` vs `cible_taux_PCA` (mêmes seuils que `gaugeColor`). Tri desc par remplissage de barre. Guard si colonnes absentes.

### Dashboard manager PC (afgto79/mwps-backend → index.html)
- [x] Cartes par opérateur : PMHO + Taux PCA + barre Propositions (nb_PCA+nb_PCR vs cible/j)
- [x] Alertes 3j (sous cible PMHO/PCA, progression, dates manquantes)
- [x] Classement · Volume PC (nb_PCA+nb_PCR du jour)
- [x] Tendance Volume PC — mois courant (chart line)
- [x] Tendance PMHO — mois courant (chart line)
- [x] Objectifs mensuels : PMHO moy. + Volume PC moy./j vs cible
- [x] Auto-refresh 60s avec compte à rebours
- [x] `normalizeDate` gère DD/MM/YYYY
- [x] Opérateurs chargés dynamiquement depuis feuille `operators`

### Dashboard manager mobile (afgto79/mwps-backend → mobile/mobile.html)
- [x] 4 onglets : KPI (cartes opérateurs), Classement PMHO mensuel, chart PMHO, chart Volume PC
- [x] Cartes : PMHO + Taux PCA + barre Propositions + barres trajectoire + streak + alertes 3j
- [x] Leaderboard PMHO mensuel moyen, barres proportionnelles au leader
- [x] `normalizeDate` gère DD/MM/YYYY
- [x] Opérateurs chargés dynamiquement depuis feuille `operators`
- [x] URL : `https://afgto79.github.io/mwps-backend/mobile/mobile.html`

---

## Ce qui reste à faire

### En cours / beta test
- [ ] **DÉPLOYER** les fichiers TRANSFERT/ sur le serveur (sessions 6-10 : main.py, parser_xls.py, sheets_push.py, sheets_flags.py, config/operators.json)
- [ ] **DÉPLOYER** `watchdog.py` sur le serveur + créer tâche planifiée Windows à 01h00
- [ ] Vérifier que la tâche planifiée tourne correctement chaque jour après déploiement
- [ ] Décider opérateur 4 "AMEZQUITA" (ID=4) : ignorer ou activer dans feuille `operators`
- [ ] Vérifier que la PWA opérateur affiche bien la dernière journée travaillée (pas la dernière date avec données)
- [ ] Tester l'installation PWA Android avec `?op=X` → vérifier que start_url est correct

### Robustesse — Points de vigilance identifiés (session 10)

#### AHK — échecs récurrents à 00h05 (pattern identifié)
Winpharma bloqué sur MAJ ou alerte sanitaire → AHK abandonne après 20s timeout.
Observé régulièrement depuis avril 2026 (04-17, 04-22, 04-25, 04-26, 04-29, 05-01, 05-08, 05-11, 05-13, 05-19, 05-28, 06-04, 06-11, 06-13).
**Solution déployée (session 11)** : `watchdog.py` à 01h00 — relance automatique + email + screenshots.

#### AHK — échec silencieux le 11/06/2026
L'AHK a échoué ("Excel non ouvert après 20s — abandon") → aucun export XLS/TXT pour le 10/06.
- **Symptôme** : données manquantes en Sheets, PMHO=None
- **Procédure de récupération manuelle** :
  1. Exporter manuellement XLS et TXT depuis Winpharma
  2. Copier les fichiers dans `TRANSFERT/input/` sur le serveur (ou la machine dev)
  3. Lancer `python main.py --date YYYYMMDD` (date = demain par rapport aux XLS)
  4. Le script détecte automatiquement tous les XLS non encore poussés
- **À faire** : notification manager en cas d'échec AHK (Phase 5 — alerte)

#### find_txt_file — sélection par mtime (piège)
`find_txt_file` choisit le TXT le plus récemment **modifié** (pas la date dans le nom).
- **Risque** : exporter manuellement un TXT pour une date antérieure le rend "plus récent" → le script l'utilise pour toutes les dates, y compris les jours suivants → nb_PCA/PCR faux
- **Règle** : ne jamais laisser dans `input/` un TXT dont la date (dans le nom) est antérieure au TXT le plus récent. Supprimer l'ancien après vérification.

#### Quota Google Sheets 429 lors de runs de rattrapage (session 12 — 16/06/2026)
Run 61 dates d'un coup (rattrapage) → ~61 lectures Sheets en ~1 min → quota dépassé (limite : 60 reads/min/user).
- **Symptôme** : `HttpError 429 RATE_LIMIT_EXCEEDED` sur les dernières dates traitées — push échoué pour 06-13, 06-14, 06-15
- **Résolution** : relancer `main.py` à quota reposé → les dates déjà présentes sont skippées, seules les manquantes sont poussées. 06-15 a été récupérée au run 08:46 (4 lignes pushées).
- **Cause structurelle** : le skip-check lit la feuille Sheets 1 fois par date × opérateur → ~4 reads/date × 61 dates = trop.
- **Amélioration possible** : charger tout `data` en mémoire 1 seule fois au démarrage → 0 lecture pendant le traitement des dates.

#### Quota 429 sur flags après push data (session 13 — 17/06/2026)
Run quotidien normal (1 date) mais push data consomme 2 retries (429) → quota encore saturé quand les flags démarrent immédiatement → flags échoués.
- **Fix déployé** : backoff retry `5s → 15s` dans `api_call` (`sheets_client.py`) + délai fixe `30s` entre push_data et compute_and_push_flags (`main.py`).
- **Diagnostic** : rapport email `mailer.py` indique maintenant le statut flags OK/ECHEC à chaque run.

#### operators.json — ignore list (chaîne exacte XLS requise)
Le champ `ignore` doit contenir la chaîne **exacte** telle qu'elle apparaît dans le XLS (`"9 MARCAGGI PAULE"`, pas `"9"`).
Format XLS : `"{ID} {NOM COMPLET}"` (ex : `"4 AMEZQUITA"`, `"9 MARCAGGI PAULE"`).

#### Opérateurs inconnus dans XLS
Si un opérateur est dans le XLS mais absent de la feuille `operators` Sheets et de la liste `ignore` :
- Ses données sont poussées dans `data` → elles n'apparaissent pas dans les dashboards
- Un WARNING "Nouvel opérateur détecté" est loggé à chaque run
- Résoudre en ajoutant l'opérateur dans la feuille `operators` (actif=TRUE) ou dans `ignore`

**Opérateurs occasionnels connus (session 12)** : AMEZQUITA (4) et MAGALHAES (7) sont des opérateurs occasionnels. Leurs données sont précieuses mais ne doivent **pas** figurer dans les dashboards. Le WARNING répété est donc attendu — ce n'est pas un bug. Piste d'amélioration : ajouter une liste `occasional_operators` dans la config pour passer le log en INFO.

---

## Intentions pour la suite

### Capacité Google Sheets
- Limite officielle : 10 millions de cellules. À ~10 000 cellules/an (5 op × 250j × 8 col), aucun risque pratique.
- Performance API : `fetchSheet('data')` charge toutes les lignes. Acceptable jusqu'à ~5 000–10 000 lignes (10–20 ans). Si besoin : limiter le fetch aux 12 derniers mois.
- Le format d'affichage des dates dans Sheets (colonne A) peut être changé librement — le code lit la valeur brute, pas le format visuel.

### Gestion des opérateurs ✅ FAIT

Source de vérité unique : feuille `operators` dans Google Sheets.
- Ajouter un opérateur → nouvelle ligne, `actif=TRUE`
- Suspendre → `actif=FALSE` (disparaît de tous les dashboards et de la PWA)
- Backend (`main.py`) lit la feuille au démarrage et met à jour `operators_config` en mémoire. Fallback sur `operators.json` si Sheets indisponible.
- Couleurs disponibles en plus des 4 actuelles : `#ec4899` `#06b6d4` `#f59e0b` `#84cc16` `#6366f1`

### Phase 4B — Dashboard manager ✅ FAIT — en beta test

Fichier source : `input/mwps_dashboard_4b.html` — déployé sur `https://afgto79.github.io/mwps-backend/`

Affiché sur **PC comptoir** en pharmacie.

Contient :
- Cartes par opérateur (PMHO + PCA + alertes `sous_cible_*_3j`)
- Leaderboard classement PCA du dernier jour travaillé
- Graphiques line chart PMHO et PCA — mois courant, tous opérateurs
- Barre progression objectifs mensuels moyens
- Auto-refresh 60s avec compte à rebours
- Normalisation dates Excel serial + décimales FR (virgule → point)

> Validé visuellement le 09/04/2026. Données mock encore présentes — se lissera avec les vraies données quotidiennes.

---

### UI/UX — Référence Plecto

L'UI doit s'inspirer de Plecto (`input/MWPS_Plecto_Reference_v2.md`).  
Principes à appliquer :

1. **2 KPI max** sur la vue principale (PMHO + taux PCA)
2. **Couleur = signal principal** : vert/orange/rouge selon écart à la cible — jamais valeur brute seule
3. **1 écran = 1 message** : lecture en < 3 secondes, zéro scroll
4. **Leaderboard toujours visible** — jamais absent, gamification intégrée au layout
5. **Pop-up événementielle unique** au chargement si flag = true (record, streak, objectif atteint)
6. **Cible glissante** : objectif mensuel ÷ jours ouvrés restants (calculé côté Python)
7. **Chiffres oversized** : lisibilité à 1 mètre minimum

Checklist à valider avant chaque livraison design :
- [ ] Action déclenchée en < 5 secondes après ouverture ?
- [ ] Position dans le classement visible sans interaction ?
- [ ] Progression vs cible tangible et colorée ?
- [ ] Écran lisible à 1 mètre, en 3 secondes ?
- [ ] Zéro scroll sur la vue principale ?

Anti-patterns à éviter : dashboard analytique dense, widgets multi-métriques, cible mensuelle fixe non glissante, notifications continues.

---

---

### Phase 5 — Robustesse
- Logs fichier sur le serveur (`main.py >> mwps.log 2>&1`) avec rotation
- Alertes en cas d'échec (pas de données → notification manager)
- Gestion des jours fériés / pharmacie fermée (ne pas pousser de lignes vides)

### Phase 6 — Évolution UI PWA opérateur ✅ FAIT

#### Barres de progression mensuelle glissante (KPI cards)

Les barres sous les valeurs PMHO et PCA affichent la **trajectoire mensuelle glissante**.
Fallback : si pas encore de données (début de mois), affiche valeur jour / cible.

```
ratio = moyenne_cumulée_mois / (objectif_mensuel × jours_travaillés / jours_ouvrés_totaux)
```
Couleurs : vert ≥ 95% / orange 80–95% / rouge < 80%

Colonnes `traj_ratio_PMHO` et `traj_ratio_PCA` calculées dans `sheets_flags.py` (feuille `flags`, colonnes Q et R).

#### Section équipe — PMHO mensuel

- Titre : ~~Équipe · Dernière journée~~ → **Panier moyen · Mois en cours**
- Barres : PMHO moyen mensuel par opérateur, proportionnel au leader (leader = 100%)
- Couleur : `gaugeColor(pmho_moy, cible_PMHO)`
- Valeur affichée : `fmtPMHO(avg)` (ex : 18,50€)
- Tri : décroissant par PMHO moyen

> Note : les KPI cards (valeurs du jour PMHO + PCA) restent inchangées — les données sont celles de la veille, pushées à 7h00.

### Phase 7 — Notifications push
- Notification Android en début de shift avec le résumé de l'opérateur
- Piste : ntfy.sh (léger, auto-hébergeable)

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée, orchestration |
| `aggregator.py` | Calcul KPIs fusionnés |
| `sheets_push.py` | Push vers feuille `data` (idempotent) |
| `sheets_flags.py` | Calcul et push des flags/streaks |
| `config/operators.json` | Mapping ID → nom opérateur |
| `config/settings.json` | ID Sheets + chemin credentials |
| `pwa/index.html` | PWA opérateur (dashboard mobile) |
| `pwa/config.js` | SHEETS_ID, API_KEY, OPERATORS |
| `pwa/service-worker.js` | Cache PWA (v11) |
| `mobile/mobile.html` | Dashboard manager mobile (déployé dans `afgto79/mwps-backend`) |
| `watchdog.py` | Fallback AHK : relance auto à 01h00 + email + screenshots |
| `mailer.py` | Rapport email post-run : screenshot + log + statut flags → logs/mail.log |
| `TRANSFERT/` | Package à copier sur le serveur |
