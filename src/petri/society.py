"""Los encuentros: en cuáles piensan las células, qué saben al pensar y qué pasa con lo que deciden.

Después de cada tick el mundo deja las parejas que acaban de quedar vecinas. Una pareja piensa si no
pensó hace poco (pair_cooldown) y si ninguna de las dos está esperando otra respuesta. Con una mente
lenta (el modelo contesta ~1.5 veces por segundo y el mundo no lo espera) además tiene que dar abasto
(max_backlog) y las dos tienen que alcanzar a vivir hasta la respuesta (si no, el pedido se pierde);
primero las de familias distintas. Una mente instantánea piensa en todas. Cada célula decide por su
cuenta, con una foto de la situación del momento. Mientras la pareja piensa las dos se quedan quietas
(si no, la respuesta llega ~10 ticks después y ya se alejaron); se aplica si las dos siguen vivas y cerca.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Protocol

from .world import World

ACTIONS = ("compartir", "atacar", "ignorar", "hablar")


@dataclass(frozen=True, slots=True)
class Request:
    """Lo que una célula sabe cuando piensa."""

    tick: int
    cell: int
    other: int
    trust: float
    energy: float
    threshold: float  # energía con la que se divide
    other_energy: float
    same_family: bool
    food_near: float  # 0..1, la comida de las 9 casillas a su alrededor
    memory: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    request: Request
    action: str
    say: str = ""
    seconds: float = 0.0
    error: str = ""


class Mind(Protocol):
    status: str
    slow: bool  # tarda ticks en contestar: hay que elegir en qué encuentros piensa

    def submit(self, request: Request) -> None: ...
    def poll(self) -> list[Decision]: ...
    def backlog(self) -> int: ...


@dataclass(slots=True)
class SocialRules:
    share: float = 0.2  # fracción de su energía que regala al compartir
    steal: float = 0.3  # fracción de la energía de la otra que se lleva si gana un ataque
    attack_cost: float = 1.0
    lose: float = 0.1  # fracción de su energía que pierde si el ataque le sale mal
    reach: int = 2  # distancia máxima para que la decisión todavía se aplique
    pair_cooldown: int = 150  # ticks antes de que la misma pareja vuelva a pensar
    max_backlog: int = 4
    survive: int = 12  # ticks de energía que necesita cada una para que valga la pena que piense


@dataclass(frozen=True, slots=True)
class Entry:
    """Una línea de lo que pasó, para el visor."""

    tick: int
    cell: int
    lineage: int
    other: int
    other_lineage: int
    action: str
    say: str
    outcome: str


class Society:
    def __init__(self, world: World, mind: Mind, rules: SocialRules | None = None) -> None:
        self.world = world
        self.mind = mind
        self.rules = rules or SocialRules()
        self.log: deque[Entry] = deque(maxlen=8)
        self.actions: Counter[str] = Counter()
        self.thoughts = 0  # pedidos a la mente
        self.unthought = 0  # encuentros que no alcanzaron a pensar
        self.late = 0  # respuestas que llegaron cuando ya no se podían aplicar
        self._pending: set[int] = set()
        self._cooldown: dict[tuple[int, int], int] = {}
        self._open: dict[tuple[int, int], int] = {}  # parejas pensando → respuestas que faltan

    def after_step(self) -> None:
        for decision in self.mind.poll():
            self._apply(decision)
        for a, b in self._chosen():
            for cell, other in ((a, b), (b, a)):
                self.mind.submit(self._request(cell, other))
                self._pending.add(cell)
                self.thoughts += 1
            self._cooldown[(a, b)] = self.world.tick + self.rules.pair_cooldown
            self._open[(a, b)] = 2
        self.world.frozen = {cid for pair in self._open for cid in pair}

    def _chosen(self) -> list[tuple[int, int]]:
        w = self.world
        candidates = []
        for pair in w.encounters:
            if self._cooldown.get(pair, 0) > w.tick:
                continue
            if pair[0] in self._pending or pair[1] in self._pending:
                self.unthought += 1
                continue
            if self.mind.slow and any(c.energy < self.rules.survive * w.rules.upkeep(c.genome)
                                      for c in map(w.cells.get, pair)):
                self.unthought += 1
                continue
            candidates.append(pair)
        if len(self._cooldown) > 5000:
            self._cooldown = {p: t for p, t in self._cooldown.items() if t > w.tick}
        if not self.mind.slow:
            return candidates

        chosen = []
        for pair in sorted(candidates, key=lambda p: w.cells[p[0]].lineage == w.cells[p[1]].lineage):
            if self.mind.backlog() + 2 * (len(chosen) + 1) > self.rules.max_backlog:
                self.unthought += 1
            else:
                chosen.append(pair)
        return chosen

    def _request(self, cell_id: int, other_id: int) -> Request:
        w = self.world
        cell, other = w.cells[cell_id], w.cells[other_id]
        food = sum(w.food[w.index(*w.wrap(cell.x + dx, cell.y + dy))] for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        return Request(
            tick=w.tick, cell=cell.id, other=other.id, trust=cell.genome.trust, energy=cell.energy,
            threshold=cell.genome.repro_threshold, other_energy=other.energy,
            same_family=cell.lineage == other.lineage, food_near=food / (9 * w.rules.food_max),
            memory=tuple(cell.memory),
        )

    def _apply(self, decision: Decision) -> None:
        req = decision.request
        self._pending.discard(req.cell)
        pair = (min(req.cell, req.other), max(req.cell, req.other))
        self._open[pair] = self._open.get(pair, 1) - 1
        if self._open[pair] <= 0:
            del self._open[pair]
        w = self.world
        cell, other = w.cells.get(req.cell), w.cells.get(req.other)
        if cell is None:
            self.late += 1
            return
        action = decision.action if decision.action in ACTIONS else "ignorar"
        if other is None or self._distance(cell, other) > self.rules.reach:
            if action in ("compartir", "atacar"):
                self.late += 1
                return
            outcome = ""
        elif action == "compartir":
            outcome = self._share(cell, other)
        elif action == "atacar":
            outcome = self._attack(cell, other)
        else:
            outcome = ""
        self.actions[action] += 1
        if decision.say and other and self._distance(cell, other) <= self.rules.reach:
            other.memory.append(f"una {_family(other, cell)} te dijo «{decision.say}»")
        if decision.error:
            outcome = f"(sin respuesta: {decision.error})"
        self.log.append(Entry(w.tick, cell.id, cell.lineage, req.other, other.lineage if other else -1,
                              action, decision.say, outcome))

    def _share(self, cell, other) -> str:
        gift = cell.energy * self.rules.share
        cell.energy -= gift
        other.energy = min(self.world.rules.max_energy, other.energy + gift)
        cell.memory.append(f"le regalaste {gift:.0f} de energía a una {_family(cell, other)}")
        other.memory.append(f"una {_family(other, cell)} te regaló {gift:.0f} de energía")
        return f"le da {gift:.0f}"

    def _attack(self, cell, other) -> str:
        cell.energy -= self.rules.attack_cost
        if self.world.rng.random() < cell.energy / max(1e-9, cell.energy + other.energy):
            loot = other.energy * self.rules.steal
            other.energy -= loot
            cell.energy = min(self.world.rules.max_energy, cell.energy + loot)
            cell.memory.append(f"atacaste a una {_family(cell, other)} y le quitaste {loot:.0f}")
            other.memory.append(f"una {_family(other, cell)} te atacó y te quitó {loot:.0f}")
            return f"gana, le quita {loot:.0f}"
        loss = cell.energy * self.rules.lose
        cell.energy -= loss
        cell.memory.append(f"atacaste a una {_family(cell, other)}, te defendió y perdiste {loss:.0f}")
        other.memory.append(f"una {_family(other, cell)} te atacó y la rechazaste")
        return f"pierde {loss:.0f}"

    def _distance(self, a, b) -> int:
        w = self.world
        return max(abs(w.delta(a.x, b.x, w.rules.width)), abs(w.delta(a.y, b.y, w.rules.height)))


def _family(cell, other) -> str:
    return "de tu familia" if cell.lineage == other.lineage else "de otra familia"
