#!/usr/bin/env bash
# Comparison on alfred: the same seeds with nani-4b and with the control (rules with the same latency,
# and instant rules). Each run leaves its log in ~/petri-runs/<date>/; the summary goes to summary.txt.
#   nohup scripts/alfred/compare.sh 1 2 3 > /dev/null 2>&1 &
# With the model at 4 ticks/s, 4000 ticks take ~17 min per seed (one at a time: there's a single GPU).
set -euo pipefail
cd "$(dirname "$0")/../.."
TICKS=${TICKS:-4000}
OUT=~/petri-runs/$(date +%F-%H%M)
mkdir -p "$OUT"
run() {  # name, petri headless arguments
    local name=$1; shift
    docker compose run --rm -T petri headless --ticks "$TICKS" --every 500 "$@" > "$OUT/$name.log" 2>&1 </dev/null
    echo "$name: $(grep '^end' "$OUT/$name.log")" >> "$OUT/summary.txt"
}
for seed in "$@"; do
    run "s$seed-rules" --mind rules --seed "$seed"
    run "s$seed-rules-lat3" --mind rules --latency 3 --seed "$seed"
done
for seed in "$@"; do
    run "s$seed-llm" --mind llm --seed "$seed"
done
echo "done $(date +%T)" >> "$OUT/summary.txt"
