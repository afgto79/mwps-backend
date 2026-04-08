"""
parser_xls.py — Lecture du fichier XLS Winperformance

Retourne pour chaque opérateur ses données cumulatives du mois (Nb Ventes + CA HO TTC).
Le calcul PMHO différentiel (J - J-1) est effectué ici à partir des deux fichiers.

Nommage attendu : tdbbaroq_YYYYMM_auYYYYMMDD.xls
  YYYYMMDD = date de l'export (hier par rapport au run)
"""

import os
import re
import logging
import xlrd
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Plages de lignes (index 0-based) dans la feuille "présentation par opérateur"
BLOC_N_ROWS  = range(22, 31)   # période courante → UTILISER
BLOC_N1_ROWS = range(6, 14)    # année précédente → pour référence J-1 si même mois

XLS_SHEET_INDEX = 3
COL_OPERATEUR   = 0
COL_NB_VENTES   = 6
COL_CA_HO       = 33


def _extract_date_from_filename(filename: str) -> date | None:
    """Extrait la date YYYYMMDD depuis le nom de fichier (prend le dernier groupe de 8 chiffres)."""
    matches = re.findall(r'\d{8}', filename)
    if not matches:
        return None
    try:
        d = matches[-1]
        return date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    except ValueError:
        return None


def find_xls_files(input_dir: str, target_date: date) -> tuple[str | None, str | None]:
    """
    Cherche les fichiers XLS J et J-1 dans input_dir.

    target_date = date du run (aujourd'hui).
    XLS J   = export "au {target_date - 1 jour}"
    XLS J-1 = export "au {target_date - 2 jours}"

    Retourne (path_j, path_j1) — None si absent.
    """
    date_j  = target_date - timedelta(days=1)
    date_j1 = target_date - timedelta(days=2)

    xls_j = xls_j1 = None

    for fname in os.listdir(input_dir):
        if not fname.lower().endswith('.xls'):
            continue
        fdate = _extract_date_from_filename(fname)
        if fdate == date_j:
            xls_j = os.path.join(input_dir, fname)
        elif fdate == date_j1:
            xls_j1 = os.path.join(input_dir, fname)

    return xls_j, xls_j1


def _parse_bloc(sheet, rows: range, ignore_list: list[str]) -> dict:
    """
    Parse un bloc de lignes et retourne :
    { operator_id: {'nom': str, 'nb_ventes': float, 'ca_ho': float} }
    """
    data = {}
    for r in rows:
        row = sheet.row_values(r)
        raw = str(row[COL_OPERATEUR]).strip()

        if not raw or raw == 'TOTAL':
            continue
        if raw in ignore_list:
            continue

        parts = raw.split()
        if not parts:
            continue
        op_id = parts[0]
        nom_brut = ' '.join(parts[1:]) if len(parts) > 1 else raw

        try:
            nb_ventes = float(row[COL_NB_VENTES]) if row[COL_NB_VENTES] != '' else 0.0
            ca_ho     = float(row[COL_CA_HO])     if row[COL_CA_HO]     != '' else 0.0
        except (TypeError, ValueError):
            nb_ventes = ca_ho = 0.0

        data[op_id] = {
            'nom':       nom_brut,
            'nb_ventes': nb_ventes,
            'ca_ho':     ca_ho,
        }
    return data


def parse_xls(filepath: str, ignore_list: list[str]) -> dict:
    """
    Lit le fichier XLS et retourne les données du bloc N (période courante).
    { operator_id: {'nom', 'nb_ventes', 'ca_ho'} }
    """
    wb = xlrd.open_workbook(filepath)
    ws = wb.sheets()[XLS_SHEET_INDEX]
    return _parse_bloc(ws, BLOC_N_ROWS, ignore_list)


def compute_nb_ventes_j(data_j: dict, data_j1: dict | None) -> dict:
    """
    Calcule le Nb Ventes Comptoir du jour J = col6_J - col6_J-1.
    Retourne { operator_id: int | None }
    None si J-1 absent. 0 si différentiel négatif (anomalie, WARNING loggé).
    """
    result = {}
    for op_id, vals in data_j.items():
        if data_j1 is None:
            result[op_id] = None
            continue

        vals_prev = data_j1.get(op_id)
        if vals_prev is None:
            result[op_id] = None
            continue

        delta = int(vals['nb_ventes']) - int(vals_prev['nb_ventes'])
        if delta < 0:
            logger.warning(
                "Nb Ventes J - J-1 < 0 pour opérateur %s (anomalie : %d) — valeur forcée à 0",
                op_id, delta,
            )
            result[op_id] = 0
        else:
            result[op_id] = delta

    return result


def compute_pmho(data_j: dict, data_j1: dict | None) -> dict:
    """
    Calcule le PMHO différentiel J / J-1 pour chaque opérateur.
    Retourne { operator_id: float | None }
    """
    pmho = {}
    for op_id, vals in data_j.items():
        if data_j1 is None:
            pmho[op_id] = None
            continue

        vals_prev = data_j1.get(op_id)
        if vals_prev is None:
            pmho[op_id] = None
            continue

        delta_ventes = vals['nb_ventes'] - vals_prev['nb_ventes']
        delta_ca     = vals['ca_ho']     - vals_prev['ca_ho']

        if delta_ventes == 0:
            logger.warning(
                "PMHO indisponible pour opérateur %s : Nb Ventes J - J-1 = 0", op_id
            )
            pmho[op_id] = None
        else:
            pmho[op_id] = round(delta_ca / delta_ventes, 2)

    return pmho
