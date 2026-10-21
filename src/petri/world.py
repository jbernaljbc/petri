"""El mundo: una grilla toroidal con comida que vuelve a crecer y células que viven en ella.

Fase 1, sin modelo: cada célula va hacia la comida más rica que ve, come, gasta energía según su genoma,
se divide cuando junta bastante (la hija hereda el genoma con mutaciones) y muere sin energía o de vieja.
Una casilla tiene a lo más una célula, así que el espacio también se compite. Cada tanto llega una
inmigrante de una familia nueva, para que nunca quede un solo linaje para siempre.

Los "encuentros" (dos células que pasan a ser vecinas) quedan en `World.encounters` después de cada
tick: society.py decide en cuáles piensan las células y aplica lo que deciden.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from .genome import Genome

NEIGHBORS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]


@dataclass(slots=True)
class Rules:
    width: int = 32
    height: int = 32
    food_max: float = 10.0  # comida máxima por casilla
    regrow: float = 0.08  # lo que crece por tick una casilla de fertilidad 1
    patches: int = 4  # manchas fértiles
    bite: float = 4.0  # lo que come una célula por tick
    base_cost: float = 0.4  # energía por tick solo por vivir
    speed_cost: float = 0.25  # × speed²
    vision_cost: float = 0.08  # × vision
    max_energy: float = 150.0
    max_age: int = 500
    mutation_rate: float = 0.3
    start_energy: float = 40.0
    immigrants: int = 300  # cada cuántos ticks llega una célula de una familia nueva (0 = nunca)

    def upkeep(self, genome: Genome) -> float:
        return self.base_cost + self.speed_cost * genome.speed**2 + self.vision_cost * genome.vision


@dataclass(slots=True)
class Cell:
    id: int
    x: int
    y: int
    energy: float
    genome: Genome
    born: int
    generation: int = 0
    lineage: int = 0  # id de la fundadora de su linaje
    parent: int | None = None
    stride: float = 0.0  # fracción de paso acumulada (speed no es entera)
    memory: deque[str] = field(default_factory=lambda: deque(maxlen=3))  # lo último que le pasó, para el modelo


@dataclass(slots=True)
class TickStats:
    births: int = 0
    deaths: int = 0
    starved: int = 0
    encounters: int = 0
    immigrants: int = 0


@dataclass
class World:
    rules: Rules
    seed: int
    rng: random.Random = field(init=False)
    tick: int = 0
    cells: dict[int, Cell] = field(default_factory=dict)
    last: TickStats = field(default_factory=TickStats)
    encounters: list[tuple[int, int]] = field(default_factory=list)  # parejas nuevas del último tick

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.fertility = self._fertility()
        self.food = [f * self.rules.food_max for f in self.fertility]
        self._at: dict[tuple[int, int], int] = {}
        self._next_id = 1
        self._pairs: set[tuple[int, int]] = set()
        self.frozen: set[int] = set()  # células que se detuvieron a pensar: comen y gastan, pero no caminan

    # ---- armar el cultivo

    def _fertility(self) -> list[float]:
        """Manchas gaussianas en el toro, entre 0.05 (árido) y 1 (fértil)."""
        w, h = self.rules.width, self.rules.height
        sigma = min(w, h) / 6
        centers = [(self.rng.uniform(0, w), self.rng.uniform(0, h)) for _ in range(self.rules.patches)]
        raw = []
        for y in range(h):
            for x in range(w):
                value = 0.0
                for cx, cy in centers:
                    dx = min(abs(x - cx), w - abs(x - cx))
                    dy = min(abs(y - cy), h - abs(y - cy))
                    value += math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))
                raw.append(value)
        top = max(raw) or 1.0
        return [0.05 + 0.95 * v / top for v in raw]

    def seed_cells(self, count: int) -> int:
        """Siembra fundadoras (o inmigrantes): genoma al azar y una familia nueva cada una."""
        free = [(x, y) for y in range(self.rules.height) for x in range(self.rules.width) if (x, y) not in self._at]
        spots = self.rng.sample(free, min(count, len(free)))
        for x, y in spots:
            cell = self._add(x, y, self.rules.start_energy, Genome.random(self.rng))
            cell.lineage = cell.id
        return len(spots)

    def _add(self, x: int, y: int, energy: float, genome: Genome, parent: Cell | None = None) -> Cell:
        cell = Cell(id=self._next_id, x=x, y=y, energy=energy, genome=genome, born=self.tick)
        if parent:
            cell.generation, cell.lineage, cell.parent = parent.generation + 1, parent.lineage, parent.id
        self._next_id += 1
        self.cells[cell.id] = cell
        self._at[(x, y)] = cell.id
        return cell

    # ---- geometría

    def index(self, x: int, y: int) -> int:
        return y * self.rules.width + x

    def wrap(self, x: int, y: int) -> tuple[int, int]:
        return x % self.rules.width, y % self.rules.height

    def delta(self, a: int, b: int, size: int) -> int:
        """Distancia con signo de a hacia b por el camino más corto del toro."""
        return (b - a + size // 2) % size - size // 2

    def free_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        spots = [self.wrap(x + dx, y + dy) for dx, dy in NEIGHBORS]
        return [p for p in spots if p not in self._at]

    def cell_at(self, x: int, y: int) -> Cell | None:
        cid = self._at.get((x, y))
        return self.cells[cid] if cid else None

    # ---- un tick

    def step(self) -> TickStats:
        self.tick += 1
        stats = TickStats()
        r = self.rules
        for i, f in enumerate(self.fertility):
            self.food[i] = min(r.food_max, self.food[i] + r.regrow * f)

        order = list(self.cells.values())
        self.rng.shuffle(order)
        for cell in order:
            if cell.id not in self.frozen:
                self._move(cell)
            self._eat(cell)
            cell.energy -= r.upkeep(cell.genome)
            if cell.energy <= 0:
                stats.starved += 1
                self._die(cell)
            elif self.tick - cell.born >= r.max_age:
                self._die(cell)
            elif cell.energy >= cell.genome.repro_threshold and self._divide(cell):
                stats.births += 1
        stats.deaths = len(order) + stats.births - len(self.cells)
        if r.immigrants and self.tick % r.immigrants == 0:
            stats.immigrants = self.seed_cells(1)
        self.encounters = self._new_encounters()
        stats.encounters = len(self.encounters)
        self.last = stats
        return stats

    def _move(self, cell: Cell) -> None:
        cell.stride += cell.genome.speed
        steps = int(cell.stride)
        cell.stride -= steps
        for _ in range(steps):
            if self.food[self.index(cell.x, cell.y)] >= self.rules.bite:
                return  # aquí hay comida de sobra: se queda comiendo
            target = self._best_food(cell)
            spot = self._step_toward(cell, target) if target else None
            if spot is None:
                options = self.free_neighbors(cell.x, cell.y)
                if not options:
                    return
                spot = self.rng.choice(options)
            del self._at[(cell.x, cell.y)]
            cell.x, cell.y = spot
            self._at[spot] = cell.id

    def _best_food(self, cell: Cell) -> tuple[int, int] | None:
        """La casilla libre con más comida dentro de su visión (a igual comida, la más cercana)."""
        # la fracción cuenta como probabilidad de ver una casilla más: si no, 1.9 vería lo mismo que 1.0 y
        # costaría más, y la selección siempre bajaría la visión al mínimo
        vision = cell.genome.vision
        radius = int(vision) + (self.rng.random() < vision % 1)
        here = self.food[self.index(cell.x, cell.y)]
        best, best_key = None, (here, 0)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if not (dx or dy):
                    continue
                x, y = self.wrap(cell.x + dx, cell.y + dy)
                if (x, y) in self._at:
                    continue
                key = (self.food[self.index(x, y)], -max(abs(dx), abs(dy)))
                if key > best_key:
                    best, best_key = (x, y), key
        return best

    def _step_toward(self, cell: Cell, target: tuple[int, int]) -> tuple[int, int] | None:
        sx = _sign(self.delta(cell.x, target[0], self.rules.width))
        sy = _sign(self.delta(cell.y, target[1], self.rules.height))
        for dx, dy in ((sx, sy), (sx, 0), (0, sy)):
            if not (dx or dy):
                continue
            spot = self.wrap(cell.x + dx, cell.y + dy)
            if spot not in self._at:
                return spot
        return None

    def _eat(self, cell: Cell) -> None:
        i = self.index(cell.x, cell.y)
        take = max(0.0, min(self.rules.bite, self.food[i], self.rules.max_energy - cell.energy))
        self.food[i] -= take
        cell.energy += take

    def _divide(self, cell: Cell) -> bool:
        spots = self.free_neighbors(cell.x, cell.y)
        if not spots:
            return False
        x, y = self.rng.choice(spots)
        share = cell.energy * cell.genome.child_share
        cell.energy -= share
        self._add(x, y, share, cell.genome.mutate(self.rng, self.rules.mutation_rate), parent=cell)
        return True

    def _die(self, cell: Cell) -> None:
        """La energía que le quedaba vuelve al suelo como comida."""
        i = self.index(cell.x, cell.y)
        self.food[i] = min(self.rules.food_max, self.food[i] + max(0.0, cell.energy) * 0.5)
        del self._at[(cell.x, cell.y)]
        del self.cells[cell.id]

    def _new_encounters(self) -> list[tuple[int, int]]:
        """Parejas de vecinas que no lo eran en el tick anterior, en orden estable (id menor primero)."""
        pairs = set()
        for (x, y), cid in self._at.items():
            for dx, dy in NEIGHBORS[4:]:  # la mitad de los vecinos basta para ver cada pareja una vez
                other = self._at.get(self.wrap(x + dx, y + dy))
                if other:
                    pairs.add((min(cid, other), max(cid, other)))
        new = sorted(pairs - self._pairs)
        self._pairs = pairs
        return new

    # ---- para mirar

    def summary(self) -> dict:
        cells = list(self.cells.values())
        genes: dict[str, float] = {}
        if cells:
            for name in Genome.__dataclass_fields__:
                genes[name] = sum(getattr(c.genome, name) for c in cells) / len(cells)
        return {
            "tick": self.tick,
            "population": len(cells),
            "lineages": len({c.lineage for c in cells}),
            "max_generation": max((c.generation for c in cells), default=0),
            "food": sum(self.food),
            "energy": sum(c.energy for c in cells),
            "genes": genes,
        }


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)
