# Cartographie des narratifs climat sur YouTube France

**Dashboard en ligne : https://lahourba.github.io/narratifs-climat-youtube/**

Outil qui collecte des vidéos YouTube francophones sur le climat, les classe par
**narratif dominant** via un LLM, pondère par l'audience (vues), et restitue le
tout dans un dashboard web.

**Objectif :** montrer à quels messages sur le climat la population française est
exposée sur YouTube — pas seulement ce qui est produit, mais ce qui est *vu*.
Le projet répond à une question posée publiquement par Jean-Marc Jancovici :
savoir, de façon centralisée, « à quels "messages" la population est exposée »
sur les réseaux sociaux.

> Périmètre assumé : YouTube uniquement. Corpus construit par recherche YouTube
> (requêtes de consensus **et** sceptiques) puis élargi par crawl de chaînes
> (~66 000 vidéos collectées) ; les vidéos les plus vues sont classifiées
> (~88 % des vues du corpus). La classification est assistée par IA, validée
> par un double codage humain (kappa de Cohen), et comporte une marge d'erreur.

---

## Architecture

Un pipeline de **scripts Python indépendants** et une **application React** qui
lit des JSON statiques.

```
collect.py / crawl_channels.py  →  transcripts.py  →  classify.py  →  language.py  →  aggregate.py  →  dashboard/
videos_raw.json                    videos_with_       videos_          (champ lang)    aggregates.json
                                   transcripts.json   classified.json                  + videos.json
                                                            ↘  comments.py → comments.json (climat de l'audience)
```

