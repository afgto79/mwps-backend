"""
sheets_client.py — Authentification Google Sheets et utilitaires partagés

Utilisé par sheets_init, sheets_push, sheets_flags.
"""

import json
import logging
import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, 'config', 'settings.json')


def load_settings() -> dict:
    with open(SETTINGS_PATH, encoding='utf-8') as f:
        return json.load(f)


def get_service():
    """Authentifie via Service Account et retourne le client Sheets v4."""
    settings  = load_settings()
    cred_path = settings['credentials_path']

    # Fallback : chercher credentials.json dans config/ du projet si le chemin absolu est introuvable
    if not os.path.exists(cred_path):
        alt = os.path.join(BASE_DIR, 'config', 'credentials.json')
        if os.path.exists(alt):
            logger.debug('credentials_path introuvable, fallback sur %s', alt)
            cred_path = alt

    creds = service_account.Credentials.from_service_account_file(
        cred_path, scopes=SCOPES
    )
    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def api_call(callable_fn, retries: int = 3, backoff: int = 5):
    """
    Exécute un appel API Sheets avec retry sur 429 / 503.
    callable_fn doit être un callable sans argument (lambda ou partial).
    """
    for attempt in range(retries):
        try:
            return callable_fn()
        except HttpError as exc:
            if exc.resp.status in (429, 503) and attempt < retries - 1:
                logger.warning(
                    'Sheets API %d — retry %d/%d dans %ds',
                    exc.resp.status, attempt + 1, retries - 1, backoff,
                )
                time.sleep(backoff)
            else:
                raise


def read_sheet(service, spreadsheet_id: str, sheet: str) -> list[dict]:
    """
    Lit une feuille entière et retourne une liste de dicts (header = première ligne).
    Les cellules manquantes sont remplies par ''.
    """
    resp = api_call(lambda: service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet}!A:Z',
    ).execute())
    rows = resp.get('values', [])
    if len(rows) < 2:
        return []
    headers = rows[0]
    result  = []
    for row in rows[1:]:
        padded = row + [''] * (len(headers) - len(row))
        result.append(dict(zip(headers, padded)))
    return result
