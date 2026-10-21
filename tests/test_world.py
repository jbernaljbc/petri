import random

from petri.genome import LIMITS, Genome
from petri.world import Rules, World


def _world(seed: int = 7, cells: int = 30, **rules) -> World:
    world = World(Rules(width=20, height=20, **rules), seed=seed)
    world.seed_cells(cells)
    return world


def _run(world: World, ticks: int) -> None:
    for _ in range(ticks):
        world.step()


def test_same_seed_same_culture():
    a, b = _world(), _world()
    _run(a, 300)
    _run(b, 300)
    assert a.summary() == b.summary()
    assert [(c.id, c.x, c.y) for c in a.cells.values()] == [(c.id, c.x, c.y) for c in b.cells.values()]


def test_mutation_stays_within_limits():
    rng = random.Random(1)
    genome = Genome()
    for _ in range(2000):
        genome = genome.mutate(rng, rate=1.0)
        for name, (lo, hi, _) in LIMITS.items():
            assert lo <= getattr(genome, name) <= hi


def test_one_cell_per_tile():
    world = _world(cells=80)
    for _ in range(200):
        world.step()
        spots = [(c.x, c.y) for c in world.cells.values()]
        assert len(spots) == len(set(spots))
        assert all(world.cell_at(x, y) for x, y in spots)


def test_division_splits_energy_and_inherits_lineage():
    world = World(Rules(width=10, height=10), seed=3)
    world.seed_cells(1)
    parent = next(iter(world.cells.values()))
    parent.energy = 100.0
    assert world._divide(parent)
    child = next(c for c in world.cells.values() if c.id != parent.id)
    assert parent.energy + child.energy == 100.0
    assert (child.lineage, child.parent, child.generation) == (parent.lineage, parent.id, 1)


def test_starvation_without_food():
    world = _world(regrow=0.0)
    world.food = [0.0] * len(world.food)
    _run(world, 200)
    assert not world.cells


def test_encounter_counts_only_new_neighbors():
    world = World(Rules(width=10, height=10), seed=1)
    a = world._add(2, 2, 50.0, Genome())
    world._add(3, 2, 50.0, Genome())
    assert world._new_encounters() == [(1, 2)]
    assert world._new_encounters() == []  # siguen juntas: no es un encuentro nuevo
    del world._at[(a.x, a.y)]
    a.x = 7
    world._at[(a.x, a.y)] = a.id
    assert world._new_encounters() == []


def test_torus_delta_takes_shortest_way():
    world = World(Rules(width=10, height=10), seed=1)
    assert world.delta(1, 9, 10) == -2
    assert world.delta(9, 1, 10) == 2


def test_immigrants_bring_new_families():
    world = _world(cells=5, immigrants=50)
    arrived = sum(world.step().immigrants for _ in range(200))
    assert arrived == 4
    assert world._next_id - 1 >= 5 + 4
