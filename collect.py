#!/usr/bin/env python3
"""
collect.py — Étape 1 du pipeline.

Collecte des vidéos YouTube francophones sur le climat via plusieurs requêtes
de recherche (incluant volontairement des requêtes sceptiques pour ne pas
biaiser le corpus vers le consensus).

Pour chaque vidéo, on récupère les métadonnées et statistiques.
Sortie : data/videos_raw.json (dédupliqué par video_id).

Idempotent : relançable. Les vidéos déjà présentes dans videos_raw.json sont
conservées et fusionnées avec les nouvelles (les stats sont rafraîchies).

Pré-requis : variable d'environnement YOUTUBE_API_KEY.

Usage :
    python collect.py
    python collect.py --months 12 --max-pages 3
"""

import argparse
import os
import sys
import time

import requests

from common import data_path, ensure_data_dir, iso_duration_to_seconds, load_json, log, now_iso, save_json
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- #
# Configuration (modifiable en haut du fichier comme demandé)
# --------------------------------------------------------------------------- #

# Requêtes de recherche. On inclut des angles sceptiques ET de consensus pour
# obtenir un corpus représentatif de ce à quoi le public est réellement exposé.
SEARCH_QUERIES = [
    "changement climatique",
    "réchauffement climatique",
    "crise climatique",
    "transition écologique",
    "rapport GIEC",
    "arnaque climatique",
    "écologie punitive",
]

REGION_CODE = "FR"
RELEVANCE_LANGUAGE = "fr"

# Période par défaut : 24 derniers mois.
DEFAULT_MONTHS = 24

# --- Dé-biaisage temporel ---
# Une seule fenêtre publishedAfter=24 mois triée par 'relevance' surreprésente
# les événements récents (ex. canicule). On découpe plutôt la période en fenêtres
# successives, chacune interrogée également → représentation temporelle équilibrée.
DEFAULT_WINDOW_MONTHS = 4       # taille d'une fenêtre (24 mois / 4 = 6 fenêtres)
DEFAULT_PAGES_PER_WINDOW = 1    # pages par (requête, fenêtre, ordre) — 50 résultats/page
# Combiner plusieurs ordres réduit le biais de popularité de 'relevance' seul.
# 'date' apporte un échantillon chronologique moins lié à l'audience.
DEFAULT_ORDERS = ["relevance", "date"]

# Garde-fou : on prévient si l'estimation dépasse le quota quotidien YouTube.
DAILY_QUOTA = 10000

# Coûts quota YouTube Data API v3 (unités).
COST_SEARCH = 100   # search.list
COST_VIDEOS = 1     # videos.list (par appel de 50 ids max)

API_BASE = "https://www.googleapis.com/youtube/v3"
OUTPUT_FILE = data_path("videos_raw.json")

# Petite pause entre appels pour rester courtois avec l'API.
SLEEP_BETWEEN_CALLS = 0.1


class QuotaTracker:
    """Comptabilise le quota consommé pour le logger en fin de run."""

    def __init__(self):
        self.units = 0

    def add(self, n: int):
        self.units += n