| Script              | Rôle                                                            | Sortie                                        |
| ------------------- | --------------------------------------------------------------- | --------------------------------------------- |
| `collect.py`        | Recherche multi-requêtes + métadonnées/stats YouTube             | `data/videos_raw.json`                        |
| `crawl_channels.py` | Élargissement du corpus par crawl de chaînes (effet boule de neige) | `data/videos_raw.json` + `data/crawl_state.json` |
| `transcripts.py`    | Transcripts FR (hors quota, proxy supporté)                      | `data/videos_with_transcripts.json`           |
| `classify.py`       | Classification du narratif via LLM (multi-fournisseurs)          | `data/videos_classified.json`                 |
| `language.py`       | Détection de langue (le filtre FR strict est appliqué à l'agrégation) | champ `lang` dans `videos_classified.json` |
| `comments.py`       | Analyse du « climat » des sections de commentaires               | `dashboard/src/data/comments.json`            |
| `aggregate.py`      | Agrégats pondérés par les vues (FR uniquement, hors-sujet exclu) | `dashboard/src/data/{aggregates,videos}.json` |
| `dashboard/`        | Visualisation (React + Vite + TS + Tailwind + Recharts)          | site statique                                 |

Chaque script est **lançable seul** et **idempotent** (relançable sans tout
recasser) : les éléments déjà traités sont réutilisés.

`taxonomy.py` est la source unique de vérité pour la taxonomie ; `llm.py`
abstrait le fournisseur LLM (`LLM_PROVIDER` : anthropic, gemini, openai,
ollama) ; `validate_llm.py` compare un modèle au codage humain de référence
(dossier `kappa/`, protocole inclus).

---

## Clés API nécessaires

| Variable d'environnement | Utilisée par            | Où l'obtenir                                |
| ------------------------ | ----------------------- | -------------------------------------------- |
| `YOUTUBE_API_KEY`        | `collect.py`, `crawl_channels.py`, `comments.py` | Google Cloud Console → YouTube Data API v3 |
| `ANTHROPIC_API_KEY` ou `GEMINI_API_KEY`… | `classify.py`, `comments.py` (selon `LLM_PROVIDER`) | console.anthropic.com / aistudio.google.com |

Voir `.env.example` pour la liste complète (proxy transcripts, choix du modèle…).
`transcripts.py` n'utilise pas de clé (youtube-transcript-api est hors quota).

---

## Installation

### 1. Pipeline Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # puis renseigner les clés
```

### 2. Dashboard

```bash
cd dashboard
npm install
```

---

## Exécution, dans l'ordre

```bash
# (venv activé, .env renseigné)
python collect.py                      # 1. collecte (option : crawl_channels.py pour élargir)
python transcripts.py                  # 2. transcripts FR
python classify.py                     # 3. classification LLM (--limit N --by-views pour cibler les plus vues)
python language.py                     # 4. détection de langue
python comments.py --by-views --limit 800   # 5. (optionnel) climat des commentaires
python aggregate.py                    # 6. agrégats pondérés
cd dashboard && npm run dev            # 7. dashboard (http://localhost:5173)
```

Le dashboard est déployé automatiquement sur GitHub Pages à chaque push sur
`main` (`.github/workflows/deploy.yml`).

---

## La taxonomie des 8 narratifs

| Clé                        | Définition                                                                                    |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| `URGENCE_MOBILISATION`     | Le climat est une crise grave nécessitant une action forte et rapide.                          |
| `SCIENCE_PEDAGOGIE`        | Explication factuelle des mécanismes, données, rapports GIEC, registre neutre.                 |
| `SOLUTIONS_TECHNO`         | Focus sur les solutions : renouvelables, sobriété, innovation, gestes.                          |
| `SCEPTICISME_MINIMISATION` | Remise en cause de la gravité, du consensus, ou de l'origine humaine.                           |
| `CRITIQUE_INACTION`        | Réclame PLUS d'action : inaction des gouvernements, greenwashing, lobby fossile.               |
| `OPPOSITION_ECOLOGIE`      | S'oppose aux politiques écologiques : « écologie punitive », anti-ZFE, coût des renouvelables. |
| `ANXIETE_EFFONDREMENT`     | Registre anxiogène : collapsologie, fatalisme, éco-anxiété.                                     |
| `HORS_SUJET`               | Le climat n'est qu'un prétexte/accroche — **exclu du rapport** à l'agrégation.                 |

La distinction `CRITIQUE_INACTION` / `OPPOSITION_ECOLOGIE` est centrale : les
deux critiquent, mais l'une réclame plus d'écologie et l'autre moins.

### Validation de la classification

La classification LLM a été confrontée à un double codage humain sur un
échantillon (protocole et données dans `kappa/`) : kappa de Cohen ≈ 0,45
(accord modéré), les désaccords étant concentrés sur les frontières
SCIENCE↔SOLUTIONS et URGENCE↔CRITIQUE_INACTION. Les règles de tranchement
correspondantes ont été intégrées au prompt.

---

## Le dashboard

Quatre vues, navigation simple, lisible sur mobile :

- **Cartographie** — répartition des narratifs pondérée par les vues, avec
  toggle *vues / nombre de vidéos* pour montrer l'écart entre ce qui est
  produit et ce qui est vu. + top chaînes par narratif.
- **Évolution** — aires empilées des vues par narratif et par trimestre,
  bascule valeur absolue / part (100 %), sélecteur de période.
- **Audience** — le « climat » des sections de commentaires (adhésion,
  scepticisme, hostilité à l'écologie, complotisme…), son évolution, et les
  vidéos pro-climat aux commentaires les plus hostiles.
- **Explorateur** — table filtrable/triable des vidéos classées, avec lien
  YouTube, narratif et score de confiance.

### Limites connues (assumées)

- Les vues sont **cumulées depuis la publication** : c'est un proxy de
  l'exposition, pas une mesure de l'audience récente.
- Les vues ne disent rien des **personnes** (pas de reach unique, pas de
  démographie — l'API publique ne les expose pas).
- Une partie des vues provient de **campagnes publicitaires** de chaînes
  institutionnelles (option d'exclusion dans la Cartographie).
- Le corpus reflète ce que la recherche et le graphe de chaînes YouTube
  remontent, pas l'intégralité de la plateforme.

---

## Robustesse

- **Ne crashe jamais sur une vidéo isolée** : chaque erreur (API down,
  transcript absent, JSON malformé) est loggée et le traitement continue.
- **Écriture atomique** des JSON + sauvegardes de progression régulières ;
  scripts reprenables après interruption.
- **Quota YouTube** : consommation loggée, arrêt propre si quota épuisé.
- **Parsing LLM robuste** : isolation du bloc JSON, validation de structure,
  retries avec backoff (gère les rate-limits).

---

## Structure des fichiers

```
.
├── collect.py            # collecte YouTube (recherche)
├── crawl_channels.py     # élargissement par crawl de chaînes
├── transcripts.py        # transcripts FR
├── classify.py           # classification LLM
├── language.py           # détection de langue
├── comments.py           # climat des sections de commentaires
├── aggregate.py          # agrégats pondérés
├── taxonomy.py           # taxonomie + schéma partagés
├── llm.py                # abstraction multi-fournisseurs LLM
├── validate_llm.py       # validation contre le codage humain
├── kappa/                # protocole + données du double codage (Cohen's kappa)
├── common.py             # helpers (JSON atomique, durée, logs)
├── data/                 # JSON intermédiaires (gitignored, régénérables)
└── dashboard/
    ├── src/
    │   ├── App.tsx
    │   ├── components/    # Cartographie / Evolution / Audience / Explorateur
    │   ├── constants.ts   # libellés, couleurs, formats
    │   ├── types.ts
    │   └── data/          # aggregates.json + videos.json + comments.json (générés)
    └── package.json
```
