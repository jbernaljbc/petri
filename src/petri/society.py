"""Encounters: which ones the cells think about, what they know while thinking and what their decisions do.

After each tick the world leaves the pairs that just became neighbors. A pair thinks if it hasn't
thought recently (pair_cooldown) and neither cell is waiting for another answer. With a slow mind (the
model answers ~1.5 times per second and the world doesn't wait for it) the mind must also keep up
(max_backlog) and both cells must live long enough to get the answer (otherwise the request is wasted);
pairs from different families go first. An instant mind thinks about all of them. Each cell decides on
its own, from a snapshot of the situation at that moment. While the pair thinks both cells stand still
(otherwise the answer arrives ~10 ticks later and they've walked apart); it applies if both are still
alive and close.

The actions and everything the cells remember are in Spanish: it's the language of the model's prompt.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Protocol

from .world import World

ACTIONS = ("compartir", "atacar", "ignorar", "hablar")  # share, attack, ignore, talk


@dataclass(frozen=True, slots=True)
class Request:
    """What a cell knows when it thinks."""

    tick: int
    cell: int
    other: int
    trust: float
    energy: float
    threshold: float  # energy at which it divides
    other_energy: float
    same_family: bool
    food_near: float  # 0..1, the food on the 9 tiles around it
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
    slow: bool  # takes ticks to answer: it has to pick which encounters to think about

    def submit(self, request: Request) -> None: ...
    def poll(self) -> list[Decision]: ...
    def backlog(self) -> int: ...


@dataclass(slots=True)
class SocialRules:
    share: float = 0.2  # fraction of its energy it gives away when sharing
    steal: float = 0.3  # fraction of the other's energy it takes when an attack succeeds
    attack_cost: float = 1.0
    lose: float = 0.1  # fraction of its energy it loses when an attack fails
    reach: int = 2  # maximum distance for a decision to still apply
    pair_cooldown: int = 150  # ticks before the same pair thinks again
    max_backlog: int = 4
    survive: int = 12  # ticks of energy each one needs for thinking to be worth it


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of what happened, for the viewer."""

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
        self.thoughts = 0  # requests sent to the mind
        self.unthought = 0  # encounters that didn't get to think
        self.late = 0  # answers that arrived when they could no longer apply
        self._pending: set[int] = set()
        self._cooldown: dict[tuple[int, int], int] = {}
        self._open: dict[tuple[int, int], int] = {}  # pairs thinking → answers still missing

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
            outcome = f"(no answer: {decision.error})"
        self.log.append(Entry(w.tick, cell.id, cell.lineage, req.other, other.lineage if other else -1,
                              action, decision.say, outcome))

    def _share(self, cell, other) -> str:
        gift = cell.energy * self.rules.share
        cell.energy -= gift
        other.energy = min(self.world.rules.max_energy, other.energy + gift)
        cell.memory.append(f"le regalaste {gift:.0f} de energía a una {_family(cell, other)}")
        other.memory.append(f"una {_family(other, cell)} te regaló {gift:.0f} de energía")
        return f"gives {gift:.0f}"

    def _attack(self, cell, other) -> str:
        cell.energy -= self.rules.attack_cost
        if self.world.rng.random() < cell.energy / max(1e-9, cell.energy + other.energy):
            loot = other.energy * self.rules.steal
            other.energy -= loot
            cell.energy = min(self.world.rules.max_energy, cell.energy + loot)
            cell.memory.append(f"atacaste a una {_family(cell, other)} y le quitaste {loot:.0f}")
            other.memory.append(f"una {_family(other, cell)} te atacó y te quitó {loot:.0f}")
            return f"wins, takes {loot:.0f}"
        loss = cell.energy * self.rules.lose
        cell.energy -= loss
        cell.memory.append(f"atacaste a una {_family(cell, other)}, te defendió y perdiste {loss:.0f}")
        other.memory.append(f"una {_family(other, cell)} te atacó y la rechazaste")
        return f"loses {loss:.0f}"

    def _distance(self, a, b) -> int:
        w = self.world
        return max(abs(w.delta(a.x, b.x, w.rules.width)), abs(w.delta(a.y, b.y, w.rules.height)))


def _family(cell, other) -> str:
    return "de tu familia" if cell.lineage == other.lineage else "de otra familia"
