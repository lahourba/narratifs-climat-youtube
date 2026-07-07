#!/usr/bin/env python3
"""
crawl_channels.py — élargit le corpus par CRAWL DES CHAÎNES (100× moins cher en
quota que la recherche).

Pour chaque chaîne déjà repérée (+ une liste de chaînes à cibler), on aspire son
catalogue d'uploads via playlistItems.list, on filtre les vidéos liées au climat
par mots-clés, et on fusionne dans data/videos_raw.json.

- Priorise les chaînes de l'écosystème sceptique / opposition (là où le corpus est
  le plus mince), puis les chaînes les plus présentes.
- Reprenable sur plusieurs jours : l'état (chaînes déjà crawlées) est sauvegardé ;
  le script s'arrête proprement à l'épuisement du quota et reprend au run suivant.

Coûts quota : channels.list = 1 u / 50 chaînes · playlistItems.list = 1 u / 50 vidéos
· videos.list = 1 u / 50 vidéos.

Usage :
    python crawl_channels.py                       # crawl (reprend où il s'était arrêté)
    python crawl_channels.py --max-videos 500      # profondeur par chaîne
    python crawl_channels.py --reset               # repart de zéro (oublie l'état)

Pré-requis : YOUTUBE_API_KEY.
"""

import argparse
import os
import sys
import time

from collect import (COST_VIDEOS, QuotaExceeded, QuotaTracker, SLEEP_BETWEEN_CALLS,
                     _api_get, fetch_video_details, normalize_video)
from common import data_path, ensure_data_dir, load_json, log, now_iso, save_json

RAW_FILE = data_path("videos_raw.json")
STATE_FILE = data_path("crawl_state.json")

# Coût quota d'un appel channels.list / playlistItems.list.
COST_LIGHT = 1

# --------------------------------------------------------------------------- #
# Filtre climat : on ne garde que les vidéos dont le titre/description évoque le
# sujet (évite d'inonder le corpus de hors-sujet en crawlant tout un catalogue).
# --------------------------------------------------------------------------- #
CLIMATE_KEYWORDS = [
    "climat", "climatique", "réchauffement", "rechauffement", "giec", "carbone",
    "co2", "écolog", "ecolog", "réchauffiste", "climatoscept", "canicule",
    "effet de serre", "gaz à effet", "biodiversité", "fossile", "éolien", "eolien",
    "panneau solaire", "renouvelable", "transition énerg", "transition energ",
    "décarbon", "decarbon", "sobriété", "greenwashing", "collapso", "effondrement",
    "giec", "cop30", "cop29", "cop28", "zfe", "écologie punitive", "dérèglement",
    "banquise", "fonte des glaces", "montée des eaux", "empreinte carbone",
]

# Chaînes à cibler explicitement, résolues via recherche de chaîne (search.list,
# 100 unités/quête). Utile pour ajouter la sphère sceptique/complotiste absente
# du corpus initial. Ces chaînes sont crawlées EN PRIORITÉ.
SEED_CHANNEL_QUERIES: list = [
    "Association des climato-réalistes",
    "Benoît Rittaud",
    "François Gervais climat",
    "Géopolitique Profonde",
    "Citizen Light",
    "Alcaline climato-réaliste",
    "Idriss Aberkane",
]

# (Optionnel) chaînes par @handle, résolues à 1 unité/quête si tu en connais.
SEED_HANDLES: list = []


def load_state() -> dict:
    return load_json(STATE_FILE, default={"crawled_channels": []}) or {"crawled_channels": []}


def save_state(state: dict) -> None:
    save_json(STATE_FILE, state)


def is_climate(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(kw in text for kw in CLIMATE_KEYWORDS)


def resolve_handles(handles, api_key, quota) -> list:
    """Résout des @handles YouTube en channel_id."""
    ids = []
    for h in handles:
        handle = h.lstrip("@")
        try:
            data = _api_get("channels", {"part": "id", "forHandle": handle}, api_key)
            quota.add(COST_LIGHT)
            items = data.get("items", [])
            if items:
                ids.append(items[0]["id"])
                log(f"  @{handle} → {items[0]['id']}")
            else:
                log(f"  @{handle} : introuvable")
        except QuotaExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"  @{handle} : erreur ({e})")
        time.sleep(SLEEP_BETWEEN_CALLS)
    return ids


