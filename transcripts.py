#!/usr/bin/env python3
"""
transcripts.py — Étape 2 du pipeline.

Lit data/videos_raw.json et récupère le transcript FR de chaque vidéo via
youtube-transcript-api (hors quota YouTube Data API).

- Gère proprement les vidéos sans transcript (transcript=null, ne crashe pas).
- Tronque chaque transcript aux ~3000 premiers mots.
- Pacing lent + jitter pour éviter le blocage d'IP par YouTube.
- Backoff exponentiel sur blocage (IpBlocked / TooManyRequests) : on attend que
  l'IP soit de nouveau acceptée puis on retente la MÊME vidéo.
- Reprise intelligente : on ne re-saute que les statuts définitifs (ok, disabled,
  no_transcript). Les blocages/erreurs transitoires sont retentés au prochain run.
- Support proxy optionnel (recommandé pour les gros corpus) via variables d'env.

Sortie : data/videos_with_transcripts.json

Usage :
    python transcripts.py
    python transcripts.py --delay 3 --limit 50
    python transcripts.py --force        # re-télécharge tout
"""

import argparse
import os
import random
import time

from common import (data_path, ensure_data_dir, load_json, log, now_iso,
                    save_json, truncate_words)

INPUT_FILE = data_path("videos_raw.json")
OUTPUT_FILE = data_path("videos_with_transcripts.json")

# Langues FR à tenter, dans l'ordre de préférence.
LANGUAGES = ["fr", "fr-FR", "fr-CA"]

# Troncature : ~3000 premiers mots.
MAX_WORDS = 3000

# Délai de base entre deux requêtes (secondes) + jitter aléatoire ajouté par-dessus.
# Un pacing trop rapide déclenche le blocage d'IP de YouTube.
DEFAULT_DELAY = 2.0
JITTER_MAX = 2.0

# Backoff sur blocage : on attend INITIAL puis on double à chaque fois, plafonné.
BLOCK_BACKOFF_INITIAL = 20
BLOCK_BACKOFF_CAP = 180
MAX_BLOCK_RETRIES = 6  # au-delà, on abandonne la vidéo (statut rate_limited, retentée plus tard)

# Erreurs de proxy/connexion (nœud de sortie mort ou lent) : on retente VITE, car
# un proxy rotatif fournit une nouvelle IP de sortie au prochain essai.
MAX_PROXY_RETRIES = 4
PROXY_RETRY_SLEEP = 2

# Timeout dur (connect, read) en secondes : sans lui, un nœud proxy mort fait
# « hanger » la requête ~25 s avant d'échouer. Avec, l'échec est rapide et le
# retry obtient une nouvelle IP de sortie.
REQUEST_TIMEOUT = (10, 15)

# Statuts considérés comme DÉFINITIFS : inutile de les retenter.
DONE_STATUSES = {"ok", "disabled", "no_transcript"}


def _proxies_from_env():
    """
    Retourne le dict de proxies requests ({'http':..., 'https':...}) à partir des
    variables d'env, ou None. On extrait l'URL Webshare via to_requests_dict() pour
    pouvoir l'attacher à NOTRE session (avec timeout), plutôt que de laisser la lib
    créer une session sans timeout.
    """
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    pwd = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    http = os.environ.get("YT_HTTP_PROXY")
    https = os.environ.get("YT_HTTPS_PROXY")
    if user and pwd:
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            # Ciblage pays optionnel (ex. WEBSHARE_LOCATIONS=fr ou fr,be,ch).
            # ⚠️ nécessite un plan Webshare avec géo-targeting ; sinon laisser vide
            # (rotation mondiale). Contourne les blocages « pas dispo dans ton pays ».
            locs = [c.strip() for c in os.environ.get("WEBSHARE_LOCATIONS", "").split(",") if c.strip()]
            proxies = WebshareProxyConfig(
                proxy_username=user, proxy_password=pwd,
                filter_ip_locations=locs or None).to_requests_dict()
            suffix = f" — pays : {','.join(locs)}" if locs else ""
            log(f"Proxy Webshare activé (timeout + rotation d'IP forcée){suffix}.")
            return proxies
        except ImportError:
            log("Avertissement : version sans support Webshare, proxy ignoré.")
    if http or https:
        log("Proxy HTTP générique activé (avec timeout).")
        return {"http": http or https, "https": https or http}
    return None


