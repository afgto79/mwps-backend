"""
main.py — Point d'entrée MWPS

Usage :
    python main.py               # date cible = aujourd'hui
    python main.py --date 20260407

Codes de sortie :
    0 = succès
    1 = erreur bloquante (fichier XLS J introuvable)
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

from parser_xls import scan_xls_dir, find_xls_files, parse_xls, compute_pmho, compute_nb_ventes_j
from parser_txt import find_txt_file, parse_txt
from aggregator import aggregate

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR  = os.path.join(BASE_DIR, 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
LOGS_DIR   = os.path.join(BASE_DIR, 'logs')
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'operators.json')

CSV_FIELDS = ['date', 'operateur_id', 'operateur_nom', 'nb_ventes_comptoir_j',
              'PMHO', 'nb_PCA', 'nb_PCR', 'taux_acceptation']


def setup_logging(target_date: date) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f'mwps_{target_date.strftime("%Y%m%d")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def parse_args() -> date:
    parser = argparse.ArgumentParser(description='MWPS — parser KPIs pharmacie')
    parser.add_argument(
        '--date',
        metavar='YYYYMMDD',
        help='Date cible du run (défaut : aujourd\'hui)',
    )
    args = parser.parse_args()
    if args.date:
        try:
            return datetime.strptime(args.date, '%Y%m%d').date()
        except ValueError:
            print(f'Erreur : format de date invalide "{args.date}" (attendu YYYYMMDD)', file=sys.stderr)
            sys.exit(1)
    return date.today()


def _fmt(value) -> str:
    """Formate une valeur pour le CSV : None → chaîne vide, float → str."""
    if value is None:
        return ''
    return str(value)


def main() -> int:
    target_date = parse_args()
    setup_logging(target_date)
    logger = logging.getLogger(__name__)

    logger.info('Run démarré — date cible : %s', target_date.isoformat())

    # --- Config opérateurs (base locale) ---
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            operators_config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error('Impossible de lire %s : %s', CONFIG_PATH, e)
        return 1

    ignore_list = operators_config.get('ignore', [])

    # --- Sync opérateurs depuis Sheets (remplace la liste locale si disponible) ---
    try:
        from sheets_client import get_service, load_settings
        _settings = load_settings()
        _svc      = get_service()
        _res      = _svc.spreadsheets().values().get(
            spreadsheetId=_settings['google_sheets_id'],
            range='operators'
        ).execute()
        _rows = _res.get('values', [])
        if len(_rows) >= 2:
            _headers = _rows[0]
            _ops = {}
            for _row in _rows[1:]:
                _obj = dict(zip(_headers, _row + [''] * len(_headers)))
                if _obj.get('actif', '').upper() == 'TRUE':
                    _ops[_obj['id']] = _obj['nom']
            if _ops:
                operators_config['operators'] = _ops
                logger.info('Opérateurs chargés depuis Sheets : %s', list(_ops.keys()))
    except Exception as _e:
        logger.warning('Sync opérateurs Sheets échoué, fallback operators.json : %s', _e)

    # --- Fichiers TXT (cumulatifs — trouvés une seule fois, filtrés par date dans la boucle) ---
    txt_991 = find_txt_file(INPUT_DIR, '991')
    txt_990 = find_txt_file(INPUT_DIR, '990')

    if txt_991 is None:
        logger.warning('Fichier TXT 991 introuvable dans input\\ — nb_PCA sera 0')
    else:
        logger.info('TXT 991 trouvé : %s', os.path.basename(txt_991))

    if txt_990 is None:
        logger.warning('Fichier TXT 990 introuvable dans input\\ — nb_PCR sera 0')
    else:
        logger.info('TXT 990 trouvé : %s', os.path.basename(txt_990))

    # --- Scan de tous les fichiers XLS disponibles ---
    all_xls = scan_xls_dir(INPUT_DIR)
    dates_to_process = sorted(d for d in all_xls if d < target_date)

    if not dates_to_process:
        logger.error('Aucun fichier XLS trouvé dans input\\ (antérieur à %s)', target_date)
        return 1

    logger.info('%d date(s) XLS à traiter : %s',
                len(dates_to_process),
                ', '.join(d.isoformat() for d in dates_to_process))

    # --- Init Sheets (une seule connexion pour tout le run) ---
    sheets_available  = False
    spreadsheet_id    = None
    service           = None
    push_data         = None
    compute_and_push_flags = None

    try:
        from sheets_client import get_service, load_settings
        from sheets_push import push_data
        from sheets_flags import compute_and_push_flags

        settings       = load_settings()
        spreadsheet_id = settings['google_sheets_id']
        service        = get_service()
        sheets_available = True
    except Exception as e:
        logger.error('Sheets inaccessible, données disponibles localement dans output/ : %s', e)

    # --- Boucle sur toutes les dates XLS ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    total_pushed  = 0
    total_skipped = 0
    last_rows: list[dict] = []
    last_data_date = None

    for data_date in dates_to_process:
        xls_j_path = all_xls[data_date]

        # J-1 = dernier fichier disponible avant data_date
        prev_dates = [d for d in all_xls if d < data_date]
        xls_j1_path = all_xls[max(prev_dates)] if prev_dates else None

        logger.info('--- %s ---', data_date.isoformat())
        logger.info('XLS J   : %s', os.path.basename(xls_j_path))
        if xls_j1_path:
            logger.info('XLS J-1 : %s', os.path.basename(xls_j1_path))
        else:
            logger.warning('XLS J-1 absent — PMHO indisponible pour cette date')

        # Parsing XLS
        try:
            xls_data = parse_xls(xls_j_path, ignore_list)
        except Exception as e:
            logger.error('Erreur lecture XLS J (%s) : %s — date ignorée', data_date, e)
            continue

        xls_j1_data = None
        if xls_j1_path is not None:
            try:
                xls_j1_data = parse_xls(xls_j1_path, ignore_list)
            except Exception as e:
                logger.warning('Erreur lecture XLS J-1, PMHO sera null : %s', e)

        pmho_data        = compute_pmho(xls_data, xls_j1_data)
        nb_ventes_j_data = compute_nb_ventes_j(xls_data, xls_j1_data)

        # Parsing TXT (filtré sur data_date — les fichiers TXT sont cumulatifs)
        pca_data: dict = {}
        pcr_data: dict = {}

        if txt_991 is not None:
            try:
                pca_data = parse_txt(txt_991, data_date)
            except Exception as e:
                logger.error('Erreur lecture TXT 991 : %s', e)

        if txt_990 is not None:
            try:
                pcr_data = parse_txt(txt_990, data_date)
            except Exception as e:
                logger.error('Erreur lecture TXT 990 : %s', e)

        # Agrégation
        rows = aggregate(data_date, xls_data, pmho_data, nb_ventes_j_data,
                         pca_data, pcr_data, operators_config)

        # Écriture CSV
        csv_path = os.path.join(OUTPUT_DIR, f'mwps_{data_date.strftime("%Y%m%d")}.csv')
        try:
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                f.write('|'.join(CSV_FIELDS) + '\n')
                for row in rows:
                    f.write('|'.join(_fmt(row[k]) for k in CSV_FIELDS) + '\n')
            logger.info('CSV écrit : %s', os.path.relpath(csv_path, BASE_DIR))
        except OSError as e:
            logger.error('Impossible d\'écrire le CSV : %s', e)

        # Push Sheets (idempotent sur data_date + operateur_id)
        if sheets_available:
            try:
                pushed, skipped = push_data(rows, data_date, spreadsheet_id, service)
                total_pushed  += pushed
                total_skipped += skipped
            except Exception as e:
                logger.error('Sheets push échoué pour %s : %s', data_date, e)

        last_rows      = rows
        last_data_date = data_date

    # --- Flags : calculés une seule fois après tous les pushs ---
    if sheets_available and last_rows and last_data_date is not None:
        try:
            compute_and_push_flags(last_data_date, last_rows, spreadsheet_id, service)
            logger.info(
                'Sheets : %d ligne(s) pushée(s), %d skippée(s), flags calculés pour %d opérateurs',
                total_pushed, total_skipped, len(last_rows),
            )
        except Exception as e:
            logger.error('Sheets flags échoué : %s', e)

    logger.info('Run terminé — %d date(s) traitée(s), %d opérateur(s) au dernier jour',
                len(dates_to_process), len(last_rows))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        logging.getLogger(__name__).error('Erreur non catchée : %s', e, exc_info=True)
        sys.exit(1)
