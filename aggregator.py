"""
aggregator.py — Fusion des données XLS et TXT, calcul des KPIs finaux

Produit une liste de dicts prête à écrire en CSV pipe-séparé.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def aggregate(
    target_date: date,
    xls_data: dict,
    pmho_data: dict,
    nb_ventes_j_data: dict,
    pca_data: dict,
    pcr_data: dict,
    operators_config: dict,
) -> list[dict]:
    """
    Fusionne les données et retourne les lignes KPI.

    xls_data         : { op_id: {'nom', 'nb_ventes', 'ca_ho'} }
    pmho_data        : { op_id: float | None }
    nb_ventes_j_data : { op_id: int | None }  (différentiel col6 J - J-1)
    pca_data         : { op_id: int }   (comptages TXT 991)
    pcr_data         : { op_id: int }   (comptages TXT 990)
    operators_config : contenu de operators.json
    """
    op_map    = operators_config.get('operators', {})
    date_str  = target_date.strftime('%Y-%m-%d')
    rows      = []

    for op_id, vals in xls_data.items():
        # Résolution du nom
        if op_id in op_map:
            nom = op_map[op_id]
        else:
            nom = vals['nom']
            logger.warning(
                'Nouvel opérateur détecté — ID=%s, nom brut="%s %s" (non mappé dans operators.json)',
                op_id, op_id, nom,
            )

        pmho          = pmho_data.get(op_id)
        nb_ventes_j   = nb_ventes_j_data.get(op_id)
        nb_pca = pca_data.get(op_id, 0)
        nb_pcr = pcr_data.get(op_id, 0)

        total = nb_pca + nb_pcr
        taux  = round(nb_pca / total, 4) if total > 0 else None

        rows.append({
            'date':                  date_str,
            'operateur_id':          op_id,
            'operateur_nom':         nom,
            'nb_ventes_comptoir_j':  nb_ventes_j,
            'PMHO':                  pmho,
            'nb_PCA':                nb_pca,
            'nb_PCR':                nb_pcr,
            'taux_acceptation':      taux,
        })

    return rows
