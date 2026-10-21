"""Genoma de una célula: unos pocos números que se heredan con mutaciones.

Ningún gen es gratis (los costos están en world.Rules): ser rápido o ver lejos ayuda a encontrar comida
pero gasta energía en cada tick, así que la selección busca un equilibrio y no "todo al máximo".
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, replace

# gen → (mínimo, máximo, desviación de una mutación)
LIMITS: dict[str, tuple[float, float, float]] = {
    "speed": (0.5, 3.0, 0.15),  # casillas por tick (la fracción se acumula)
    "vision": (1.0, 6.0, 0.3),  # radio en casillas para ver comida
    "repro_threshold": (20.0, 120.0, 5.0),  # energía con la que se divide
    "child_share": (0.2, 0.7, 0.04),  # fracción de su energía que le pasa a la hija
}


@dataclass(frozen=True, slots=True)
class Genome:
    speed: float = 1.0
    vision: float = 3.0
    repro_threshold: float = 60.0
    child_share: float = 0.4

    @classmethod
    def random(cls, rng: random.Random) -> Genome:
        return cls(**{name: rng.uniform(lo, hi) for name, (lo, hi, _) in LIMITS.items()})

    def mutate(self, rng: random.Random, rate: float) -> Genome:
        """Copia con errores: cada gen cambia con probabilidad `rate`, sin salirse de sus límites."""
        changes = {}
        for name, (lo, hi, sigma) in LIMITS.items():
            if rng.random() < rate:
                changes[name] = min(hi, max(lo, getattr(self, name) + rng.gauss(0, sigma)))
        return replace(self, **changes)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)
