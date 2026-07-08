#!/usr/bin/env python3
"""
comments.py — PROTOTYPE : analyse du « climat de la section commentaires ».

Idée : une vidéo peut être neutre alors que ses commentaires sont virulents
(climatosceptiques, hostiles à l'écologie, complotistes). On mesure donc une
dimension DIFFÉRENTE du narratif de la vidéo : la réaction de l'audience.

Pour un échantillon de vidéos :
  1. récupère les commentaires les plus visibles (YouTube commentThreads.list, ~1 unité quota/vidéo) ;
  2. classe le climat de la section via l'API Anthropic.

Sortie : data/videos_comments.json
Comparée au narratif de la vidéo (videos_classified.json) pour montrer les écarts.

Usage :
    python comments.py --by-views --limit 20
    python comments.py --ids abc123,def456

Pré-requis : YOUTUBE_API_KEY et ANTHROPIC_API_KEY (dans .env).
"""

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from common import data_path, ensure_data_dir, load_json, log, now_iso, save_json

INPUT_FILE = data_path("videos_classified.json")
OUTPUT_FILE = data_path("videos_comments.json")
# Export slim pour le dashboard (dict keyé par video_id).
DASHBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "dashboard", "src", "data", "comments.json")
DEFAULT_WORKERS = 8

API_BASE = "https://www.googleapis.com/youtube/v3"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400

MAX_COMMENTS = 30          # commentaires top-niveau analysés par vidéo
COMMENT_WORD_CAP = 45      # tronque chaque commentaire

# Climats possibles de la section commentaires (≠ narratif de la vidéo).
COMMENT_CLIMATES = [
    "adhesion_science", "critique_methode", "colere_inaction",
    "scepticisme_deni", "hostilite_ecologie",
    "complotisme", "anxiete", "moquerie", "neutre", "hors_sujet", "mixte",
]

# Définitions injectées dans le prompt. Leçon du kappa vidéo : sans définitions
# ni règles de tranchement, le modèle range tout commentaire négatif sous une
# vidéo « verte » dans hostilite_ecologie (ex. : des connaisseurs qui critiquent
# une monoculture AU NOM de la biodiversité, ou la colère contre un État qui
# gère mal une canicule).
CLIMATE_DEFINITIONS = """Définitions :
- adhesion_science : accepte la réalité du changement climatique, soutient ou complète la vidéo.
- critique_methode : négatif envers la SOLUTION présentée, AU NOM de l'environnement (monoculture, biodiversité, greenwashing, « fausse bonne idée »). Critiquer une solution n'est PAS être hostile à l'écologie.
- colere_inaction : colère contre l'État / les responsables parce qu'ils n'en font PAS ASSEZ (adaptation, prévention, moyens). Réclame plus d'action.
- scepticisme_deni : nie ou minimise le changement climatique ou son origine humaine.
- hostilite_ecologie : s'oppose à l'action climatique, aux politiques écologiques ou aux écologistes EN TANT QUE TELS (« écologie punitive », rejet des ZFE/éoliennes parce qu'écolos).
- complotisme : y voit une manipulation, un agenda caché.
- anxiete : peur, fatalisme, éco-anxiété dominants.
- moquerie : ironie / dérision dominante.
- neutre : factuel, questions, sans position nette.
- mixte : plusieurs camps s'affrontent sans dominante.
- hors_sujet : les commentaires ne parlent ni de climat ni d'écologie.

Règles de tranchement :
- hostilite_ecologie SEULEMENT si l'hostilité vise l'écologie ou l'action climatique ELLE-MÊME.
- Colère contre la gestion d'une canicule ou le manque de moyens → colere_inaction.
- Critique d'un projet « vert » pour ses dégâts environnementaux → critique_methode.
- Défiance envers médias/institutions sans rejet de l'écologie → neutre, mixte ou hors_sujet selon le contenu."""

