#!/bin/bash
# Orchestration ponctuelle : attend la fin des transcripts, puis lance la
# classif Gemini top 1000, puis affiche le bilan des deux étapes.
cd /Users/datafed/janco || exit 1

# 1) Attendre la fin des transcripts en cours.
while pgrep -f "transcripts.py" >/dev/null; do sleep 30; done
echo "=== TRANSCRIPTS TERMINÉS $(date '+%F %T') ==="
tail -6 data/transcripts_run.log

# 2) Lancer la classif Gemini (gratuit) sur le même périmètre top 1000.
echo "===== $(date '+%F %T') — classify --by-views --limit 1000 (gemini) =====" >> data/classify_run.log
.venv/bin/python classify.py --by-views --limit 1000 >> data/classify_run.log 2>&1

# 3) Bilan classif.
echo "=== CLASSIF TERMINÉE $(date '+%F %T') ==="
tail -8 data/classify_run.log
