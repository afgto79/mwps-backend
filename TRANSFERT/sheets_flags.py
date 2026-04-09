"""
sheets_flags.py — Calcul et push des flags de gamification

Feuille `flags` écrasée à chaque run.
Ordre de calcul : cible_j → streak → records → best_team → objectifs mensuels → alertes 3j.
"""

import logging
from datetime import date
from typing import Optional

from sheets_client import api_call, get_service, load_settings, read_sheet

logger = logging.getLogger(__name__)

FLAGS_SHEET   = 'flags'
DATA_SHEET    = 'data'
TARGETS_SHEET = 'targets'

FLAGS_HEADERS = [
    'date', 'operateur_id', 'operateur_nom',
    'streak_PCA', 'streak_PMHO',
    'record_PMHO', 'record_taux_PCA',
    'best_team_PCA',
    'objectif_mensuel_PMHO_atteint', 'objectif_mensuel_PCA_atteint',
    'cible_j_PMHO', 'cible_j_PCA',
    'sous_cible_PMHO_3j', 'sous_cible_PCA_3j',
    'objectif_volume_atteint', 'progression_PCA',
    'traj_ratio_PMHO', 'traj_ratio_PCA',
]


# ── Helpers génériques ───────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    """Convertit une valeur en float ou None."""
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_working(row: dict) -> bool:
    """True si l'opérateur a fait au moins 1 vente ce jour (nb_ventes_comptoir_j > 0)."""
    v = _f(row.get('nb_ventes_comptoir_j'))
    return v is not None and v > 0


def _normalize_row(row: dict) -> dict:
    """Convertit toutes les valeurs d'un dict en str (pour uniformiser les sources)."""
    return {k: ('' if v is None else str(v)) for k, v in row.items()}


# ── Cible journalière glissante ──────────────────────────────────────────────

def _compute_cible_j(
    month_history: list[dict],
    cible_mensuelle: float,
    jours_ouvres: int,
    kpi_field: str,
) -> float:
    """
    Cible glissante pour le jour J.
    month_history = lignes du mois pour cet opérateur AVANT J (date < J).
    """
    if cible_mensuelle == 0:
        return 0.0

    worked = [r for r in month_history if _is_working(r)]
    jours_ecoules  = len(worked)
    jours_restants = jours_ouvres - jours_ecoules   # inclut J

    if jours_restants <= 0:
        return round(cible_mensuelle, 4)

    vals   = [_f(r.get(kpi_field)) for r in worked]
    vals   = [v for v in vals if v is not None]
    cumul  = sum(vals) / len(vals) if vals else 0.0

    cible_j = (cible_mensuelle * jours_ouvres - cumul * jours_ecoules) / jours_restants
    return round(max(0.0, cible_j), 4)


# ── Streak ───────────────────────────────────────────────────────────────────

def _compute_streak(
    all_data: list[dict],
    op_id: str,
    kpi_field: str,
    cible: float,
    target_date: date,
    today_row: dict,
) -> int:
    """
    Streak = nb de jours consécutifs (incluant aujourd'hui) où kpi >= cible.
    Jours non ouvrés (toute l'équipe à 0) : compteur gelé, on remonte.
    Jour ouvré mais opérateur absent ou sans données : streak cassé.
    """
    date_str = target_date.isoformat()

    # Vérifier aujourd'hui d'abord
    if not _is_working(today_row):
        return 0
    today_kpi = _f(today_row.get(kpi_field))
    if today_kpi is None or today_kpi < cible:
        return 0

    streak = 1

    # Remonter dans le passé (J-1, J-2, …)
    past_dates = sorted(
        {r['date'] for r in all_data if r['date'] < date_str},
        reverse=True,
    )

    for d_str in past_dates:
        day_rows = [r for r in all_data if r['date'] == d_str]

        # Jour non ouvré → streak suspendu, on continue à remonter
        if not any(_is_working(r) for r in day_rows):
            continue

        # Opérateur présent ce jour ?
        op_rows = [r for r in day_rows if r.get('operateur_id') == op_id]
        if not op_rows or not _is_working(op_rows[0]):
            break   # absent un jour ouvré → streak cassé

        kpi_val = _f(op_rows[0].get(kpi_field))
        if kpi_val is None:
            break   # pas de données → streak cassé

        if kpi_val >= cible:
            streak += 1
        else:
            break   # sous la cible → streak cassé

    return streak