def resolve_queries(queries, api_key, quota) -> list:
    """Résout des noms de chaîne en channel_id via search.list (100 unités/quête)."""
    ids = []
    for q in queries:
        try:
            data = _api_get("search", {"part": "snippet", "type": "channel",
                                       "q": q, "maxResults": 1}, api_key)
            quota.add(100)
            items = data.get("items", [])
            if items:
                cid = items[0]["id"]["channelId"]
                title = items[0]["snippet"].get("channelTitle") or items[0]["snippet"].get("title", "")
                ids.append(cid)
                log(f"  « {q} » → {cid} ({title})")
            else:
                log(f"  « {q} » : introuvable")
        except QuotaExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"  « {q} » : erreur ({e})")
        time.sleep(SLEEP_BETWEEN_CALLS)
    return ids


def get_uploads_playlists(channel_ids, api_key, quota) -> dict:
    """Retourne {channel_id: uploads_playlist_id} pour un lot de chaînes."""
    out = {}
    for i in range(0, len(channel_ids), 50):
        chunk = [c for c in channel_ids[i:i + 50] if c]
        if not chunk:
            continue
        data = _api_get("channels", {"part": "contentDetails", "id": ",".join(chunk)}, api_key)
        quota.add(COST_LIGHT)
        for item in data.get("items", []):
            try:
                out[item["id"]] = item["contentDetails"]["relatedPlaylists"]["uploads"]
            except (KeyError, TypeError):
                continue
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out


def crawl_uploads(playlist_id, api_key, quota, max_videos) -> list:
    """Parcourt les uploads d'une chaîne, retourne les vidéos climat (id, titre…)."""
    videos = []
    scanned = 0
    page_token = None
    while scanned < max_videos:
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id,
                  "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        try:
            data = _api_get("playlistItems", params, api_key)
        except Exception:  # noqa: BLE001 — playlist privée/supprimée : on passe
            break
        quota.add(COST_LIGHT)
        for item in data.get("items", []):
            scanned += 1
            sn = item.get("snippet", {})
            vid = item.get("contentDetails", {}).get("videoId")
            if vid and is_climate(sn.get("title", ""), sn.get("description", "")):
                videos.append(vid)
        page_token = data.get("nextPageToken")
        time.sleep(SLEEP_BETWEEN_CALLS)
        if not page_token:
            break
    return videos


def priority_order(existing_videos, all_channel_ids) -> list:
    """
    Ordonne les chaînes : d'abord l'écosystème sceptique/opposition (corpus mince),
    puis les chaînes les plus présentes, puis le reste.
    """
    classified = load_json(data_path("videos_classified.json"), default=[]) or []
    skeptic = set()
    for v in classified:
        c = v.get("classification")
        if isinstance(c, dict) and c.get("narratif_principal") in (
                "SCEPTICISME_MINIMISATION", "OPPOSITION_ECOLOGIE"):
            if v.get("channel_id"):
                skeptic.add(v["channel_id"])

    # Nombre de vidéos par chaîne dans le corpus (proxy de pertinence).
    from collections import Counter
    counts = Counter(v.get("channel_id") for v in existing_videos if v.get("channel_id"))

    def key(cid):
        return (0 if cid in skeptic else 1, -counts.get(cid, 0))

    return sorted([c for c in all_channel_ids if c], key=key)