PROMPT = """Tu analyses le CLIMAT DE LA SECTION COMMENTAIRES d'une vidéo YouTube sur le climat — c'est-à-dire la réaction de l'audience, PAS le contenu de la vidéo.

{definitions}

Voici le titre de la vidéo et un échantillon de ses commentaires les plus visibles.
Réponds UNIQUEMENT par un objet JSON valide :
{{
  "climat_dominant": "<une valeur parmi : {climates}>",
  "part_sceptique_pct": <entier 0-100, part des commentaires qui nient ou minimisent la science du climat>,
  "part_hostile_ecologie_pct": <entier 0-100, part hostile aux politiques écolo / aux écologistes>,
  "virulence": <float 0-1>,
  "resume": "<une phrase en français>"
}}
Aucun texte hors du JSON.

Titre de la vidéo : {title}

Commentaires :
{comments}"""


def fetch_comments(video_id: str, api_key: str):
    """
    Récupère jusqu'à MAX_COMMENTS commentaires top-niveau (par pertinence).
    Retourne (liste, status) : status ∈ {ok, disabled, none, error}.
    """
    params = {
        "part": "snippet", "videoId": video_id, "maxResults": 100,
        "order": "relevance", "textFormat": "plainText", "key": api_key,
    }
    try:
        r = requests.get(f"{API_BASE}/commentThreads", params=params, timeout=30)
    except requests.RequestException as e:
        return [], f"error:{type(e).__name__}"
    if r.status_code == 403:
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        reason = ""
        try:
            reason = body["error"]["errors"][0]["reason"]
        except (KeyError, IndexError, TypeError):
            pass
        if reason in ("commentsDisabled",):
            return [], "disabled"
        return [], f"error:403:{reason}"
    if r.status_code != 200:
        return [], f"error:{r.status_code}"

    items = r.json().get("items", [])
    comments = []
    for it in items[:MAX_COMMENTS]:
        try:
            sn = it["snippet"]["topLevelComment"]["snippet"]
            txt = (sn.get("textDisplay") or "").strip()
            if txt:
                comments.append(" ".join(txt.split()[:COMMENT_WORD_CAP]))
        except (KeyError, TypeError):
            continue
    return comments, ("ok" if comments else "none")


def extract_json(text: str):
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def classify_comments(complete, title: str, comments: list):
    """Classe le climat de la section. Retourne un dict ou {'error': ...}."""
    joined = "\n".join(f"- {c}" for c in comments)
    prompt = PROMPT.format(definitions=CLIMATE_DEFINITIONS,
                           climates="|".join(COMMENT_CLIMATES), title=title, comments=joined)
    MAX_ATTEMPTS = 6
    for attempt in range(MAX_ATTEMPTS):
        try:
            text = complete(prompt, MAX_TOKENS)
        except Exception as e:  # noqa: BLE001
            # Backoff plus long sur rate-limit (429) — fréquent sur Gemini gratuit.
            msg = str(e).lower()
            is_rate = any(k in msg for k in ("429", "too many requests", "quota", "resource"))
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep((8 if is_rate else 2) * (attempt + 1))
            continue
        parsed = extract_json(text)
        if isinstance(parsed, dict) and parsed.get("climat_dominant") in COMMENT_CLIMATES:
            return parsed
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(1)
    return {"error": "json_invalide_ou_api"}


