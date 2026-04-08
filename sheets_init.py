"""
sheets_init.py — Initialisation unique de la structure Google Sheets

Crée les 3 feuilles (data / targets / flags) si absentes,
pose les en-têtes, et pré-remplit targets avec les 5 opérateurs du mois courant.

Utilisation : python sheets_init.py
"""

import logging
import sys
from datetime import date

from sheets_client import api_call, get_service, load_settings

logger = logging.getLogger(__name__)

# ── En-têtes ────────────────────────────────────────────────────────────────

DATA_HEADERS = [
    'date', 'operateur_id', 'operateur_nom', 'nb_ventes_comptoir_j',
    'PMHO', 'nb_PCA', 'nb_PCR', 'taux_acceptation',
]

TARGETS_HEADERS = [
    'annee_mois', 'operateur_id', 'operateur_nom',
    'cible_PMHO', 'cible_taux_PCA', 'cible_nb_propositions_j', 'jours_ouvres_mois',
]

FLAGS_HEADERS = [
    'date', 'operateur_id', 'operateur_nom',
    'streak_PCA', 'streak_PMHO',
    'record_PMHO', 'record_taux_PCA',
    'best_team_PCA',
    'objectif_mensuel_PMHO_atteint', 'objectif_mensuel_PCA_atteint',
    'cible_j_PMHO', 'cible_j_PCA',
    'sous_cible_PMHO_3j', 'sous_cible_PCA_3j',
    'objectif_volume_atteint', 'progression_PCA',
]

INITIAL_OPERATORS = [
    ('1', 'DE PREMONT'),
    ('2', 'DUCHE CHRISTELLE'),
    ('7', 'MAGALHAES'),
    ('8', 'CARUANA'),
    ('9', 'MARCAGGI PAULE'),
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def _existing_sheet_names(service, spreadsheet_id: str) -> list[str]:
    resp = api_call(lambda: service.spreadsheets().get(
        spreadsheetId=spreadsheet_id
    ).execute())
    return [s['properties']['title'] for s in resp.get('sheets', [])]


def _add_sheet(service, spreadsheet_id: str, title: str) -> None:
    api_call(lambda: service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': [{'addSheet': {'properties': {'title': title}}}]},
    ).execute())
    logger.info('Feuille créée : %s', title)


def _set_header(service, spreadsheet_id: str, sheet: str, headers: list[str]) -> None:
    api_call(lambda: service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet}!A1',
        valueInputOption='RAW',
        body={'values': [headers]},
    ).execute())
    logger.info('En-têtes posés sur %s (%d colonnes)', sheet, len(headers))


def add_missing_columns(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    headers: list[str],
) -> None:
    """
    Vérifie quelles colonnes de `headers` sont absentes de la ligne 1 du sheet
    et les ajoute à la fin, sans toucher aux données existantes.
    """
    resp = api_call(lambda: service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!1:1',
    ).execute())
    current = resp.get('values', [[]])[0] if resp.get('values') else []

    missing = [h for h in headers if h not in current]
    if not missing:
        logger.info('%s : schema a jour, aucune colonne manquante', sheet_name)
        return

    new_header_row = current + missing
    api_call(lambda: service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!A1',
        valueInputOption='RAW',
        body={'values': [new_header_row]},
    ).execute())
    logger.info('%s : %d colonne(s) ajoutee(s) : %s', sheet_name, len(missing), missing)


def _row_count(service, spreadsheet_id: str, sheet: str) -> int:
    resp = api_call(lambda: service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet}!A:A',
    ).execute())
    return len(resp.get('values', []))


# ── Point d'entrée ───────────────────────────────────────────────────────────

def run_init(spreadsheet_id: str = None, service=None) -> None:
    if service is None:
        service = get_service()
    if spreadsheet_id is None:
        spreadsheet_id = load_settings()['google_sheets_id']

    existing = _existing_sheet_names(service, spreadsheet_id)
    logger.info('Feuilles existantes : %s', existing)

    # Créer les feuilles manquantes (headers complets) ou compléter les existantes
    for sheet_name, headers in [
        ('data',    DATA_HEADERS),
        ('targets', TARGETS_HEADERS),
        ('flags',   FLAGS_HEADERS),
    ]:
        if sheet_name not in existing:
            _add_sheet(service, spreadsheet_id, sheet_name)
            _set_header(service, spreadsheet_id, sheet_name, headers)
        else:
            add_missing_columns(service, spreadsheet_id, sheet_name, headers)

    # Pré-remplir targets si vide (seulement header présent)
    n_rows = _row_count(service, spreadsheet_id, 'targets')
    if n_rows <= 1:
        month_str = date.today().strftime('%Y-%m')
        rows = [[month_str, op_id, op_nom, 0.0, 0.0, 22]
                for op_id, op_nom in INITIAL_OPERATORS]
        api_call(lambda: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='targets!A2',
            valueInputOption='USER_ENTERED',
            body={'values': rows},
        ).execute())
        logger.info(
            'targets initialisé : %d opérateurs pour %s (cibles à renseigner manuellement)',
            len(rows), month_str,
        )
    else:
        logger.info('targets déjà renseigné (%d lignes de données)', n_rows - 1)

    logger.info('Initialisation terminée.')


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    run_init()
