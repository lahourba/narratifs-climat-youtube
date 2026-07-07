#!/usr/bin/env python3
"""
aggregate.py — Étape 4 du pipeline.

Calcule les agrégats PONDÉRÉS PAR LES VUES à partir de videos_classified.json :
  - part de chaque narratif en % des vues totales ET en % du nombre de vidéos ;
  - évolution par trimestre (vues par narratif) ;
  - top chaînes par narratif ;
  - tonalité émotionnelle croisée avec le narratif.

Sorties (consommées par le dashboard) :
  - dashboard/src/data/aggregates.json   (agrégats + métadonnées)
  - dashboard/src/data/videos.json       (détail vidéo-par-vidéo pour l'explorateur)

Idempotent : recalculé intégralement à chaque exécution.

Usage :
    python aggregate.py
"""

import os
from collections import defaultdict
from datetime import datetime, timezone

from common import data_path, load_json, log, now_iso, save_json
from taxonomy import NARRATIVE_KEYS, TONALITES

INPUT_FILE = data_path("videos_classified.json")

# Sorties dans le dashboard (créées si besoin).
DASHBOARD_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dashboard", "src", "data"
)
AGGREGATES_FILE = os.path.join(DASHBOARD_DATA_DIR, "aggregates.json")
VIDEOS_FILE = os.path.join(DASHBOARD_DATA_DIR, "videos.json")

# Nombre de chaînes retournées par narratif.
TOP_CHANNELS_N = 8

# Narratifs retirés du rapport. HORS_SUJET (climat = simple accroche) est exclu à
# la demande : il pollue l'analyse et nuit à la crédibilité du rapport. Les données
# source (videos_classified.json) sont conservées ; c'est un filtre d'agrégation.
EXCLUDED_NARRATIVES = {"HORS_SUJET"}
REPORT_KEYS = [k for k in NARRATIVE_KEYS if k not in EXCLUDED_NARRATIVES]

# Chaînes institutionnelles / annonceurs (audit 7/07) : ~21 % des vues du corpus
# viennent de chaînes d'institutions ou d'annonceurs (Enedis seul ≈ 10 %) dont la
# visibilité est très probablement achetée (campagnes pub YouTube). On ne les
# retire PAS du rapport : on les marque, et le dashboard offre un toggle
# d'exclusion analogue au toggle HORS_SUJET de la Cartographie.
INSTITUTIONAL_CHANNEL_IDS = {
    "UCMzqWRZDxw6yOgKjP7-VraQ",  # Enedis
    "UCe2_2k-_81Y4RNKBnlMjrLg",  # Ministères Écologie Territoires
    "UCEYjEYFApmoF217Ks1Tg4Sw",  # BANQUE DES TERRITOIRES
    "UCJBmrvimOZNMCKoYr2k5_Yw",  # AFD - Agence française de développement
    "UCIjo06T9erEvYBXVIDUCxTA",  # Hellio
}

# Seuil minimal d'échantillon pour publier un trimestre dans l'évolution du
# climat d'audience : en dessous, un trimestre à 1-2 vidéos affiche des extrêmes
# (0 % ou 100 % hostile) sans signification statistique.
AUDIENCE_MIN_VIDEOS = 5
AUDIENCE_MIN_VIEWS = 1_000_000


def quarter_of(published_at: str) -> str:
    """Retourne le trimestre 'YYYY-Qn' à partir d'une date ISO, ou None."""
    if not published_at or len(published_at) < 7:
        return None
    try:
        year = int(published_at[0:4])
        month = int(published_at[5:7])
    except ValueError:
        return None
    q = (month - 1) // 3 + 1
    return f"{year}-Q{q}"


def current_quarter() -> str:
    """Trimestre 'YYYY-Qn' en cours (UTC) — par définition incomplet."""
    now = datetime.now(timezone.utc)
    return f"{now.year}-Q{(now.month - 1) // 3 + 1}"


