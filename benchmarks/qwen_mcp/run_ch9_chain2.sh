#!/bin/bash
# Rest der Pod-Kette mit zwei Wiederholungen (ohne fp16): wartet, bis der laufende 32B-Team-Lauf die Wiederholungen
# 1 und 2 beendet hat (72 Sitzungen; der Harness arbeitet Wiederholung für Wiederholung ab), stoppt ihn dann,
# fährt die Prüfaufgaben des 32B mit 2 Wiederholungen und danach Coder und 14B (je Team + Prüfaufgaben, 2 Wiederholungen).
cd "$(dirname "$0")"
P=http://62.169.158.40:46800
until [ "$(grep -c '^\[' results/ch9n_pod_32b_32k.log)" -ge 72 ]; do sleep 20; done
docker stop bench-ch9n-pod_32b_32k-team > /dev/null 2>&1
echo "gestoppt nach Wiederholung 2: $(date +%H:%M:%S)" >> results/ch9n_pod_32b_32k.log
REPS=2 STEPS=holdout ./run_ch9_matrix.sh pod_32b_32k $P qwen3:32b 32768
REPS=2 ./run_ch9_matrix.sh pod_coder30b_32k $P qwen3-coder:30b 32768 pull
REPS=2 ./run_ch9_matrix.sh pod_14b_32k $P qwen3:14b 32768 pull
echo "KETTE 2 BEENDET $(date +%H:%M:%S)" > results/ch9n_chain2.done
