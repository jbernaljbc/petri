#!/usr/bin/env bash
# Comparación en alfred: las mismas semillas con nani-4b y con el control (reglas con la misma latencia,
# y reglas instantáneas). Cada corrida deja su log en ~/petri-runs/<fecha>/; el resumen queda en resumen.txt.
#   nohup scripts/alfred/compare.sh 1 2 3 > /dev/null 2>&1 &
# Con el modelo a 4 ticks/s, 4000 ticks son ~17 min por semilla (de a una: la GPU es una sola).
set -euo pipefail
cd "$(dirname "$0")/../.."
TICKS=${TICKS:-4000}
OUT=~/petri-runs/$(date +%F-%H%M)
mkdir -p "$OUT"
run() {  # nombre, argumentos de petri headless
    local name=$1; shift
    docker compose run --rm -T petri headless --ticks "$TICKS" --every 500 "$@" > "$OUT/$name.log" 2>&1 </dev/null
    echo "$name: $(grep '^fin' "$OUT/$name.log")" >> "$OUT/resumen.txt"
}
for seed in "$@"; do
    run "s$seed-rules" --mind rules --seed "$seed"
    run "s$seed-rules-lat3" --mind rules --latency 3 --seed "$seed"
done
for seed in "$@"; do
    run "s$seed-llm" --mind llm --seed "$seed"
done
echo "listo $(date +%T)" >> "$OUT/resumen.txt"
