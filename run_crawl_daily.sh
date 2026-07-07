#!/bin/bash
# Lance un run quotidien du crawl (reprend automatiquement l'état).
# Le .env (clé YouTube) est chargé automatiquement par common.load_dotenv.
PROJ="/Users/datafed/janco"
cd "$PROJ" || exit 1

# Ne pas empiler si un crawl est déjà en cours.
if pgrep -f "crawl_channels.py" >/dev/null 2>&1; then
    echo "$(date '+%F %T') — crawl déjà en cours, on saute." >> data/crawl_cron.log
    exit 0
fi

# Au réveil, launchd démarre souvent avant que le réseau/DNS soit remonté.
# On attend que googleapis soit joignable (max ~5 min) avant de lancer.
for i in $(seq 1 30); do
    if curl -s -m 8 -o /dev/null https://www.googleapis.com/discovery/v1/apis; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "$(date '+%F %T') — réseau indisponible après 5 min, abandon du run." >> data/crawl_cron.log
        exit 0
    fi
    sleep 10
done

echo "===== $(date '+%F %T') — run quotidien =====" >> data/crawl_cron.log
"$PROJ/.venv/bin/python" crawl_channels.py --max-videos 400 >> data/crawl_cron.log 2>&1