def _make_http_client():
    """
    Session requests avec timeout dur sur CHAQUE requête (sinon un nœud proxy mort
    fait hanger ~25 s). Avec proxy : 'Connection: close' force une nouvelle connexion
    — donc une nouvelle IP de sortie rotative — à chaque tentative.
    """
    import requests

    proxies = _proxies_from_env()

    class _TimeoutSession(requests.Session):
        def request(self, *args, **kwargs):
            if not kwargs.get("timeout"):
                kwargs["timeout"] = REQUEST_TIMEOUT
            return super().request(*args, **kwargs)

    session = _TimeoutSession()
    if proxies:
        session.proxies.update(proxies)
        session.headers["Connection"] = "close"
    return session


def _get_api():
    """
    Retourne une fonction de fetch unifiée, compatible avec les versions récentes
    (>=1.0, API par instance) et anciennes (<1.0, API statique).
    On injecte notre propre session HTTP (timeout + proxy) via http_client.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    http_client = _make_http_client()

    # API moderne (>= 1.0) : instance avec .fetch() et http_client personnalisé.
    try:
        instance = YouTubeTranscriptApi(http_client=http_client)
    except TypeError:
        # Constructeur sans argument http_client (très ancienne version)
        instance = YouTubeTranscriptApi()

    if hasattr(instance, "fetch"):
        def fetch(video_id):
            fetched = instance.fetch(video_id, languages=LANGUAGES)
            return " ".join(snippet.text for snippet in fetched)
        return fetch

    # API historique (méthodes statiques)
    def fetch(video_id):
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=LANGUAGES)
        return " ".join(seg.get("text", "") for seg in segments)
    return fetch


def _classify_error(exc) -> str:
    """Mappe une exception vers un statut. 'block' et 'proxy' sont transitoires (à retenter)."""
    name = type(exc).__name__
    if "TranscriptsDisabled" in name:
        return "disabled"
    if "NoTranscriptFound" in name or "NotTranslatable" in name:
        return "no_transcript"
    if "VideoUnavailable" in name or "VideoUnplayable" in name:
        return "unavailable"
    if any(k in name for k in ("Blocked", "TooManyRequests", "IpBlocked")):
        return "block"
    # Erreurs proxy/réseau : nœud de sortie défaillant → retenter avec une IP fraîche.
    if any(k in name for k in ("Proxy", "RetryError", "ChunkedEncoding", "ConnectionError",
                               "Timeout", "MaxRetry", "SSLError", "RequestFailed",
                               "RequestException")):
        return "proxy"
    return f"error:{name}"


def fetch_one(fetch_fn, video_id: str):
    """
    Récupère le transcript d'une vidéo, avec backoff sur blocage d'IP.
    Retourne (texte_tronqué|None, status). Ne lève jamais.
    """
    backoff = BLOCK_BACKOFF_INITIAL
    block_tries = 0
    proxy_tries = 0
    while True:
        try:
            text = fetch_fn(video_id)
            if not text or not text.strip():
                return None, "no_transcript"
            return truncate_words(text.strip(), MAX_WORDS), "ok"
        except Exception as e:  # noqa: BLE001 — on ne crashe jamais sur une vidéo
            status = _classify_error(e)
            if status == "block":
                # Blocage YouTube : backoff exponentiel (long).
                if block_tries < MAX_BLOCK_RETRIES:
                    block_tries += 1
                    log(f"  Blocage YouTube (IP). Pause {backoff}s puis reprise…")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, BLOCK_BACKOFF_CAP)
                    continue
                return None, "rate_limited"
            if status == "proxy":
                # Nœud proxy défaillant : retry rapide pour obtenir une IP fraîche.
                if proxy_tries < MAX_PROXY_RETRIES:
                    proxy_tries += 1
                    time.sleep(PROXY_RETRY_SLEEP)
                    continue
                return None, "proxy_failed"
            return None, status


def main():
    parser = argparse.ArgumentParser(description="Récupération des transcripts FR.")
    parser.add_argument("--force", action="store_true",
                        help="Re-télécharge même les transcripts déjà récupérés.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"Délai de base entre requêtes en s (défaut {DEFAULT_DELAY}).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Ne récupère que N vidéos (les N premières, ou les N plus "
                             "vues avec --by-views).")
    parser.add_argument("--by-views", action="store_true",
                        help="Cible les vidéos les plus vues (à combiner avec --limit). "
                             "Économise la bande passante proxy sur un gros corpus.")
    args = parser.parse_args()

    ensure_data_dir()

    videos = load_json(INPUT_FILE, default=None)
    if videos is None:
        log(f"ERREUR : {INPUT_FILE} introuvable. Lance d'abord collect.py.")
        return

    # Réutilisation de l'existant pour la reprise.
    existing = {v["video_id"]: v for v in (load_json(OUTPUT_FILE, default=[]) or [])}

    # Ensemble cible si --limit : les N premières, ou les N plus vues (--by-views).
    # On ne récupère que cette cible ; le reste est conservé tel quel.
    target_ids = None
    if args.limit is not None:
        pool = videos
        if args.by_views:
            pool = sorted(videos, key=lambda v: v.get("view_count") or 0, reverse=True)
        target_ids = {v["video_id"] for v in pool[:args.limit]}
        how = "les plus vues" if args.by_views else "les premières"
        log(f"Cible : {len(target_ids)} vidéos ({how}).")

    try:
        fetch_fn = _get_api()
    except ImportError as e:
        import sys
        log(f"ERREUR : import de youtube-transcript-api impossible ({e}).")
        log(f"Python utilisé : {sys.executable}")
        log("Lance bien le python du venv : .venv/bin/python transcripts.py")
        return

    out = []
    stats = {"ok": 0, "skipped": 0, "no_transcript": 0, "disabled": 0,
             "unavailable": 0, "rate_limited": 0, "error": 0}
    processed = 0

    for i, video in enumerate(videos, start=1):
        vid = video["video_id"]
        prev = existing.get(vid)

        # Reprise : on saute UNIQUEMENT les statuts définitifs (sauf --force).
        if prev and not args.force and prev.get("transcript_status") in DONE_STATUSES:
            out.append({**video, **{k: prev[k] for k in
                        ("transcript", "transcript_status", "transcript_fetched_at")
                        if k in prev}})
            stats["skipped"] += 1
            continue

        # Hors cible : on conserve la vidéo telle quelle (non récupérée).
        if target_ids is not None and vid not in target_ids:
            out.append(prev or video)
            continue

        text, status = fetch_one(fetch_fn, vid)
        processed += 1
        video = dict(video)
        video["transcript"] = text
        video["transcript_status"] = status
        video["transcript_fetched_at"] = now_iso()
        out.append(video)

        if status == "ok":
            stats["ok"] += 1
        elif status.startswith("error"):
            stats["error"] += 1
        elif status in stats:
            stats[status] += 1
        else:
            stats["error"] += 1

        if processed % 5 == 0:
            log(f"  {i}/{len(videos)} (traités={processed}, ok={stats['ok']}, "
                f"sans={stats['no_transcript']}, bloqués={stats['rate_limited']})")
            save_json(OUTPUT_FILE, out)  # sauvegarde de progression

        # Pacing lent + jitter pour ne pas se faire bloquer.
        time.sleep(args.delay + random.uniform(0, JITTER_MAX))

    save_json(OUTPUT_FILE, out)
    log("-" * 60)
    log(f"Terminé : {len(out)} vidéos écrites dans {OUTPUT_FILE}.")
    log(f"OK : {stats['ok']} | réutilisés : {stats['skipped']} | absents : "
        f"{stats['no_transcript']} | désactivés : {stats['disabled']} | "
        f"bloqués (à retenter) : {stats['rate_limited']} | erreurs : {stats['error']}")
    if stats["rate_limited"] > 0:
        log("Des vidéos restent bloquées : relance le script plus tard (reprise auto), "
            "ou configure un proxy (voir .env.example).")


if __name__ == "__main__":
    main()
