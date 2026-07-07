"""
Taxonomie partagée des narratifs climat et schéma de classification.

Ce module est importé par classify.py et aggregate.py pour garantir une
source unique de vérité sur les 6 narratifs et la structure JSON attendue.
"""

# Les 6 narratifs, avec leur définition exacte telle qu'utilisée dans le prompt.
NARRATIVES = {
    "URGENCE_MOBILISATION": (
        "le climat est une crise grave nécessitant une action forte et rapide"
    ),
    "SCIENCE_PEDAGOGIE": (
        "explication factuelle des mécanismes, données, rapports GIEC, registre neutre"
    ),
    "SOLUTIONS_TECHNO": (
        "focus sur les solutions (renouvelables, sobriété, innovation, gestes)"
    ),
    "SCEPTICISME_MINIMISATION": (
        "remise en cause de la gravité, du consensus, ou de l'origine humaine"
    ),
    "CRITIQUE_INACTION": (
        "critique qui RÉCLAME PLUS d'action climatique : dénonciation de l'inaction "
        "des gouvernements, du greenwashing, du lobby fossile, des promesses non tenues. "
        "Accepte la science du climat et reproche qu'on n'en fasse pas assez"
    ),
    "OPPOSITION_ECOLOGIE": (
        "critique DE l'écologie comme programme politique : « écologie punitive », "
        "rejet des ZFE / normes / contraintes environnementales, dénonciation des "
        "écologistes ou du coût des renouvelables. N'attaque pas forcément la science, "
        "mais s'oppose aux politiques écologiques"
    ),
    "ANXIETE_EFFONDREMENT": (
        "registre anxiogène, collapsologie, fatalisme, éco-anxiété"
    ),
    "HORS_SUJET": (
        "le climat n'est qu'un prétexte ou une accroche : aucun narratif climatique "
        "substantiel (marketing, divertissement, sujet sans réel rapport)"
    ),
}

# Ordre canonique (utilisé pour l'affichage et les agrégats).
NARRATIVE_KEYS = list(NARRATIVES.keys())

# Valeurs autorisées pour le champ "tonalite".
TONALITES = ["urgence", "anxiété", "neutre", "optimisme", "colère", "moquerie"]

# Valeurs autorisées pour le champ "registre".
REGISTRES = ["information", "opinion", "divertissement"]


def taxonomy_block() -> str:
    """Retourne les 6 définitions numérotées, prêtes à insérer dans le prompt."""
    lines = []
    for i, (key, definition) in enumerate(NARRATIVES.items(), start=1):
        lines.append(f"{i}. {key} : {definition}")
    return "\n".join(lines)


# Schéma de sortie attendu de la classification (documentaire / pour le prompt).
SCHEMA_DESCRIPTION = """{
  "narratif_principal": "<une des 6 valeurs ci-dessus>",
  "narratif_secondaire": "<une des 6 valeurs ou null>",
  "confiance": <float 0-1>,
  "tonalite": "<urgence|anxiété|neutre|optimisme|colère|moquerie>",
  "presence_solutions": <true|false>,
  "registre": "<information|opinion|divertissement>",
  "justification": "<une phrase>"
}"""


def is_valid_classification(obj) -> bool:
    """Validation légère de la structure renvoyée par le LLM."""
    if not isinstance(obj, dict):
        return False
    if obj.get("narratif_principal") not in NARRATIVE_KEYS:
        return False
    sec = obj.get("narratif_secondaire")
    if sec is not None and sec not in NARRATIVE_KEYS:
        return False
    if obj.get("tonalite") not in TONALITES:
        return False
    if obj.get("registre") not in REGISTRES:
        return False
    if not isinstance(obj.get("presence_solutions"), bool):
        return False
    try:
        float(obj.get("confiance"))
    except (TypeError, ValueError):
        return False
    return True