# ── Progression PCA vs moyenne 7 jours ouvrés ───────────────────────────────

def _compute_progression_pca(
    all_data: list[dict],
    op_id: str,
    nb_pca_j: int,
    target_date: date,
) -> tuple[bool, Optional[float]]:
    """
    True si nb_PCA du jour J > moyenne nb_PCA sur les 7 derniers jours ouvrés.
    Seuls les jours où nb_ventes_comptoir_j > 0 sont pris en compte.
    Si historique < 3 jours ouvrés → (False, None).
    Retourne (bool, moyenne_7j).
    """
    date_str   = target_date.isoformat()
    past_dates = sorted(
        {r['date'] for r in all_data if r['date'] < date_str},
        reverse=True,
    )

    pca_vals: list[float] = []
    for d_str in past_dates:
        if len(pca_vals) >= 7:
            break
        op_rows = [r for r in all_data if r['date'] == d_str and r.get('operateur_id') == op_id]
        if op_rows and _is_working(op_rows[0]):
            pca_val = _f(op_rows[0].get('nb_PCA'))
            if pca_val is not None:
                pca_vals.append(pca_val)

    if len(pca_vals) < 3:
        return False, None

    avg = round(sum(pca_vals) / len(pca_vals), 4)
    return nb_pca_j > avg, avg


# ── Alerte 3 jours sous la cible ────────────────────────────────────────────

def _compute_sous_cible_3j(
    all_data: list[dict],
    op_id: str,
    kpi_field: str,
    cible: float,
    target_date: date,
    today_row: dict,
) -> bool:
    """
    True si les 3 derniers jours travaillés (incluant aujourd'hui) sont tous sous la cible.
    Moins de 3 jours travaillés → False.
    """
    if cible == 0:
        return False

    date_str  = target_date.isoformat()
    worked_kpis: list[Optional[float]] = []

    # Aujourd'hui
    if _is_working(today_row):
        worked_kpis.append(_f(today_row.get(kpi_field)))

    # Passé
    past_dates = sorted(
        {r['date'] for r in all_data if r['date'] < date_str},
        reverse=True,
    )
    for d_str in past_dates:
        if len(worked_kpis) >= 3:
            break
        op_rows = [r for r in all_data if r['date'] == d_str and r.get('operateur_id') == op_id]
        if op_rows and _is_working(op_rows[0]):
            worked_kpis.append(_f(op_rows[0].get(kpi_field)))

    if len(worked_kpis) < 3:
        return False

    return all(v is None or v < cible for v in worked_kpis[:3])


# ── Point d'entrée principal ─────────────────────────────────────────────────

