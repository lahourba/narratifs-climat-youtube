# Protocole d'accord inter-annotateur (Cohen's kappa)

Objectif : mesurer l'accord entre **ton codage humain** et le **label de l'IA**, narratif principal uniquement.

## Fichiers
- `kappa_sample_coding.csv` — **à coder en aveugle** (105 vidéos, 15 par narratif, ordre mélangé, SANS le label IA).
- `kappa_sample_key.csv` — les labels de l'IA, à n'ouvrir **qu'après** ton codage.

## Les 7 narratifs (code avec EXACTEMENT ces clés dans la colonne `label_humain`)

1. **URGENCE_MOBILISATION** — le climat est une crise grave nécessitant une action forte et rapide.
2. **SCIENCE_PEDAGOGIE** — explication factuelle des mécanismes, données, GIEC, registre neutre.
3. **SOLUTIONS_TECHNO** — focus sur les solutions : renouvelables, sobriété, innovation, gestes.
4. **SCEPTICISME_MINIMISATION** — conteste la SCIENCE : gravité, consensus, ou origine humaine.
5. **CRITIQUE_INACTION** — réclame PLUS d'action : dénonce l'inaction des gouvernements, le greenwashing, le lobby fossile (accepte la science).
6. **OPPOSITION_ECOLOGIE** — s'oppose AUX POLITIQUES écologiques : écologie punitive, anti-ZFE, coût des renouvelables (n'attaque pas forcément la science).
7. **ANXIETE_EFFONDREMENT** — registre anxiogène : collapsologie, fatalisme, éco-anxiété.

> Règle de tranche : code la NARRATION DOMINANTE de la vidéo (l'intention principale de l'auteur), pas un thème secondaire.

## Démarche
1. Pour chaque ligne de `kappa_sample_coding.csv`, lis titre + description + extrait de transcript (et ouvre la vidéo si besoin), puis remplis `label_humain` avec une des 7 clés. Mets une remarque en colonne `notes` pour les cas limites.
2. Quand tout est codé, joins par `video_id` avec `kappa_sample_key.csv`.
3. Calcule le kappa (Python) :
   ```python
   import pandas as pd
   from sklearn.metrics import cohen_kappa_score, confusion_matrix
   a = pd.read_csv("kappa_sample_coding.csv")
   b = pd.read_csv("kappa_sample_key.csv")
   m = a.merge(b, on="video_id")
   print("kappa global:", cohen_kappa_score(m.label_humain, m.ia_principal))
   ```

## Ce que tu me renvoies pour améliorer le modèle
1. La **matrice de confusion** (humain × IA).
2. Les **cas de désaccord** : `video_id` + ton label + label IA + une phrase de ta raison.
3. Le **kappa par catégorie** (pas seulement global).
4. Tes **définitions opérationnelles** / règles de tranche sur les cas limites.
5. Ton verdict sur les litiges connus (cas Clique « rééquilibrage »).

→ Chaque désaccord systématique deviendra une règle de désambiguïsation dans le prompt.