def quarter_range(first: str, last: str) -> list:
    """Liste CONTIGUË de trimestres 'YYYY-Qn' de first à last inclus."""
    y, q = int(first[:4]), int(first[-1])
    ly, lq = int(last[:4]), int(last[-1])
    out = []
    while (y, q) <= (ly, lq):
        out.append(f"{y}-Q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def is_classified(video: dict) -> bool:
    """Vrai si la vidéo a une classification exploitable."""
    c = video.get("classification")
    return isinstance(c, dict) and "classification_error" not in c and \
        c.get("narratif_principal") in NARRATIVE_KEYS


def safe_views(video: dict) -> int:
    """Vues, en traitant None/absent comme 0."""
    v = video.get("view_count")
    return v if isinstance(v, int) and v >= 0 else 0


def main():
    videos = load_json(INPUT_FILE, default=None)
    if videos is None:
        log(f"ERREUR : {INPUT_FILE} introuvable. Lance d'abord classify.py.")
        return

    classified_all = [v for v in videos if is_classified(v)]
    # Filtre langue STRICT : Janco s'adresse à une audience française → on ne garde
    # QUE le français avéré (lang == 'fr'). Tout autre code, y compris 'unknown'/None,
    # est écarté. Nécessite un language.py à jour sur le corpus courant.
    fr = [v for v in classified_all if v.get("lang") == "fr"]
    excluded_lang = len(classified_all) - len(fr)
    # Exclusion du hors-sujet (voir EXCLUDED_NARRATIVES) : ces vidéos ne doivent
    # apparaître nulle part dans le rapport.
    classified = [v for v in fr
                  if v["classification"]["narratif_principal"] not in EXCLUDED_NARRATIVES]
    excluded_hs = len(fr) - len(classified)
    log(f"{len(classified)}/{len(videos)} vidéos retenues "
        f"({excluded_lang} non-FR + {excluded_hs} hors-sujet exclues).")
    if not classified:
        log("Aucune vidéo classée. Rien à agréger.")
        return

    total_views = sum(safe_views(v) for v in classified)
    total_videos = len(classified)

    # --- 1) Répartition par narratif (vues + nombre de vidéos) --------------- #
    # inst_* = part venant des chaînes institutionnelles/annonceurs, pour que le
    # dashboard puisse les soustraire (toggle d'exclusion) sans re-agréger.
    n_views = defaultdict(int)
    n_count = defaultdict(int)
    inst_views = defaultdict(int)
    inst_count = defaultdict(int)
    for v in classified:
        key = v["classification"]["narratif_principal"]
        n_views[key] += safe_views(v)
        n_count[key] += 1
        if v.get("channel_id") in INSTITUTIONAL_CHANNEL_IDS:
            inst_views[key] += safe_views(v)
            inst_count[key] += 1

    narratives = {}
    for key in REPORT_KEYS:
        narratives[key] = {
            "views": n_views[key],
            "videos": n_count[key],
            "views_pct": round(100 * n_views[key] / total_views, 2) if total_views else 0,
            "videos_pct": round(100 * n_count[key] / total_videos, 2) if total_videos else 0,
            "inst_views": inst_views[key],
            "inst_videos": inst_count[key],
        }

    # --- 2) Évolution par trimestre (vues par narratif) ---------------------- #
    # quarter -> narratif -> vues
    quarter_map = defaultdict(lambda: defaultdict(int))
    for v in classified:
        q = quarter_of(v.get("published_at", ""))
        if not q:
            continue
        key = v["classification"]["narratif_principal"]
        quarter_map[q][key] += safe_views(v)

    # Axe temporel CONTIGU : les trimestres sans vidéo sont émis à 0, sinon le
    # graphe (axe catégoriel) rend p.ex. 2013-Q3 et 2015-Q2 adjacents.
    cur_q = current_quarter()
    evolution = []
    if quarter_map:
        for q in quarter_range(min(quarter_map), max(quarter_map)):
            row = {"quarter": q}
            for key in REPORT_KEYS:
                row[key] = quarter_map[q][key]
            if q == cur_q:
                # Trimestre en cours donc incomplet : le dashboard l'écarte de
                # la courbe (sinon falaise artificielle en fin de série).
                row["incomplete"] = True
            evolution.append(row)

    # --- 3) Top chaînes par narratif (par vues) ------------------------------ #
    # narratif -> channel -> {views, videos}
    chan_map = defaultdict(lambda: defaultdict(lambda: {"views": 0, "videos": 0,
                                                        "channel_id": ""}))
    for v in classified:
        key = v["classification"]["narratif_principal"]
        chan = v.get("channel_title") or "(inconnu)"
        chan_map[key][chan]["views"] += safe_views(v)
        chan_map[key][chan]["videos"] += 1
        chan_map[key][chan]["channel_id"] = v.get("channel_id", "")

    top_channels = {}
    for key in REPORT_KEYS:
        ranked = sorted(
            ({"channel": name, **info,
              "institutional": info["channel_id"] in INSTITUTIONAL_CHANNEL_IDS}
             for name, info in chan_map[key].items()),
            key=lambda c: c["views"], reverse=True,
        )
        top_channels[key] = ranked[:TOP_CHANNELS_N]

    # --- 4) Tonalité croisée avec narratif (nombre de vidéos) ---------------- #
    # narratif -> tonalite -> count
    tone_map = defaultdict(lambda: defaultdict(int))
    for v in classified:
        key = v["classification"]["narratif_principal"]
        tone = v["classification"].get("tonalite", "neutre")
        tone_map[key][tone] += 1

    tonalite_by_narrative = []
    for key in REPORT_KEYS:
        row = {"narratif": key}
        for tone in TONALITES:
            row[tone] = tone_map[key][tone]
        tonalite_by_narrative.append(row)

    # --- 5) Évolution du CLIMAT D'AUDIENCE par trimestre --------------------- #
    # (part des vues dont la section commentaires est hostile). Nécessite
    # dashboard/src/data/comments.json (produit par comments.py).
    HOSTILE = {"scepticisme_deni", "hostilite_ecologie", "complotisme"}
    comments = load_json(os.path.join(DASHBOARD_DATA_DIR, "comments.json"), default={}) or {}
    aud_total = defaultdict(int)   # quarter -> vues analysées
    aud_hostile = defaultdict(int)  # quarter -> vues hostiles
    aud_videos = defaultdict(int)  # quarter -> nb de vidéos analysées
    for v in classified:
        cc = comments.get(v["video_id"])
        if not cc or cc.get("status") != "ok" or not cc.get("climat"):
            continue
        q = quarter_of(v.get("published_at", ""))
        if not q:
            continue
        aud_total[q] += safe_views(v)
        aud_videos[q] += 1
        if cc["climat"] in HOSTILE:
            aud_hostile[q] += safe_views(v)

    audience_evolution = []
    skipped_quarters = []
    for q in sorted(aud_total.keys()):
        tot = aud_total[q]
        # Seuil minimal d'échantillon (voir AUDIENCE_MIN_*) : on ne publie un
        # trimestre que s'il est assez fourni pour que le % ait un sens.
        if aud_videos[q] < AUDIENCE_MIN_VIDEOS and tot < AUDIENCE_MIN_VIEWS:
            skipped_quarters.append(q)
            continue
        audience_evolution.append({
            "quarter": q,
            "analyzed_videos": aud_videos[q],
            "analyzed_views": tot,
            "hostile_views": aud_hostile[q],
            "hostile_pct": round(100 * aud_hostile[q] / tot, 1) if tot else 0,
        })
    if skipped_quarters:
        log(f"Climat d'audience : {len(skipped_quarters)} trimestre(s) sous le seuil "
            f"(<{AUDIENCE_MIN_VIDEOS} vidéos et <{AUDIENCE_MIN_VIEWS:,} vues) : "
            f"{', '.join(skipped_quarters)}")

    # --- Métadonnées --------------------------------------------------------- #
    dates = [v.get("published_at", "") for v in classified if v.get("published_at")]
    inst_total_views = sum(inst_views[k] for k in REPORT_KEYS)
    inst_total_videos = sum(inst_count[k] for k in REPORT_KEYS)
    meta = {
        "generated_at": now_iso(),
        "total_videos_collected": len(videos),
        "total_videos_classified": total_videos,
        "total_views": total_views,
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
        "current_quarter": cur_q,
        "narrative_keys": REPORT_KEYS,
        "tonalites": TONALITES,
        "institutional_channel_ids": sorted(INSTITUTIONAL_CHANNEL_IDS),
        "institutional_views": inst_total_views,
        "institutional_videos": inst_total_videos,
        "institutional_views_pct": (
            round(100 * inst_total_views / total_views, 1) if total_views else 0
        ),
    }

    aggregates = {
        "meta": meta,
        "narratives": narratives,
        "evolution": evolution,
        "top_channels": top_channels,
        "tonalite_by_narrative": tonalite_by_narrative,
        "audience_evolution": audience_evolution,
    }

    # --- Détail vidéo-par-vidéo pour l'explorateur --------------------------- #
    videos_out = []
    for v in classified:
        c = v["classification"]
        videos_out.append({
            "video_id": v["video_id"],
            "title": v.get("title", ""),
            "channel_title": v.get("channel_title", ""),
            "published_at": v.get("published_at", ""),
            "view_count": safe_views(v),
            "like_count": v.get("like_count"),
            "comment_count": v.get("comment_count"),
            "duration_seconds": v.get("duration_seconds", 0),
            "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            "narratif_principal": c.get("narratif_principal"),
            "narratif_secondaire": c.get("narratif_secondaire"),
            "confiance": c.get("confiance"),
            "tonalite": c.get("tonalite"),
            "presence_solutions": c.get("presence_solutions"),
            "registre": c.get("registre"),
            "justification": c.get("justification", ""),
            "has_transcript": v.get("transcript_status") == "ok",
            "is_institutional": v.get("channel_id") in INSTITUTIONAL_CHANNEL_IDS,
        })
    # Tri par défaut : vues décroissantes.
    videos_out.sort(key=lambda x: x["view_count"], reverse=True)

    os.makedirs(DASHBOARD_DATA_DIR, exist_ok=True)
    save_json(AGGREGATES_FILE, aggregates)
    save_json(VIDEOS_FILE, videos_out)

    log("-" * 60)
    log(f"Agrégats écrits : {AGGREGATES_FILE}")
    log(f"Détail vidéos écrit : {VIDEOS_FILE} ({len(videos_out)} vidéos)")
    log(f"Vues totales : {total_views:,} | Trimestres : {len(evolution)}")
    # Petit récapitulatif lisible.
    for key in REPORT_KEYS:
        n = narratives[key]
        log(f"  {key:<26} {n['views_pct']:>5.1f}% vues | {n['videos_pct']:>5.1f}% vidéos")


if __name__ == "__main__":
    main()