def _published_after(months: int) -> str:
    """Retourne la date RFC 3339 correspondant à `months` mois avant maintenant."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_windows(total_months: int, window_months: int) -> list:
    """
    Découpe la période [maintenant - total_months ; maintenant] en fenêtres
    successives de `window_months`. Retourne une liste de (after_iso, before_iso),
    de la plus ancienne à la plus récente. Sert à échantillonner le corpus de
    façon temporellement équilibrée.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30 * total_months)
    step = timedelta(days=30 * window_months)
    windows = []
    cursor = start
    while cursor < now:
        nxt = min(cursor + step, now)
        windows.append((cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        cursor = nxt
    return windows


def _api_get(endpoint: str, params: dict, api_key: str) -> dict:
    """Appel GET vers l'API YouTube avec gestion d'erreurs et retries légers."""
    params = dict(params)
    params["key"] = api_key
    url = f"{API_BASE}/{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            log(f"  Erreur réseau ({e}). Nouvel essai dans 2s…")
            time.sleep(2)
            continue
        if resp.status_code == 200:
            return resp.json()
        # Quota dépassé : 403 avec reason quotaExceeded → on arrête proprement.
        if resp.status_code == 403:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            reason = ""
            try:
                reason = body["error"]["errors"][0]["reason"]
            except (KeyError, IndexError, TypeError):
                pass
            if reason in ("quotaExceeded", "dailyLimitExceeded"):
                raise QuotaExceeded(reason)
            log(f"  Erreur 403 ({reason or 'inconnue'}) : {resp.text[:200]}")
            raise RuntimeError(f"403 {reason}")
        if resp.status_code in (500, 503):
            log(f"  Erreur serveur {resp.status_code}. Nouvel essai dans 2s…")
            time.sleep(2)
            continue
        log(f"  Erreur HTTP {resp.status_code} : {resp.text[:200]}")
        raise RuntimeError(f"HTTP {resp.status_code}")
    raise RuntimeError(f"Échec après plusieurs tentatives sur {endpoint}")


class QuotaExceeded(Exception):
    """Levée quand le quota quotidien YouTube est épuisé."""


def search_video_ids(query: str, published_after: str, published_before: str,
                     order: str, max_pages: int, api_key: str,
                     quota: QuotaTracker) -> list:
    """Recherche les video_id pour une requête, une fenêtre temporelle et un ordre."""
    ids = []
    page_token = None
    for page in range(max_pages):
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 50,
            "regionCode": REGION_CODE,
            "relevanceLanguage": RELEVANCE_LANGUAGE,
            "publishedAfter": published_after,
            "publishedBefore": published_before,
            "order": order,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _api_get("search", params, api_key)
        quota.add(COST_SEARCH)
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = data.get("nextPageToken")
        time.sleep(SLEEP_BETWEEN_CALLS)
        if not page_token:
            break
    return ids


def fetch_video_details(video_ids: list, api_key: str, quota: QuotaTracker) -> dict:
    """Récupère snippet + statistics + contentDetails pour une liste d'ids."""
    details = {}
    # videos.list accepte jusqu'à 50 ids par appel.
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "maxResults": 50,
        }
        data = _api_get("videos", params, api_key)
        quota.add(COST_VIDEOS)
        for item in data.get("items", []):
            details[item["id"]] = item
        time.sleep(SLEEP_BETWEEN_CALLS)
    return details


def normalize_video(item: dict, matched_query: str) -> dict:
    """Transforme un item brut de l'API en notre schéma de stockage."""
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})

    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    duration = content.get("duration", "")
    return {
        "video_id": item["id"],
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "channel_id": snippet.get("channelId", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": to_int(stats.get("viewCount")),
        "like_count": to_int(stats.get("likeCount")),
        "comment_count": to_int(stats.get("commentCount")),
        "duration": duration,
        "duration_seconds": iso_duration_to_seconds(duration),
        "matched_queries": [matched_query],
        "collected_at": now_iso(),
    }


def main():
    parser = argparse.ArgumentParser(description="Collecte de vidéos YouTube climat (FR).")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                        help=f"Profondeur de la recherche en mois (défaut {DEFAULT_MONTHS}).")
    parser.add_argument("--window-months", type=int, default=DEFAULT_WINDOW_MONTHS,
                        help=f"Taille des fenêtres temporelles en mois (défaut {DEFAULT_WINDOW_MONTHS}).")
    parser.add_argument("--pages-per-window", type=int, default=DEFAULT_PAGES_PER_WINDOW,
                        help=f"Pages par (requête, fenêtre, ordre) (défaut {DEFAULT_PAGES_PER_WINDOW}).")
    parser.add_argument("--orders", nargs="+", default=DEFAULT_ORDERS,
                        help="Ordres de tri combinés : relevance date viewCount rating "
                             f"(défaut : {' '.join(DEFAULT_ORDERS)}).")
    args = parser.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log("ERREUR : variable d'environnement YOUTUBE_API_KEY absente.")
        sys.exit(1)

    ensure_data_dir()
    windows = generate_windows(args.months, args.window_months)
    log(f"Période : {args.months} mois, découpés en {len(windows)} fenêtres de "
        f"{args.window_months} mois.")
    log(f"{len(SEARCH_QUERIES)} requêtes × {len(windows)} fenêtres × "
        f"{len(args.orders)} ordre(s) ({', '.join(args.orders)}) × "
        f"{args.pages_per_window} page(s).")

    # Estimation du quota et garde-fou.
    est_calls = len(SEARCH_QUERIES) * len(windows) * len(args.orders) * args.pages_per_window
    est_units = est_calls * COST_SEARCH
    log(f"Estimation : ~{est_calls} appels search ≈ {est_units} unités "
        f"(quota quotidien YouTube = {DAILY_QUOTA}).")
    if est_units > DAILY_QUOTA:
        log("⚠ L'estimation dépasse le quota quotidien : réduis --orders, augmente "
            "--window-months, ou la collecte s'arrêtera proprement à l'épuisement.")

    quota = QuotaTracker()

    # Chargement de l'existant pour fusion idempotente (dédup par video_id).
    existing = load_json(OUTPUT_FILE, default=[]) or []
    by_id = {v["video_id"]: v for v in existing}
    log(f"{len(by_id)} vidéo(s) déjà présente(s) dans {os.path.basename(OUTPUT_FILE)}.")

    # 1) Récupération des ids candidats : chaque requête est interrogée sur CHAQUE
    #    fenêtre temporelle et CHAQUE ordre → corpus temporellement équilibré.
    id_to_query = {}
    try:
        for query in SEARCH_QUERIES:
            q_total = 0
            for (after, before) in windows:
                for order in args.orders:
                    ids = search_video_ids(query, after, before, order,
                                           args.pages_per_window, api_key, quota)
                    for vid in ids:
                        id_to_query.setdefault(vid, set()).add(query)
                    q_total += len(ids)
            log(f"« {query} » : {q_total} résultats bruts sur {len(windows)} fenêtres.")
    except QuotaExceeded as e:
        log(f"Quota YouTube épuisé ({e}). On poursuit avec ce qui a été collecté.")

    unique_ids = list(id_to_query.keys())
    log(f"{len(unique_ids)} vidéo(s) unique(s) trouvée(s) au total.")

    # 2) Récupération des détails (stats, durée) par lots de 50.
    new_count = 0
    try:
        details = fetch_video_details(unique_ids, api_key, quota)
    except QuotaExceeded as e:
        log(f"Quota épuisé pendant la récupération des détails ({e}).")
        details = {}

    for vid, item in details.items():
        queries = sorted(id_to_query.get(vid, set()))
        try:
            normalized = normalize_video(item, queries[0] if queries else "")
            normalized["matched_queries"] = queries
        except Exception as e:  # ne jamais crasher sur une vidéo isolée
            log(f"  Vidéo {vid} ignorée (normalisation impossible : {e}).")
            continue
        if vid in by_id:
            # Mise à jour : on rafraîchit les stats, on fusionne les requêtes.
            merged_queries = sorted(set(by_id[vid].get("matched_queries", [])) | set(queries))
            normalized["matched_queries"] = merged_queries
        else:
            new_count += 1
        by_id[vid] = normalized

    result = list(by_id.values())
    save_json(OUTPUT_FILE, result)

    log("-" * 60)
    log(f"Quota consommé : {quota.units} unités "
        f"(search={quota.units}/… ; budget quotidien YouTube par défaut = 10000).")
    log(f"{new_count} nouvelle(s) vidéo(s), {len(result)} au total dans {OUTPUT_FILE}.")
    if len(result) < 800:
        log("Note : moins de 800 vidéos. Augmente --max-pages ou ajoute des requêtes.")


if __name__ == "__main__":
    main()