def main():
    parser = argparse.ArgumentParser(description="Prototype : climat des commentaires.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--by-views", action="store_true")
    parser.add_argument("--ids", type=str, default=None, help="Liste de video_id séparés par des virgules.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Vidéos traitées en parallèle (défaut {DEFAULT_WORKERS}).")
    parser.add_argument("--force", action="store_true",
                        help="Re-analyse tout (re-télécharge les commentaires et reclasse), "
                             "utile après un changement de taxonomie/prompt.")
    args = parser.parse_args()

    yt_key = os.environ.get("YOUTUBE_API_KEY")
    if not yt_key:
        log("ERREUR : YOUTUBE_API_KEY absente.")
        return
    try:
        from llm import get_completer
        complete, provider = get_completer()
        log(f"Fournisseur LLM : {provider}")
    except Exception as e:  # noqa: BLE001
        log(f"ERREUR init LLM : {e}")
        return

    ensure_data_dir()
    videos = load_json(INPUT_FILE, default=None)
    if videos is None:
        log(f"ERREUR : {INPUT_FILE} introuvable.")
        return

    # Ne garder que les vidéos classées, ET cohérentes avec le rapport :
    # français avéré + hors HORS_SUJET (mêmes exclusions que aggregate.py).
    classified = [v for v in videos if isinstance(v.get("classification"), dict)
                  and "classification_error" not in v["classification"]
                  and v.get("lang") == "fr"
                  and v["classification"].get("narratif_principal") != "HORS_SUJET"]

    if args.ids:
        wanted = set(args.ids.split(","))
        sample = [v for v in classified if v["video_id"] in wanted]
    else:
        pool = sorted(classified, key=lambda v: v.get("view_count") or 0, reverse=True) \
            if args.by_views else classified
        sample = pool[:args.limit]

    # Reprise : on réutilise les analyses déjà valides (ou terminales : commentaires
    # désactivés/absents) et on ne (re)traite QUE les vidéos échouées ou nouvelles.
    existing = {r["video_id"]: r for r in (load_json(OUTPUT_FILE, default=[]) or [])}

    def is_done(v):
        if args.force:
            return False
        r = existing.get(v["video_id"])
        if not r:
            return False
        if r.get("comments_status") in ("disabled", "none"):
            return True  # terminal : pas de commentaires à analyser
        return bool((r.get("comment_climate") or {}).get("climat_dominant"))

    reused = [existing[v["video_id"]] for v in sample if is_done(v)]
    todo = [v for v in sample if not is_done(v)]
    log(f"Commentaires : {len(todo)} à traiter, {len(reused)} réutilisées "
        f"({args.workers} en parallèle)…")

    results = list(reused)
    lock = threading.Lock()
    done = {"n": 0}

    def work(v):
        comments, status = fetch_comments(v["video_id"], yt_key)
        rec = {
            "video_id": v["video_id"], "title": v.get("title", ""),
            "channel_title": v.get("channel_title", ""), "view_count": v.get("view_count"),
            "narratif_video": v["classification"]["narratif_principal"],
            "n_comments": len(comments), "comments_status": status,
            "analyzed_at": now_iso(),
        }
        if status == "ok":
            rec["comment_climate"] = classify_comments(complete, v.get("title", ""), comments)
        else:
            rec["comment_climate"] = {"climat_dominant": None, "status": status}
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, v) for v in todo]
        for fut in as_completed(futures):
            rec = fut.result()
            with lock:
                results.append(rec)
                done["n"] += 1
                if done["n"] % 25 == 0:
                    log(f"  {done['n']}/{len(todo)}…")
                    save_json(OUTPUT_FILE, results)

    # Fusion avec l'existant : les vidéos hors échantillon (--ids, --limit)
    # sont conservées au lieu d'être écrasées.
    merged = {r["video_id"]: r for r in existing.values()}
    merged.update({r["video_id"]: r for r in results})
    out = list(merged.values())
    save_json(OUTPUT_FILE, out)

    # Export slim pour le dashboard : dict keyé par video_id.
    slim = {}
    for r in out:
        cc = r.get("comment_climate", {})
        slim[r["video_id"]] = {
            "climat": cc.get("climat_dominant"),
            "sceptique_pct": cc.get("part_sceptique_pct"),
            "hostile_pct": cc.get("part_hostile_ecologie_pct"),
            "virulence": cc.get("virulence"),
            "n_comments": r.get("n_comments", 0),
            "status": r.get("comments_status"),
        }
    save_json(DASHBOARD_FILE, slim)

    log("-" * 70)
    ok = sum(1 for r in out if r["comments_status"] == "ok")
    log(f"Terminé : {len(out)} vidéos, {ok} avec commentaires analysés.")
    log(f"Sorties : {OUTPUT_FILE} + {DASHBOARD_FILE}")


if __name__ == "__main__":
    main()
