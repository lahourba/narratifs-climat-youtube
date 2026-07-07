#!/usr/bin/env python3
"""
validate_llm.py — valide le fournisseur LLM courant contre la vérité-terrain kappa.

Rejoue la classification des 105 vidéos de l'échantillon kappa avec le modèle
sélectionné (LLM_PROVIDER, ex. ollama), puis compare :
  - kappa(humain, modèle testé)   ← le chiffre qui décide
  - kappa(humain, Sonnet actuel)  ← la référence à battre / égaler

Ne touche PAS aux données de production. Usage :
    LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b python validate_llm.py --workers 2
"""

import argparse
import csv
import os
from collections import Counter, defaultdict

from classify import classify_one
from common import data_path, load_json, log
from llm import get_completer

HUMAN_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "kappa", "kappa_mes_codes.csv")


def kappa(pairs):
    if not pairs:
        return 0.0
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    cats = set(a for a, _ in pairs) | set(b for _, b in pairs)
    pa = Counter(a for a, _ in pairs)
    pb = Counter(b for _, b in pairs)
    pe = sum((pa[c] / n) * (pb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 0.0


def main():
    parser = argparse.ArgumentParser(description="Validation du LLM contre le kappa.")
    parser.add_argument("--workers", type=int, default=2,
                        help="Requêtes simultanées (Ollama local : garder bas, 2-4).")
    parser.add_argument("--human", type=str, default=HUMAN_CSV)
    args = parser.parse_args()

    # 1) Labels humains
    if not os.path.exists(args.human):
        log(f"ERREUR : codes humains introuvables ({args.human}). "
            f"Copie ton kappa_mes_codes.csv dans kappa/.")
        return
    human = {}
    with open(args.human, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["label_humain"].strip():
                human[r["video_id"]] = r["label_humain"].strip()

    # 2) Vidéos classées (labels Sonnet actuels + métadonnées pour re-classer)
    classified = {v["video_id"]: v for v in (load_json(data_path("videos_classified.json"), []) or [])
                  if isinstance(v.get("classification"), dict)}

    ids = [vid for vid in human if vid in classified]
    log(f"{len(ids)} vidéos avec label humain ET présentes dans le corpus classé.")

    complete, provider = get_completer()
    log(f"Fournisseur testé : {provider}")

    # 3) Re-classification par le modèle testé (en parallèle léger)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    tested = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(classify_one, complete, classified[vid]): vid for vid in ids}
        for fut in as_completed(futs):
            vid = futs[fut]
            c = fut.result()
            tested[vid] = c.get("narratif_principal") if "classification_error" not in c else None
            done += 1
            if done % 20 == 0:
                log(f"  {done}/{len(ids)}…")

    # 4) Comparaisons
    valid = [vid for vid in ids if tested.get(vid)]
    log(f"{len(valid)}/{len(ids)} classées sans erreur par le modèle testé.")

    k_test = kappa([(human[v], tested[v]) for v in valid])
    k_sonnet = kappa([(human[v], classified[v]["classification"]["narratif_principal"])
                      for v in valid])
    agree_ts = sum(1 for v in valid
                   if tested[v] == classified[v]["classification"]["narratif_principal"]) / len(valid)

    log("=" * 60)
    log(f"KAPPA humain vs {provider:<22} : {k_test:.3f}")
    log(f"KAPPA humain vs Sonnet (référence)     : {k_sonnet:.3f}")
    log(f"Accord modèle testé vs Sonnet          : {agree_ts*100:.0f}%")
    log("=" * 60)

    # 5) Où le modèle testé diffère de l'humain (top confusions)
    conf = defaultdict(Counter)
    for v in valid:
        if human[v] != tested[v]:
            conf[human[v]][tested[v]] += 1
    log("Principales confusions (humain → modèle testé) :")
    flat = sorted(((h, m, n) for h, d in conf.items() for m, n in d.items()),
                  key=lambda x: -x[2])
    for h, m, n in flat[:8]:
        log(f"  {h} → {m} : {n}")


if __name__ == "__main__":
    main()
