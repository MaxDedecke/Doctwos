#!/bin/bash
# Nach dem MCP-Verbindungsabbruch des Coder-Team-Laufs (23 von 72 Sitzungen): wartet auf das Ende des laufenden
# Coder-Prüfaufgaben-Laufs, baut das Backend mit längerem Keep-Alive neu, holt die fehlenden Coder-Team-Sitzungen
# nach (gleiche Seeds) und fährt danach das 14B (Team + Prüfaufgaben, 2 Wiederholungen).
cd "$(dirname "$0")"
P=http://62.169.158.40:46800
while pgrep -f 'run_ch9_matrix.sh pod_coder30b_32k' > /dev/null; do sleep 20; done
(cd ../.. && docker compose up -d --build backend-api > /dev/null 2>&1)
for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' doctus-backend)" = healthy ] && break; sleep 5; done
REPS=2 RESUME=1 ./run_ch9_matrix.sh pod_coder30b_32k $P qwen3-coder:30b 32768
REPS=2 ./run_ch9_matrix.sh pod_14b_32k $P qwen3:14b 32768 pull
echo "KETTE 3 BEENDET $(date +%H:%M:%S)" > results/ch9n_chain3.done
