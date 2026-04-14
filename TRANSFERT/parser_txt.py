"""
parser_txt.py — Lecture des fichiers TXT 990 (PCR) et 991 (PCA)

Les fichiers sont cumulatifs (toutes les mouvements depuis init).
Filtre obligatoire : ne garder que les lignes dont la date == target_date.

Ligne utile : champ Commentaires contient "Facture N" et Modifs == -1
Ligne ignorée : "Fiche produit" (initialisation stock +100)

Format colonnes : | Date | Modifs | Commentaires | Poste | Opér. |
Encodage : ISO-8859-1, fins de ligne CRLF
"""

import os
import re
import glob
import logging
from datetime import date

logger = logging.getLogger(__name__)


def _parse_operator_id(raw: str) -> str:
    """Extrait l'ID numérique depuis le champ Opér. (ex: '8*' → '8', '1  ' → '1')."""
    digits = re.sub(r'[^\d]', '', raw.strip())
    return digits if digits else raw.strip()


def find_txt_file(input_dir: str, cip: str) -> str | None:
    """
    Cherche le fichier TXT le plus récent pour le CIP donné (990 ou 991).
    Retourne le chemin ou None.
    """
    pattern = os.path.join(input_dir, f'{cip}_*.TXT')
    matches = glob.glob(pattern)
    if not matches:
        # Essai insensible à la casse sur l'extension
        pattern_lower = os.path.join(input_dir, f'{cip}_*.txt')
        matches = glob.glob(pattern_lower)
    if not matches:
        return None
    # En cas de fichiers multiples, prendre le plus récemment modifié
    return max(matches, key=os.path.getmtime)


def parse_txt(filepath: str, target_date: date) -> dict:
    """
    Parse un fichier TXT 990 ou 991 et retourne le nombre de passages
    par opérateur pour target_date.

    Retourne : { operator_id: int }
    """
    target_str = target_date.strftime('%d/%m/%y')  # ex: '07/04/26'
    counts: dict[str, int] = {}

    with open(filepath, encoding='iso-8859-1', newline='') as f:
        for line in f:
            line = line.rstrip('\r\n')

            # Ignorer en-têtes, séparateurs, lignes vides
            if not line.startswith('|'):
                continue
            stripped = line.lstrip('|').strip()
            if stripped.startswith('-') or stripped.startswith('H'):
                continue

            fields = [f.strip() for f in line.split('|')]
            # Structure attendue : ['', date, modifs, commentaires, poste, oper, '']
            # Au moins 6 champs utiles
            if len(fields) < 6:
                continue

            date_field    = fields[1].strip()
            modifs_field  = fields[2].strip()
            comment_field = fields[3].strip()
            oper_field    = fields[5].strip()

            # Filtre date
            if not date_field.startswith(target_str):
                continue

            # Filtre type de mouvement
            if 'Facture N' not in comment_field:
                continue

            try:
                modifs = int(modifs_field)
            except ValueError:
                continue
            if modifs != -1:
                continue

            op_id = _parse_operator_id(oper_field)
            if not op_id:
                continue

            counts[op_id] = counts.get(op_id, 0) + 1

    return counts
