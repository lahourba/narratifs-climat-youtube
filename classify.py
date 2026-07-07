#!/usr/bin/env python3
"""
classify.py — Étape 3 du pipeline.

Pour chaque vidéo, appelle l'API Anthropic (modèle claude-sonnet-4-6) pour
classer sa narration dominante selon la taxonomie des 6 narratifs.

- Entrée du LLM : titre + description + extrait de transcript (1500 premiers mots).
- Sortie LLM : JSON strict (voir taxonomy.SCHEMA_DESCRIPTION).
- Parsing robuste : strip des ``` éventuels, retry 1x si JSON invalide.
- Rate limiting léger entre les appels.
- Idempotent : les vidéos déjà classées sont sautées (sauf --force).
- Ne crashe jamais sur une vidéo isolée : log et continue.

Sortie : data/videos_classified.json

Pré-requis : variable d'environnement ANTHROPIC_API_KEY.

Usage :
    python classify.py
    python classify.py --limit 50      # ne classe que 50 vidéos (test)
    python classify.py --force         # reclasse tout
"""

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import (data_path, ensure_data_dir, load_json, log, now_iso,
                    save_json, truncate_words)
from taxonomy import (SCHEMA_DESCRIPTION, is_valid_classification, taxonomy_block)

INPUT_FILE = data_path("videos_with_transcripts.json")
OUTPUT_FILE = data_path("videos_classified.json")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 600

# Extrait de transcript fourni au LLM (premiers mots), configurable via env.
# 1500 par défaut : bon compromis coût/latence (le transcript moyen fait ~1000 mots),
# surtout pour les modèles bon marché. Monter à 3000 pour plus de contexte.
TRANSCRIPT_WORDS = int(os.environ.get("TRANSCRIPT_WORDS", "1500"))
# Description tronquée pour limiter les tokens.
DESCRIPTION_WORDS = 300

# Parallélisme : nombre d'appels API simultanés (le SDK Anthropic est thread-safe).
DEFAULT_WORKERS = 8
# Tentatives par vidéo (gère JSON invalide ET rate-limit/erreurs transitoires).
MAX_ATTEMPTS = 4

PROMPT_TEMPLATE = """Tu es un analyste de discours médiatique. Classe cette vidéo YouTube francophone sur le climat selon sa NARRATION DOMINANTE.

Voici la taxonomie :
{taxonomy}

Règles de désambiguïsation (IMPORTANTES) :
- Classe selon la POSITION RÉELLEMENT PORTÉE par la vidéo, pas selon les seuls mots du titre. Un titre qui cite un argument sceptique pour le critiquer reste du côté de la critique ou de la science.
- Une vidéo qui DÉNONCE, DOCUMENTE, ENQUÊTE SUR ou RÉFUTE le climatoscepticisme (ex. « le déni est organisé depuis 30 ans », rétrospective d'archives sur le climatoscepticisme, débunkage) n'est PAS SCEPTICISME_MINIMISATION. La catégorie SCEPTICISME_MINIMISATION s'applique UNIQUEMENT si la vidéo elle-même met en doute la gravité, le consensus scientifique ou l'origine humaine du changement climatique.
  → Si elle dénonce les sceptiques ou les responsables politiques : CRITIQUE_POLITIQUE_ECOLO.
  → Si elle explique ou réfute factuellement les arguments sceptiques : SCIENCE_PEDAGOGIE.
- Distingue bien CRITIQUE_INACTION, OPPOSITION_ECOLOGIE et SCEPTICISME_MINIMISATION — ce sont trois choses opposées :
  • CRITIQUE_INACTION = on veut PLUS d'écologie, on reproche l'inaction / le greenwashing / le lobby fossile (ex. Jancovici dénonçant l'inaction des gouvernements, dénonciation de la finance verte). Accepte la science.
  • OPPOSITION_ECOLOGIE = on s'oppose AUX POLITIQUES écologiques jugées punitives/coûteuses (ex. anti-ZFE, « ma voiture interdite », coût des éoliennes, écologie punitive). N'attaque pas forcément la science du climat.
  • SCEPTICISME_MINIMISATION = on conteste la SCIENCE elle-même (gravité, consensus, origine humaine).
  Une même vidéo de droite peut faire les trois ; choisis ce qui DOMINE.
- SCIENCE_PEDAGOGIE vs SOLUTIONS_TECHNO : ne mets SOLUTIONS_TECHNO que si le SUJET CENTRAL est une solution / techno / geste (« comment faire », « cette techno réduit X »). Si la vidéo explique surtout les mécanismes, les données ou les impacts et ne fait que mentionner des solutions au passage → SCIENCE_PEDAGOGIE.
- URGENCE_MOBILISATION vs CRITIQUE_INACTION : ne mets CRITIQUE_INACTION que si l'acte DOMINANT est de dénoncer des acteurs précis (gouvernement, lobby, entreprises, greenwashing). Un simple appel général à agir / à prendre la crise au sérieux, sans cibler d'acteur → URGENCE_MOBILISATION.
- Juge l'INTENTION, pas le premier degré : une vidéo ironique, satirique ou humoristique qui singe un discours sceptique pour le moquer n'est PAS SCEPTICISME_MINIMISATION.
- Le narratif_secondaire ne sert qu'à nuancer ; le narratif_principal doit refléter l'intention dominante de l'auteur.
- Si le climat n'est qu'un prétexte / une accroche et qu'il n'y a aucun narratif climatique substantiel (marketing, divertissement, sujet sans réel rapport) → narratif_principal = HORS_SUJET.

Analyse le titre, la description et l'extrait de transcript fournis. Réponds UNIQUEMENT par un objet JSON valide respectant ce schéma :
{schema}

Aucun texte hors du JSON.

Titre : {title}
Description : {description}
Transcript (extrait) : {transcript_excerpt}"""


