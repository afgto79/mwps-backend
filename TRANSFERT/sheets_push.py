"""
sheets_push.py — Append des données journalières vers la feuille `data`

Règle d'idempotence : si (date=J, operateur_id=X) existe déjà → skip.
Permet de relancer main.py sans créer de doublons.
"""

import logging
from datetime import date, timedelta

from sheets_client import api_call, get_service, load_settings, read_sheet

_EXCEL_EPOCH = date(1899, 12, 30)


def _normalize_date(v) -> str:
    """Convertit une date Sheets (serial Excel ou texte ISO) en ISO 'YYYY-MM-DD'."""
    try:
        n = int(float(str(v)))
        if n > 40000:
            return (_EXCEL_EPOCH + timedelta(days=n)).isoformat()
    except (ValueError, TypeError):
        pass
    return str(v)

logger = logging.getLogger(__name__)

DATA_SHEET = 'data'
DATA_COLUMNS = [
    'date', 'operateur_id', 'operateur_nom', 'nb_ventes_comptoir_j',
    'PMHO', 'nb_PCA', 'nb_PCR', 'taux_acceptation',
]


def _row_to_list(row: dict) -> list:
    """Convertit un dict agrégateur en liste ordonnée pour Sheets."""
    return ['' if row.get(col) is None else row[col] for col in DATA_COLUMNS]


def push_data(
    rows: list[dict],
    target_date: date,
    spreadsheet_id: str = None,
    service=None,
) -> tuple[int, int]:
    """
    Appende les lignes du jour dans la feuille `data`.

    Retourne (nb_pushées, nb_skippées).
    """
    if service is None:
        service = get_service()
    if spreadsheet_id is None:
        spreadsheet_id = load_settings()['google_sheets_id']

    date_str = target_date.isoformat()

    # Lire les clés existantes pour ce jour (idempotence)
    # Sheets peut renvoyer la date comme serial Excel (ex: 46118) ou ISO → normalisation
    existing = read_sheet(service, spreadsheet_id, DATA_SHEET)
    existing_keys = {
        str(r.get('operateur_id', ''))
        for r in existing
        if _normalize_date(r.get('date', '')) == date_str
    }

    to_push = []
    skipped = 0

    for row in rows:
        key = str(row['operateur_id'])
        if key in existing_keys:
            logger.info(
                'Données J déjà présentes pour opérateur %s, skip', row['operateur_id']
            )
            skipped += 1
        else:
            to_push.append(_row_to_list(row))

    if to_push:
        api_call(lambda: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f'{DATA_SHEET}!A1',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': to_push},
        ).execute())

    pushed = len(to_push)
    logger.info('Sheets data : %d ligne(s) pushée(s), %d skippée(s)', pushed, skipped)
    return pushed, skipped
