#!/usr/bin/env python3
"""
language.py — annote chaque vidéo classée avec sa langue détectée.

Le corpus contient un reliquat de vidéos non francophones (relevanceLanguage=fr
n'est qu'une suggestion côté YouTube). On détecte la langue à partir du titre +
description + début de transcript (via langdetect), et on écrit un champ `lang`.

aggregate.py exclut ensuite les vidéos clairement non-FR.
Gratuit (aucun appel LLM), idempotent.

Sortie : réécrit data/videos_classified.json avec le champ `lang`.
"""

from common import data_path, load_json, log, save_json, truncate_words

FILE = data_path("videos_classified.json")


def detect(text: str) -> str:
    """Détecte la langue d'un texte. Retourne un code ISO (fr, en, …) ou 'unknown'."""
    text = (text or "").strip()
    if len(text) < 15:  # trop court pour une détection fiable
        return "unknown"
    try:
        from langdetect import detect as _detect, DetectorFactory
        DetectorFactory.seed = 0  # rend la détection déterministe
        return _detect(text)
    except Exception:  # noqa: BLE001
        return "unknown"


def main():
    videos = load_json(FILE, default=None)
    if videos is None:
        log(f"ERREUR : {FILE} introuvable.")
        return

    from collections import Counter
    stats = Counter()
    for v in videos:
        # On combine titre + description + un bout de transcript pour fiabiliser.
        parts = [v.get("title", ""), truncate_words(v.get("description", ""), 60)]
        if v.get("transcript_status") == "ok":
            parts.append(truncate_words(v.get("transcript", ""), 60))
        v["lang"] = detect(" ".join(p for p in parts if p))
        stats[v["lang"]] += 1

    save_json(FILE, videos)
    log("Langues détectées : " + ", ".join(f"{k}={n}" for k, n in stats.most_common(8)))
    non_fr = sum(n for k, n in stats.items() if k not in ("fr", "unknown"))
    log(f"→ {non_fr} vidéos non-FR seront exclues des agrégats (fr + indéterminé conservés).")


if __name__ == "__main__":
    main()
