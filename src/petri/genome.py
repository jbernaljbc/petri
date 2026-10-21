"""A cell's genome: a few numbers inherited with mutations.

No gene is free (the costs live in world.Rules): being fast or seeing far helps find food but burns
energy every tick, so selection looks for a balance rather than "everything maxed out".
Trust costs nothing: it only matters in encounters, through what the cell decides with it.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, replace

# gene → (minimum, maximum, standard deviation of one mutation)
LIMITS: dict[str, tuple[float, float, float]] = {
    "speed": (0.5, 3.0, 0.15),  # tiles per tick (the fraction accumulates)
    "vision": (1.0, 6.0, 0.3),  # radius in tiles for spotting food
    "repro_threshold": (20.0, 120.0, 5.0),  # energy at which it divides
    "child_share": (0.2, 0.7, 0.04),  # fraction of its energy passed on to the daughter
    "trust": (0.0, 1.0, 0.08),  # trust in others: the model gets it as the cell's personality
}


@dataclass(frozen=True, slots=True)
class Genome:
    speed: float = 1.0
    vision: float = 3.0
    repro_threshold: float = 60.0
    child_share: float = 0.4
    trust: float = 0.5

    @classmethod
    def random(cls, rng: random.Random) -> Genome:
        return cls(**{name: rng.uniform(lo, hi) for name, (lo, hi, _) in LIMITS.items()})

    def mutate(self, rng: random.Random, rate: float) -> Genome:
        """Copy with errors: each gene changes with probability `rate`, staying within its limits."""
        changes = {}
        for name, (lo, hi, sigma) in LIMITS.items():
            if rng.random() < rate:
                changes[name] = min(hi, max(lo, getattr(self, name) + rng.gauss(0, sigma)))
        return replace(self, **changes)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)