def main():
    parser = argparse.ArgumentParser(description="Crawl du corpus par chaîne.")
    parser.add_argument("--max-videos", type=int, default=400,
                        help="Vidéos scannées max par chaîne (défaut 400).")
    parser.add_argument("--max-channels", type=int, default=None,
                        help="Limite le nombre de chaînes traitées ce run.")
    parser.add_argument("--reset", action="store_true", help="Oublie l'état de crawl.")
    args = parser.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log("ERREUR : YOUTUBE_API_KEY absente.")
        sys.exit(1)

    ensure_data_dir()
    existing = load_json(RAW_FILE, default=[]) or []
    by_id = {v["video_id"]: v for v in existing}
    log(f"{len(by_id)} vidéos déjà dans le corpus.")

    state = {"crawled_channels": []} if args.reset else load_state()
    crawled = set(state.get("crawled_channels", []))

    quota = QuotaTracker()

    # Chaînes ciblées (seeds) résolues d'abord — crawlées EN PRIORITÉ.
    # Mises en cache dans l'état pour ne pas re-dépenser ~700 unités à chaque run.
    seed_ids = state.get("seed_ids", [])
    if not seed_ids:
        try:
            if SEED_CHANNEL_QUERIES:
                log(f"Résolution de {len(SEED_CHANNEL_QUERIES)} chaîne(s) ciblée(s)…")
                seed_ids += resolve_queries(SEED_CHANNEL_QUERIES, api_key, quota)
            if SEED_HANDLES:
                seed_ids += resolve_handles(SEED_HANDLES, api_key, quota)
            state["seed_ids"] = seed_ids
            save_state(state)
        except QuotaExceeded:
            log("Quota épuisé pendant la résolution des chaînes ciblées.")

    corpus_channels = {v.get("channel_id") for v in existing if v.get("channel_id")}
    # Ordre : seeds d'abord, puis priorité sceptique du corpus, puis le reste.
    ordered = [c for c in seed_ids if c] + priority_order(existing, list(corpus_channels))
    seen, todo = set(), []
    for c in ordered:
        if c and c not in seen and c not in crawled:
            seen.add(c)
            todo.append(c)
    if args.max_channels:
        todo = todo[:args.max_channels]
    log(f"{len(todo)} chaîne(s) à crawler ({len(seed_ids)} ciblées, {len(crawled)} déjà faites).")

    # --- Boucle avec enregistrement INCRÉMENTAL (robuste à l'épuisement du quota) --
    # On tamponne les vidéos ; tous les FLUSH_EVERY, on détaille + sauvegarde, PUIS
    # on marque les chaînes concernées « faites ». Ainsi rien n'est perdu si le
    # quota meurt : les chaînes non flushées seront simplement retentées.
    FLUSH_EVERY = 200
    pending_ids, pending_channels = [], []
    added = {"n": 0}

    def flush():
        if pending_ids:
            details = fetch_video_details(list(dict.fromkeys(pending_ids)), api_key, quota)
            for vid, item in details.items():
                try:
                    v = normalize_video(item, "channel_crawl")
                    v["source"] = "channel_crawl"
                except Exception:  # noqa: BLE001
                    continue
                if vid not in by_id:
                    added["n"] += 1
                by_id[vid] = v
            save_json(RAW_FILE, list(by_id.values()))
        crawled.update(pending_channels)
        state["crawled_channels"] = sorted(crawled)
        state["last_run"] = now_iso()
        save_state(state)
        pending_ids.clear()
        pending_channels.clear()

    channels_done = 0
    try:
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            uploads = get_uploads_playlists(batch, api_key, quota)
            for cid in batch:
                pl = uploads.get(cid)
                if pl:
                    vids = crawl_uploads(pl, api_key, quota, args.max_videos)
                    pending_ids.extend(v for v in vids if v not in by_id)
                pending_channels.append(cid)
                channels_done += 1
                if len(pending_ids) >= FLUSH_EVERY:
                    flush()
                if channels_done % 25 == 0:
                    log(f"  {channels_done}/{len(todo)} chaînes · +{added['n']} vidéos · quota {quota.units}")
    except QuotaExceeded:
        log("Quota YouTube épuisé — arrêt propre, reprise demain.")

    try:
        flush()  # flush final
    except QuotaExceeded:
        log("Quota épuisé au flush final : les dernières chaînes seront retentées demain.")

    log("-" * 60)
    log(f"Quota consommé ce run : {quota.units} unités.")
    log(f"{added['n']} nouvelles vidéos ajoutées → {len(by_id)} au total dans {os.path.basename(RAW_FILE)}.")
    log(f"{len(crawled)} chaînes crawlées au total. Relance le script pour continuer.")


if __name__ == "__main__":
    main()
