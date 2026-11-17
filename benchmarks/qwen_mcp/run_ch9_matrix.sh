#!/bin/bash
# Kapitel 9, voller Lauf auf dem neuen Stand: Team-Aufgaben (12) und Prüfaufgaben (6), je 3 Gruppen x 3 Wiederholungen.
# Aufruf: run_ch9_matrix.sh <tag> <ollama-url> <modell> <num_ctx> [pull]
#   tag   Kennung der Konfiguration (Dateiname der Ergebnisse)
#   pull  nur für den Pod: Modell vorher laden (setzt bei Abbrüchen selbst fort), andere Modelle entladen
set -u
cd "$(dirname "$0")"
TAG=$1; URL=$2; MODEL=$3; CTX=$4; PULL=${5:-}
REPS=${REPS:-3}; STEPS=${STEPS:-"team holdout"}; RESUME=${RESUME:-}; ARMS=${ARMS:-none,local,mcp}   # z. B. REPS=2 STEPS=holdout ARMS=mcp
LOG=results/ch9n_${TAG}.log
echo "start $(date +%H:%M:%S) $TAG $MODEL ctx=$CTX" >> "$LOG"

if [ "$PULL" = "pull" ]; then
  # laufende Modelle entladen, damit Gewichte und Fenster das VRAM nicht teilen
  for m in $(curl -s -m 30 "$URL/api/ps" | python3 -I -c 'import sys,json; print(" ".join(x["name"] for x in json.load(sys.stdin)["models"]))'); do
    curl -s -m 60 "$URL/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" > /dev/null
  done
  for n in 1 2 3 4 5 6; do
    curl -s -m 30 "$URL/api/tags" | grep -q "\"$MODEL\"" && break
    curl -s -N -m 1800 "$URL/api/pull" -d "{\"model\":\"$MODEL\",\"stream\":true}" > "results/ch9n_${TAG}_pull_$n.log" 2>&1
  done
  curl -s -m 30 "$URL/api/tags" | grep -q "\"$MODEL\"" || { echo "exit 9 Modell $MODEL nicht vorhanden" >> "$LOG"; exit 9; }
fi

run() {  # <Aufgabendatei> <Festlegung> <Ausgabekennung>
  docker run --rm --name "bench-ch9n-$TAG-$3" --network host --memory 1g --cpus 1 --env-file .env.local \
    -e OLLAMA_URL="$URL" -e BENCH_MODEL="$MODEL" -e BENCH_NUM_CTX="$CTX" \
    -v "$PWD:/bench" -w /bench --entrypoint python doctus-backend-api:latest harness/run.py \
    --lock "$2" --tasks-file "$1" --reps "$REPS" --arms "$ARMS" ${RESUME:+--resume} --out "ch9n_${TAG}_$3" >> "$LOG" 2>&1
}
case " $STEPS " in *" team "*) run tasks_team.json manifest_ch9.json team;; esac
case " $STEPS " in *" holdout "*) run tasks_team_holdout.json manifest_ch9_holdout.json holdout;; esac
echo "exit $?" >> "$LOG"