def compute_and_push_flags(
    target_date: date,
    today_rows: list[dict],
    spreadsheet_id: str = None,
    service=None,
) -> None:
    """
    Calcule tous les flags pour chaque opérateur de today_rows
    et écrase la feuille `flags`.

    today_rows : liste de dicts produite par aggregator.aggregate()
    """
    if service is None:
        service = get_service()
    if spreadsheet_id is None:
        spreadsheet_id = load_settings()['google_sheets_id']

    date_str   = target_date.isoformat()
    year_month = target_date.strftime('%Y-%m')
    debut_mois = f'{year_month}-01'

    # ── Lecture des données historiques ────────────────────────────────────
    sheets_data = read_sheet(service, spreadsheet_id, DATA_SHEET)

    # Fusionner : today_rows (mémoire) + historique Sheets sans doublons du jour
    today_ids = {str(r['operateur_id']) for r in today_rows}
    historical = [
        r for r in sheets_data
        if not (r.get('date') == date_str and r.get('operateur_id') in today_ids)
    ]
    today_normalized = [_normalize_row(r) for r in today_rows]
    all_data = historical + today_normalized

    # ── Lecture des cibles ──────────────────────────────────────────────────
    targets_raw = read_sheet(service, spreadsheet_id, TARGETS_SHEET)
    targets_map: dict[tuple, dict] = {}
    for t in targets_raw:
        key = (t.get('annee_mois', ''), str(t.get('operateur_id', '')))
        targets_map[key] = {
            'cible_PMHO':              _f(t.get('cible_PMHO'))                     or 0.0,
            'cible_taux_PCA':          _f(t.get('cible_taux_PCA'))                 or 0.0,
            'jours_ouvres':            int(_f(t.get('jours_ouvres_mois'))          or 22),
            'cible_nb_propositions_j': int(_f(t.get('cible_nb_propositions_j'))    or 0),
        }

    # ── Best team PCA : meilleur taux parmi les opérateurs ayant travaillé ──
    taux_j_equipe: dict[str, float] = {}
    for row in today_rows:
        op_id = str(row['operateur_id'])
        norm  = _normalize_row(row)
        if _is_working(norm):
            taux = _f(row.get('taux_acceptation'))
            if taux is not None:
                taux_j_equipe[op_id] = taux
    best_taux = max(taux_j_equipe.values()) if taux_j_equipe else None

    # ── Calcul des flags par opérateur ─────────────────────────────────────
    flag_rows = []

    for row in today_rows:
        op_id    = str(row['operateur_id'])
        op_nom   = row['operateur_nom']
        today_r  = _normalize_row(row)

        target                = targets_map.get((year_month, op_id), {})
        cible_PMHO            = target.get('cible_PMHO',              0.0)
        cible_taux_PCA        = target.get('cible_taux_PCA',          0.0)
        jours_ouvres          = target.get('jours_ouvres',            22)
        cible_vol_j           = target.get('cible_nb_propositions_j', 0)

        # Historique du mois avant J (pour cibles glissantes et cumul mensuel)
        month_history = [
            r for r in all_data
            if r.get('operateur_id') == op_id
            and debut_mois <= r.get('date', '') < date_str
        ]

        # 1. Cibles glissantes
        cible_j_pmho = _compute_cible_j(month_history, cible_PMHO,     jours_ouvres, 'PMHO')
        cible_j_pca  = _compute_cible_j(month_history, cible_taux_PCA, jours_ouvres, 'taux_acceptation')

        # 2. Streaks (incluant aujourd'hui)
        streak_pca  = _compute_streak(all_data, op_id, 'taux_acceptation', cible_taux_PCA, target_date, today_r)
        streak_pmho = _compute_streak(all_data, op_id, 'PMHO',             cible_PMHO,     target_date, today_r)

        # 3. Records personnels (vs historique strict < J)
        pmho_j = _f(row.get('PMHO'))
        taux_j = _f(row.get('taux_acceptation'))

        hist_pmho = [_f(r.get('PMHO'))             for r in all_data if r.get('operateur_id') == op_id and r.get('date', '') < date_str]
        hist_taux = [_f(r.get('taux_acceptation'))  for r in all_data if r.get('operateur_id') == op_id and r.get('date', '') < date_str]
        hist_pmho = [v for v in hist_pmho if v is not None]
        hist_taux = [v for v in hist_taux if v is not None]

        record_pmho     = bool(pmho_j is not None and hist_pmho and pmho_j > max(hist_pmho))
        record_taux_pca = bool(taux_j is not None and hist_taux and taux_j > max(hist_taux))

        # 4. Best team PCA
        best_team_pca = bool(
            op_id in taux_j_equipe
            and best_taux is not None
            and taux_j_equipe[op_id] == best_taux
        )

        # 5. Objectifs mensuels (cumul mois incluant J)
        month_all  = month_history + [today_r]
        pmho_mois  = [_f(r.get('PMHO'))             for r in month_all if _is_working(r)]
        taux_mois  = [_f(r.get('taux_acceptation'))  for r in month_all if _is_working(r)]
        pmho_mois  = [v for v in pmho_mois if v is not None]
        taux_mois  = [v for v in taux_mois if v is not None]

        obj_pmho = bool(pmho_mois and cible_PMHO > 0
                        and (sum(pmho_mois) / len(pmho_mois)) >= cible_PMHO)
        obj_pca  = bool(taux_mois and cible_taux_PCA > 0
                        and (sum(taux_mois) / len(taux_mois)) >= cible_taux_PCA)

        # 5b. Ratio trajectoire mensuelle glissante
        # ratio = moyenne_cumulée / (cible_mensuelle × jours_travaillés / jours_ouvrés_totaux)
        def _traj_ratio(vals, cible, jours_ouvres):
            if not vals or cible == 0 or jours_ouvres == 0:
                return None
            cible_traj = cible * (len(vals) / jours_ouvres)
            if cible_traj == 0:
                return None
            return round((sum(vals) / len(vals)) / cible_traj, 4)

        traj_ratio_pmho = _traj_ratio(pmho_mois, cible_PMHO,     jours_ouvres)
        traj_ratio_pca  = _traj_ratio(taux_mois, cible_taux_PCA, jours_ouvres)

        # 6. Alertes sous-cible 3 jours
        sous_pmho_3j = _compute_sous_cible_3j(all_data, op_id, 'PMHO',             cible_PMHO,     target_date, today_r)
        sous_pca_3j  = _compute_sous_cible_3j(all_data, op_id, 'taux_acceptation', cible_taux_PCA, target_date, today_r)

        # 7. Objectif volume journalier (nb_PCA + nb_PCR >= cible_nb_propositions_j)
        nb_pca_j_int = int(_f(row.get('nb_PCA')) or 0)
        nb_pcr_j_int = int(_f(row.get('nb_PCR')) or 0)
        vol_j        = nb_pca_j_int + nb_pcr_j_int
        obj_volume   = bool(cible_vol_j > 0 and vol_j >= cible_vol_j)

        # 8. Progression PCA vs moyenne 7 jours ouvrés précédents
        progression_pca, avg_7j = _compute_progression_pca(all_data, op_id, nb_pca_j_int, target_date)
        logger.info(
            'progression_PCA -- %s (%s) : nb_PCA_J=%d, moyenne_7j=%s -> %s',
            op_id, op_nom, nb_pca_j_int,
            f'{avg_7j:.4f}' if avg_7j is not None else 'N/A (<3j ouvres)',
            progression_pca,
        )

        # Logs notables
        if record_pmho:
            logger.info('RECORD PMHO        — %s (%s) : %.2f', op_id, op_nom, pmho_j)
        if record_taux_pca:
            logger.info('RECORD taux PCA    — %s (%s) : %.4f', op_id, op_nom, taux_j)
        if best_team_pca:
            logger.info('BEST TEAM PCA      — %s (%s)', op_id, op_nom)
        if obj_pmho:
            logger.info('OBJECTIF PMHO ✓    — %s (%s)', op_id, op_nom)
        if obj_pca:
            logger.info('OBJECTIF PCA ✓     — %s (%s)', op_id, op_nom)
        if sous_pmho_3j:
            logger.warning('ALERTE sous-cible PMHO 3j  — %s (%s)', op_id, op_nom)
        if sous_pca_3j:
            logger.warning('ALERTE sous-cible PCA 3j   — %s (%s)', op_id, op_nom)

        flag_rows.append([
            date_str, op_id, op_nom,
            streak_pca, streak_pmho,
            record_pmho, record_taux_pca,
            best_team_pca,
            obj_pmho, obj_pca,
            cible_j_pmho, cible_j_pca,
            sous_pmho_3j, sous_pca_3j,
            obj_volume, progression_pca,
            traj_ratio_pmho, traj_ratio_pca,
        ])

    # ── Écriture (écrasement) de la feuille flags ───────────────────────────
    # Mettre à jour le header A1 (reflète toujours la liste FLAGS_HEADERS courante)
    api_call(lambda: service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{FLAGS_SHEET}!A1',
        valueInputOption='RAW',
        body={'values': [FLAGS_HEADERS]},
    ).execute())

    api_call(lambda: service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f'{FLAGS_SHEET}!A2:Z',
    ).execute())

    if flag_rows:
        api_call(lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{FLAGS_SHEET}!A2',
            valueInputOption='USER_ENTERED',
            body={'values': flag_rows},
        ).execute())

    logger.info('Flags calculés et pushés pour %d opérateurs', len(flag_rows))
