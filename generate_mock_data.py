"""
generate_mock_data.py — peupler la feuille `data` avec 90 jours simulés.

Profils par opérateur différenciés (PMHO, taux_PCA).
Vide d'abord toute la feuille data (hors header) avant de repeupler.

Lancement :
    python generate_mock_data.py
"""

import logging
import random
import sys
from datetime import date, timedelta

from sheets_client import api_call, get_service, load_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DATA_SHEET   = 'data'
DATA_COLUMNS = [
    'date', 'operateur_id', 'operateur_nom', 'nb_ventes_comptoir_j',
    'PMHO', 'nb_PCA', 'nb_PCR', 'taux_acceptation',
]

OP_NAMES = {
    '1': 'DE PREMONT',
    '2': 'DUCHE CHRISTELLE',
    '7': 'MAGALHAES',
    '8': 'CARUANA',
    '9': 'MARCAGGI PAULE',
}

# Profils différenciés : (pmho_moy, pmho_sigma, taux_pca_moy, taux_pca_sigma)
OP_PROFILES = {
    '1': (18.0, 3.0, 0.65, 0.12),
    '2': (15.0, 4.0, 0.55, 0.15),
    '7': (20.0, 3.0, 0.72, 0.10),
    '8': (22.0, 4.0, 0.68, 0.12),
    '9': (14.0, 5.0, 0.50, 0.18),
}

random.seed(42)


def generate_row(day: date, op_id: str) -> dict:
    is_sunday = day.weekday() == 6

    if is_sunday:
        return {
            'date':                 day.isoformat(),
            'operateur_id':         op_id,
            'operateur_nom':        OP_NAMES[op_id],
            'nb_ventes_comptoir_j': 0,
            'PMHO':                 '',
            'nb_PCA':               0,
            'nb_PCR':               0,
            'taux_acceptation':     '',
        }

    pmho_moy, pmho_sigma, taux_moy, taux_sigma = OP_PROFILES[op_id]

    nb_ventes = random.randint(10, 30)

    pmho = round(max(5.0, random.gauss(pmho_moy, pmho_sigma)), 2)

    # Taux PCA : normal clampé entre 0.10 et 1.0
    taux_raw = random.gauss(taux_moy, taux_sigma)
    taux     = max(0.10, min(1.0, taux_raw))

    total  = random.randint(3, 8)
    nb_pca = round(total * taux)
    nb_pca = max(1, min(total, nb_pca))   # au moins 1 PCA, pas plus que total
    nb_pcr = total - nb_pca
    taux_acceptation = round(nb_pca / total, 4)

    return {
        'date':                 day.isoformat(),
        'operateur_id':         op_id,
        'operateur_nom':        OP_NAMES[op_id],
        'nb_ventes_comptoir_j': nb_ventes,
        'PMHO':                 pmho,
        'nb_PCA':               nb_pca,
        'nb_PCR':               nb_pcr,
        'taux_acceptation':     taux_acceptation,
    }


def clear_data_sheet(service, spreadsheet_id: str) -> None:
    api_call(lambda: service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range='data!A2:Z',
    ).execute())
    logger.info('Feuille data vidée (A2:Z).')


def push_rows(service, spreadsheet_id: str, rows: list[list]) -> None:
    BATCH = 500
    inserted = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        api_call(lambda b=batch: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f'{DATA_SHEET}!A1',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': b},
        ).execute())
        inserted += len(batch)
        logger.info('  %d / %d lignes insérées…', inserted, len(rows))


def log_stats(rows_dicts: list[dict]) -> None:
    logger.info('── Stats moyennes par opérateur ──────────────────────')
    for op_id, nom in OP_NAMES.items():
        working = [
            r for r in rows_dicts
            if r['operateur_id'] == op_id and r['nb_ventes_comptoir_j'] != 0
        ]
        if not working:
            continue
        pmho_vals = [r['PMHO'] for r in working if r['PMHO'] != '']
        taux_vals = [r['taux_acceptation'] for r in working if r['taux_acceptation'] != '']
        nb_ventes_vals = [r['nb_ventes_comptoir_j'] for r in working]
        nb_pca_vals  = [r['nb_PCA'] for r in working]

        avg_pmho   = round(sum(pmho_vals) / len(pmho_vals), 2)   if pmho_vals else 0
        avg_taux   = round(sum(taux_vals) / len(taux_vals), 3)   if taux_vals else 0
        avg_ventes = round(sum(nb_ventes_vals) / len(nb_ventes_vals), 1)
        avg_pca    = round(sum(nb_pca_vals) / len(nb_pca_vals), 2)

        logger.info(
            '  %-20s  PMHO moy=%-6.2f  taux_PCA moy=%-5.3f  '
            'ventes moy=%-5.1f  nb_PCA moy=%.2f  jours=%d',
            nom, avg_pmho, avg_taux, avg_ventes, avg_pca, len(working),
        )
    logger.info('──────────────────────────────────────────────────────')


def main():
    settings       = load_settings()
    spreadsheet_id = settings['google_sheets_id']
    service        = get_service()

    today  = date.today()
    start  = today - timedelta(days=90)
    days   = [start + timedelta(days=i) for i in range(90)]   # J-90 … J-1

    # Générer toutes les lignes
    rows_dicts = []
    for day in days:
        for op_id in OP_NAMES:
            rows_dicts.append(generate_row(day, op_id))

    rows_out = [
        ['' if r[col] == '' else r[col] for col in DATA_COLUMNS]
        for r in rows_dicts
    ]

    logger.info('%d lignes générées (%d jours × %d opérateurs)',
                len(rows_out), len(days), len(OP_NAMES))

    # Vider puis repeupler
    clear_data_sheet(service, spreadsheet_id)
    push_rows(service, spreadsheet_id, rows_out)
    logger.info('Terminé — %d lignes insérées au total.', len(rows_out))

    log_stats(rows_dicts)


if __name__ == '__main__':
    main()
