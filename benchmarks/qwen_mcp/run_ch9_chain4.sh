#!/bin/bash
# Coder fortsetzen (fehlende Sitzungen, gleiche Seeds), dann 14B. Das Backend muss vorher mit Schlüsseltrennung
# und Keep-alive 75 s neu gebaut sein (docker compose up -d --build backend-api im Repo-Wurzelverzeichnis).
cd "$(dirname "$0")"
P=http://62.169.158.40:46800
REPS=2 RESUME=1 ./run_ch9_matrix.sh pod_coder30b_32k $P qwen3-coder:30b 32768
REPS=2 ./run_ch9_matrix.sh pod_14b_32k $P qwen3:14b 32768 pull
echo "KETTE 4 BEENDET $(date +%H:%M:%S)" > results/ch9n_chain4.done