def build_prompt(video: dict) -> str:
    """Construit le prompt de classification pour une vidéo."""
    transcript = video.get("transcript") or "(transcript indisponible)"
    return PROMPT_TEMPLATE.format(
        taxonomy=taxonomy_block(),
        schema=SCHEMA_DESCRIPTION,
        title=video.get("title", ""),
        description=truncate_words(video.get("description", ""), DESCRIPTION_WORDS),
        transcript_excerpt=truncate_words(transcript, TRANSCRIPT_WORDS),
    )


def extract_json(text: str):
    """
    Parsing robuste de la réponse LLM : retire d'éventuels fences ``` et
    isole le premier objet JSON. Retourne le dict ou None.
    """
    if not text:
        return None
    cleaned = text.strip()
    # Retire les fences markdown ```json ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # Tente un parse direct.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Sinon, isole le premier bloc {...}.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def classify_one(complete, video: dict):
    """
    Classe une vidéo via le fournisseur LLM (voir llm.py). Retourne le dict de
    classification valide, ou un dict d'erreur — ne lève jamais.
    """
    prompt = build_prompt(video)

    for attempt in range(MAX_ATTEMPTS):
        try:
            text = complete(prompt, MAX_TOKENS)
        except Exception as e:  # noqa: BLE001 — erreur API : on retente avec backoff
            name = type(e).__name__
            msg = str(e).lower()
            is_rate = "ratelimit" in name.lower() or "429" in msg or "overloaded" in msg
            if attempt < MAX_ATTEMPTS - 1:
                # Backoff plus long sur rate-limit (utile en parallèle).
                time.sleep((6 if is_rate else 2) * (attempt + 1))
                continue
            return {"classification_error": f"api:{name}"}

        parsed = extract_json(text)
        if parsed and is_valid_classification(parsed):
            return parsed

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(1)  # JSON invalide : nouvel essai

    return {"classification_error": "json_invalide_ou_api_indisponible"}


