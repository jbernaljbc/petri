from petri.genome import Genome
from petri.mind import RulesMind, _parse, prompt
from petri.society import Decision, Request, Society
from petri.world import Rules, World


class SlowMind:
    """Una mente que no contesta hasta que el test lo dice, para ver qué pasa con las respuestas tardías."""

    status = "lenta"

    def __init__(self) -> None:
        self.queue: list[Request] = []
        self.answers: list[Decision] = []

    def submit(self, request: Request) -> None:
        self.queue.append(request)

    def poll(self) -> list[Decision]:
        out, self.answers = self.answers, []
        return out

    def backlog(self) -> int:
        return len(self.queue)


def _pair(lineage_b: int | None = None) -> tuple[World, int, int]:
    world = World(Rules(width=10, height=10), seed=1)
    a = world._add(2, 2, 50.0, Genome())
    b = world._add(3, 2, 30.0, Genome())
    a.lineage, b.lineage = a.id, lineage_b if lineage_b is not None else b.id
    world.encounters = world._new_encounters()
    return world, a.id, b.id


def test_each_cell_thinks_once_per_encounter():
    world, a, b = _pair()
    mind = SlowMind()
    society = Society(world, mind)
    society.after_step()
    assert sorted((r.cell, r.other) for r in mind.queue) == [(a, b), (b, a)]
    assert world.frozen == {a, b}  # se detienen a pensar
    society.after_step()  # sigue la misma lista de encuentros, pero las dos están esperando respuesta
    assert len(mind.queue) == 2
    mind.answers = [Decision(mind.queue[0], "ignorar")]
    society.after_step()
    assert world.frozen == {a, b}  # falta la respuesta de la otra
    mind.answers = [Decision(mind.queue[1], "ignorar")]
    society.after_step()
    assert world.frozen == set()


def test_backlog_limit_leaves_encounters_unthought():
    world, a, b = _pair()
    mind = SlowMind()
    mind.queue = [None] * 3  # la mente ya está ocupada
    society = Society(world, mind)
    society.after_step()
    assert len(mind.queue) == 3
    assert society.unthought == 1


def test_share_moves_energy_and_both_remember():
    world, a, b = _pair()
    society = Society(world, SlowMind())
    request = society._request(a, b)
    society._apply(Decision(request, "compartir", "toma"))
    assert world.cells[a].energy == 40.0
    assert world.cells[b].energy == 40.0
    assert "te regaló 10" in world.cells[b].memory[0]
    assert "te dijo «toma»" in world.cells[b].memory[1]


def test_attack_either_steals_or_backfires():
    world, a, b = _pair()
    society = Society(world, SlowMind())
    society._apply(Decision(society._request(a, b), "atacar"))
    total = world.cells[a].energy + world.cells[b].energy
    assert total < 80.0  # el ataque cuesta algo, gane o pierda
    assert society.log[-1].outcome.startswith(("gana", "pierde"))


def test_late_decision_does_nothing_if_they_moved_apart():
    world, a, b = _pair()
    society = Society(world, SlowMind())
    request = society._request(a, b)
    cell = world.cells[b]
    del world._at[(cell.x, cell.y)]
    cell.x = 8
    world._at[(cell.x, cell.y)] = cell.id
    society._apply(Decision(request, "compartir"))
    assert world.cells[a].energy == 50.0
    assert society.late == 1


def test_rules_mind_is_reproducible():
    def run() -> dict:
        world = World(Rules(width=20, height=20), seed=4)
        world.seed_cells(40)
        society = Society(world, RulesMind(4))
        for _ in range(400):
            world.step()
            society.after_step()
        return {**world.summary(), "actions": dict(society.actions)}

    first = run()
    assert first == run()
    assert sum(first["actions"].values()) > 0


def test_prompt_tells_the_cell_who_it_is():
    world, a, b = _pair(lineage_b=1)
    society = Society(world, SlowMind())
    request = society._request(a, b)
    text = prompt(request)[1]["content"]
    assert "cautelosa" in text and "de tu familia" in text


def test_parse_keeps_known_actions_and_short_phrases():
    assert _parse('{"accion": "volar", "dice": "hola"}') == {"accion": "ignorar", "dice": "hola"}
    long = " ".join(["palabra"] * 30)
    assert len(_parse(f'{{"accion": "hablar", "dice": "{long}"}}')["dice"].split()) == 12
