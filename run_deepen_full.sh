#!/bin/bash
# Approfondissement top-5000 + finalisation (billing Gemini actif → workers élevés).
# 1) classif top-5000  2) langue  3) agrégation  4) commentaires (reprise)  5) agrégation finale
cd /Users/datafed/janco || exit 1
LOG=data/deepen_full.log
say() { echo "===== $(date '+%F %T') — $1 ====="; }

say "1/5 classif top-5000 (workers=8)" | tee -a $LOG
.venv/bin/python classify.py --by-views --limit 5000 --workers 8 >> data/classify_run.log 2>&1
echo "   classif finie" | tee -a $LOG

say "2/5 recalcul langue" | tee -a $LOG
.venv/bin/python language.py >> $LOG 2>&1

say "3/5 agrégation (dashboard)" | tee -a $LOG
.venv/bin/python aggregate.py >> $LOG 2>&1

say "4/5 commentaires (reprise, workers=8)" | tee -a $LOG
.venv/bin/python comments.py --by-views --limit 800 --workers 8 >> data/comments_run.log 2>&1

say "5/5 agrégation finale (intègre commentaires)" | tee -a $LOG
.venv/bin/python aggregate.py >> $LOG 2>&1

say "TERMINÉ" | tee -a $LOG
