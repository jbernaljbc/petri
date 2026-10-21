# Petri

A culture of cells on a grid: they eat, divide, mutate, compete for space and die, and when they meet
they decide what to do by thinking with a small local model — the same one a personal assistant
("nani") already serves on the home server, alfred (`nani-4b` = qwen3:4b-instruct on a 4 GB GPU, via
Ollama at `127.0.0.1:11434`), without loading another one. It's an experiment, kept apart from nani.

The cells think and speak in Spanish (the prompt, the actions and their memories); the code, the
viewer and the docs are in English.

## Running it

On alfred, with the model (deploy with `git push alfred main`, which builds the image):

```
ssh -t alfred 'cd ~/Projects/petri && docker compose run --rm petri run'
ssh -t alfred 'cd ~/Projects/petri && docker compose run --rm petri headless --ticks 2000'
```

Comparison (logs in `~/petri-runs/<date>/` plus a `summary.txt`; ~17 min per seed with the model):

```
ssh alfred 'cd ~/Projects/petri && nohup scripts/alfred/compare.sh 1 2 3 >/dev/null 2>&1 &'
```

On a PC, without the model or through a tunnel to alfred's Ollama:

```
uv sync
uv run petri run                         # "rules" mind: no model, the control group
uv run petri run --mind none --speed 5   # encounters do nothing
uv run petri headless --ticks 5000       # no viewer: numbers every 250 ticks
ssh -N -L 11435:127.0.0.1:11434 alfred &
uv run petri run --mind llm --ollama http://127.0.0.1:11435
uv run pytest
```

## The world

- A 32×32 toroidal grid with fertile patches: food regrows according to fertility.
- Each cell has energy, an age and a **genome**: speed, vision, the energy at which it divides, the
  fraction of energy it passes on to its daughter, and **trust**. Moving fast and seeing far cost
  energy every tick.
- It heads for the richest food it can see, eats, spends, divides when it reaches its threshold (the
  daughter inherits the genome with mutations, and the lineage) and dies when it runs out of energy or
  after 500 ticks; whatever it had left goes back to the ground as food. One cell per tile.
- Every 300 ticks an **immigrant** from a new family arrives (`--immigrants`, 0 = never): without them
  one family wins before tick ~2000 and from then on every encounter is between relatives.

## Encounters

When two cells become neighbors, each one decides on its own: **share** (gives away 20% of its energy),
**attack** (tries to take 30% of the other's; the one with more energy wins more easily, and a failed
attack costs 10% of its own), **ignore** or **talk**, and it can say a short phrase. When it thinks it
knows:

- its **personality**, from the **trust** gene (0 = very distrustful, 1 = very trusting), which is
  inherited and mutates like the others: selection decides what pays off;
- its energy and hunger, the other's energy, whether the other is family, how much food is nearby;
- the last 3 things that happened to it (it was given energy, it was attacked, someone said something).

nani-4b answers in ~0.75 s (JSON with a schema), so not every encounter thinks: a pair thinks if it
hasn't recently, if the mind can keep up (4 requests queued) and if both will live long enough to get
the answer; pairs from different families go first. While they think, both stand still. At 4 ticks per
second that's ~80 decisions per minute, nearly all of them applied. Requests go one at a time, so if
someone talks to nani meanwhile it waits for at most one short answer; and if the GPU has another model
loaded, petri pauses instead of evicting it.

`--mind rules` decides without a model, from trust and hunger: it's the control group (does it change
anything when a model thinks?) and the mind the tests use. On its own it thinks about every encounter;
with `--latency 3` it answers one at a time every 3 ticks, like nani-4b at 4 ticks/s, so it thinks
about the same few: that's the fair comparison.

In the viewer the green background is food, the dot's color is the lineage and `○` is a hungry cell;
below, the latest decisions. Same seed and `rules` mind, same culture.

## Phases

| Phase | | |
|---|---|---|
| 1. World without a model: food, energy, genome, mutation, terminal viewer | ✅ | |
| 2. Encounters with nani-4b, trust gene, short memory, compose on alfred | ✅ | |
| 2b. Immigrants, control group with the model's latency, comparison script | ✅ | |
| 3. Inherited text personality, traces (messages left on tiles) | ⏳ | |
| 4. History in SQLite and evolution charts | ⏳ | |
