#!/bin/bash
# Attend la passe transcripts en cours, puis fait jusqu'à 3 passes de rattrapage
# (retry auto des proxy_failed/unavailable, IP fraîche), s'arrête quand le gain
# d'« ok » plafonne, puis lance la classif Gemini top 1000.
cd /Users/datafed/janco || exit 1

count_ok() {
  .venv/bin/python -c "import json;d=json.load(open('data/videos_with_transcripts.json'));print(sum(1 for v in d if v.get('transcript_status')=='ok'))"
}

# 1) Attendre la fin de la passe en cours.
while pgrep -f "transcripts.py" >/dev/null; do sleep 30; done
echo "=== PASSE 1 TERMINÉE $(date '+%F %T') — ok=$(count_ok) ===" >> data/transcripts_run.log

# 2) Passes de rattrapage (max 3), arrêt si gain < 15.
for pass in 1 2 3; do
  before=$(count_ok)
  echo "===== $(date '+%F %T') — rattrapage $pass (ok avant=$before) =====" >> data/transcripts_run.log
  .venv/bin/python transcripts.py --by-views --limit 1000 >> data/transcripts_run.log 2>&1
  after=$(count_ok)
  gain=$((after - before))
  echo "===== rattrapage $pass fini — ok=$after (+$gain) =====" >> data/transcripts_run.log
  if [ "$gain" -lt 15 ]; then
    echo "Plateau atteint (gain=$gain), fin des passes." >> data/transcripts_run.log
    break
  fi
done

FINAL_OK=$(count_ok)
echo "=== TRANSCRIPTS TERMINÉS $(date '+%F %T') — total ok=$FINAL_OK ===" >> data/transcripts_run.log

# 3) Classif Gemini (gratuit) top 1000.
echo "===== $(date '+%F %T') — classify --by-views --limit 1000 (gemini) =====" >> data/classify_run.log
.venv/bin/python classify.py --by-views --limit 1000 >> data/classify_run.log 2>&1
echo "=== CLASSIF TERMINÉE $(date '+%F %T') ===" >> data/classify_run.log
tail -6 data/classify_run.log
