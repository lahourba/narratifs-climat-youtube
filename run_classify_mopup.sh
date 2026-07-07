#!/bin/bash
# Attend la passe classif en cours (workers=8), puis fait des passes de mop-up à
# faible concurrence (workers=3, sous la limite de débit Gemini) pour rattraper les
# HTTPError (rate-limit). S'arrête quand il ne reste plus d'erreurs ou que ça plafonne.
cd /Users/datafed/janco || exit 1

count_err() {
  .venv/bin/python -c "import json;d=json.load(open('data/videos_classified.json'));print(sum(1 for v in d if 'classification_error' in (v.get('classification') or {})))"
}

# 1) Attendre la fin de la passe en cours.
while pgrep -f "classify.py" >/dev/null; do sleep 20; done
echo "===== $(date '+%F %T') — passe classif principale finie, erreurs=$(count_err) =====" >> data/classify_run.log

# 2) Mop-up à faible concurrence (max 4 passes, stop si plus d'erreurs ou plateau).
for pass in 1 2 3 4; do
  before=$(count_err)
  [ "$before" -eq 0 ] && { echo "Plus d'erreurs, fin." >> data/classify_run.log; break; }
  echo "===== $(date '+%F %T') — mop-up $pass (erreurs avant=$before, workers=3) =====" >> data/classify_run.log
  .venv/bin/python classify.py --by-views --limit 1000 --workers 2 >> data/classify_run.log 2>&1
  after=$(count_err)
  echo "===== mop-up $pass fini — erreurs=$after (résolues: $((before-after))) =====" >> data/classify_run.log
  [ "$((before-after))" -lt 5 ] && { echo "Plateau (les erreurs restantes sont tenaces), fin." >> data/classify_run.log; break; }
done
echo "=== CLASSIF + MOP-UP TERMINÉS $(date '+%F %T') ===" >> data/classify_run.log
