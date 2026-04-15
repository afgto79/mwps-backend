# MWPS — Contexte projet
_Mis à jour : 2026-04-15 (session 4)_

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
- [x] Lecture opérateurs actifs depuis feuille Sheets `operators` au démarrage (fallback operators.json)
- [x] Fix date TXT : utilise `data_date` (date XLS J) pour filtrer PCA/PCR

### PWA opérateur (afgto79/mwps)
- [x] Dashboard par opérateur (`?op=X`)
- [x] KPIs : PMHO, taux PCA, barre propositions (nb_PCA+nb_PCR vs cible journalière)
- [x] Barres trajectoire mensuelle glissante (traj_ratio depuis flags)
- [x] Streak pill distingue PCA vs PMHO explicitement
- [x] Popups gamification précisent PCA ou PMHO
- [x] Section équipe → PMHO mensuel moyen, barres proportionnelles au leader
- [x] Onglet historique : PMHO 365j + "Nombre de Propositions — 365 jours" (PCA+PCR)
- [x] Alerte dates manquantes (30j) — congés non comptés (ligne existe avec ventes=0)
- [x] Messages coaching contextuels
- [x] Confettis + popup motivation (records, streaks, best team)
- [x] `normalizeDate` gère serial Excel ET DD/MM/YYYY (format Sheets)
- [x] `normalizeYearMonth` gère YYYYMM compact ET serial Excel
- [x] `flagRow` = dernier flag ≤ todayStr (évite alertes d'un jour de congé plus récent)
- [x] SW cache v11
- [x] Opérateurs chargés dynamiquement depuis feuille `operators`

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
- [ ] Confirmer que la tâche planifiée tourne correctement chaque jour
- [ ] Vérifier que le Sheets se remplit sans doublons sur plusieurs jours (idempotence DD/MM/YYYY corrigée)
- [ ] Vérifier que la PWA opérateur affiche bien la dernière journée travaillée (pas la dernière date avec données)
- [ ] Tester l'installation PWA Android avec `?op=X` → vérifier que start_url est correct
- [ ] Ajouter `"9"` à la liste `ignore` dans `operators.json` pour supprimer le WARNING PM des logs (cosmétique)

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
| `TRANSFERT/` | Package à copier sur le serveur |
