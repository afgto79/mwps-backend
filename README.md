# Backend MWPS

**MWPS** (Mon WinPharma Stats) — pipeline de KPIs quotidiens pour les opérateurs d'une officine, à partir des exports Winpharma.

## Ce que ça fait

Chaque jour, un script AHK compilé (déclenché par une tâche planifiée Windows) lance ce backend Python, qui :

1. Lit les exports Winpharma du jour (XLS + TXT : ventes comptoir, PCA, PCR).
2. Calcule les KPIs par opérateur (PMHO, nombre de ventes, taux d'acceptation des propositions…).
3. Pousse les résultats vers une feuille Google Sheets (Service Account), avec idempotence — un même (date, opérateur) n'est jamais dupliqué.
4. Calcule des indicateurs dérivés (records, streaks, classement d'équipe, trajectoires vs objectifs mensuels) dans une feuille séparée.

Ce dépôt sert aussi de source pour deux tableaux de bord statiques servis en `index.html` / `mobile/mobile.html` : vue par opérateur, alertes, classements, tendances du mois.

Un troisième composant — la PWA individuelle par opérateur (`?op=X`) — vit dans un dépôt séparé (`afgto79/mwps`), non listé ici.

## Architecture

```
Winpharma
  └─ exports XLS + TXT (990 PCA, 991 PCR, tbdb)
       └─ AHK (compilé) → main.py
            ├─ parser_xls.py   → PMHO, nb_ventes
            ├─ parser_txt.py   → nb_PCA, nb_PCR
            ├─ aggregator.py   → calcul taux_acceptation
            ├─ sheets_push.py  → feuille `data`
            └─ sheets_flags.py → feuille `flags` (records, streaks, trajectoires)

Google Sheets
  ├─ data      : date | operateur_id | nom | nb_ventes | PMHO | nb_PCA | nb_PCR | taux
  ├─ flags     : records, streaks, best_team, progression, trajectoires
  ├─ targets   : cibles mensuelles par opérateur
  └─ operators : source de vérité des opérateurs (id, initiales, nom, couleur, actif)

Dashboards statiques (ce dépôt)
  ├─ index.html        → dashboard manager PC
  └─ mobile/mobile.html → dashboard manager mobile
```

`watchdog.py` sert de filet de sécurité : si le run principal échoue, il relance le script à 01h00 avec capture d'écran avant/après et notification email dans tous les cas.

## Fichiers principaux

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée quotidien (`python main.py [--date JJJJMMJJ]`) |
| `parser_xls.py` / `parser_txt.py` | Extraction des exports Winpharma |
| `aggregator.py` | Calcul des KPIs agrégés |
| `sheets_client.py` / `sheets_push.py` / `sheets_flags.py` / `sheets_init.py` | Intégration Google Sheets |
| `mailer.py` | Rapport email après chaque run (succès/échec + log) |
| `watchdog.py` | Relance de secours et alerte en cas d'échec |
| `config/operators.json` | Liste de repli des opérateurs (source normale : feuille `operators`) |
| `deploy.ps1` | Déploiement vers le serveur de production (copie via `TRANSFERT/`) |

## Stack technique

- Python (parsing XLS/TXT, orchestration)
- Google Sheets API (via Service Account)
- AutoHotkey compilé + tâche planifiée Windows pour le déclenchement quotidien
- HTML/JS statique pour les deux dashboards manager

## Statut

Backend et dashboards en production. Voir [CONTEXT.md](CONTEXT.md) pour le détail complet de l'historique des sessions et des correctifs.