def main():
    parser = argparse.ArgumentParser(description="Classification des vidéos via l'API Anthropic.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Ne classe qu'un sous-ensemble de N vidéos (les N premières, "
                             "ou les N plus vues avec --by-views).")
    parser.add_argument("--by-views", action="store_true",
                        help="Cible les vidéos les plus vues (à combiner avec --limit). "
                             "Cohérent avec la pondération par les vues du projet.")
    parser.add_argument("--force", action="store_true",
                        help="Reclasse même les vidéos déjà classées.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Appels API simultanés (défaut {DEFAULT_WORKERS}).")
    parser.add_argument("--reclassify-label", type=str, default=None,
                        help="Reclasse UNIQUEMENT les vidéos dont le narratif principal "
                             "actuel est ce label (ex. après un split de taxonomie).")
    args = parser.parse_args()

    try:
        from llm import get_completer
        complete, provider_name = get_completer()
        log(f"Fournisseur LLM : {provider_name}")
    except Exception as e:  # noqa: BLE001
        log(f"ERREUR : impossible d'initialiser le fournisseur LLM ({e}). "
            f"Vérifie LLM_PROVIDER et les clés/serveur associés.")
        return

    ensure_data_dir()
    videos = load_json(INPUT_FILE, default=None)
    if videos is None:
        log(f"ERREUR : {INPUT_FILE} introuvable. Lance d'abord transcripts.py.")
        return

    existing = {v["video_id"]: v for v in (load_json(OUTPUT_FILE, default=[]) or [])}

    # Détermine l'ensemble cible quand --limit est fourni : soit les N premières
    # vidéos du fichier, soit les N plus vues (--by-views). On classe uniquement
    # cette cible ; le reste est conservé tel quel dans la sortie (rien n'est perdu).
    target_ids = None
    if args.limit is not None:
        pool = videos
        if args.by_views:
            pool = sorted(videos, key=lambda v: v.get("view_count") or 0, reverse=True)
        target_ids = {v["video_id"] for v in pool[:args.limit]}
        how = "les plus vues" if args.by_views else "les premières"
        log(f"Cible : {len(target_ids)} vidéos ({how}).")

    # Partition : on aligne la sortie sur l'ordre d'entrée (out[idx]).
    #  - déjà classée (idempotence) → réutilisée telle quelle
    #  - hors cible → conservée telle quelle (non classée)
    #  - sinon → à classer (en parallèle)
    out = [None] * len(videos)
    to_do = []
    skipped = 0
    for idx, video in enumerate(videos):
        vid = video["video_id"]
        prev = existing.get(vid)
        prev_label = (prev or {}).get("classification", {}).get("narratif_principal")

        # Mode reclassification ciblée : on ne traite QUE les vidéos portant le label
        # visé ; tout le reste est conservé tel quel (rien d'autre n'est (re)classé).
        if args.reclassify_label is not None:
            if prev_label == args.reclassify_label:
                to_do.append((idx, video))
            else:
                out[idx] = prev or video
            continue

        # Mode normal.
        if prev and not args.force and prev.get("classification") and \
                "classification_error" not in prev.get("classification", {}):
            out[idx] = prev
            skipped += 1
            continue
        if target_ids is not None and vid not in target_ids:
            out[idx] = prev or video
            continue
        to_do.append((idx, video))

    log(f"{len(to_do)} vidéo(s) à classer, {skipped} réutilisées, "
        f"{args.workers} appels simultanés.")

    lock = threading.Lock()
    counters = {"done": 0, "errors": 0}

    def work(item):
        idx, video = item
        classification = classify_one(complete, video)
        record = dict(video)
        record["classification"] = classification
        record["classified_at"] = now_iso()
        return idx, record, classification

    if to_do:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(work, item) for item in to_do]
            for n, fut in enumerate(as_completed(futures), 1):
                idx, record, classification = fut.result()
                out[idx] = record
                with lock:
                    if "classification_error" in classification:
                        counters["errors"] += 1
                    else:
                        counters["done"] += 1
                    if n % 25 == 0:
                        log(f"  {n}/{len(to_do)} traitées "
                            f"(ok={counters['done']}, erreurs={counters['errors']})…")
                        save_json(OUTPUT_FILE, [o for o in out if o is not None])

    save_json(OUTPUT_FILE, [o for o in out if o is not None])
    written = sum(1 for o in out if o is not None)
    log("-" * 60)
    log(f"Terminé : {counters['done']} classées, {skipped} réutilisées, "
        f"{counters['errors']} en erreur. Total écrit : {written} dans {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()
