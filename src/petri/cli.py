"""Petri's command line.

  petri run        the culture live in the terminal (Ctrl+C to stop)
  petri headless   no viewer, a line of numbers every so often: for tuning the balance
  petri serve      the culture with a live web dashboard (127.0.0.1:8780)

--mind picks who decides in encounters: llm (nani-4b), rules (no model, the control group) or none
(encounters do nothing). With --latency, rules answers as slowly as the model (in ticks): that's the
fair control group to compare against llm.
"""

from __future__ import annotations

import time
from enum import StrEnum

import typer
from rich.console import Console
from rich.live import Live

from .mind import OllamaMind, RulesMind
from .society import Society
from .viewer import ACTIONS, Viewer
from .web import Hub
from .web import serve as serve_web
from .world import Rules, World

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console(soft_wrap=True)  # headless lines stay whole when the output isn't a terminal


class MindKind(StrEnum):
    llm = "llm"
    rules = "rules"
    none = "none"


MIND = typer.Option(MindKind.rules, envvar="PETRI_MIND", help="who decides in encounters")
OLLAMA = typer.Option("http://127.0.0.1:11434", envvar="PETRI_OLLAMA", help="nani's Ollama")
MODEL = typer.Option("nani-4b", envvar="PETRI_MODEL")
LATENCY = typer.Option(0, help="rules: ticks per answer, one at a time (3 ≈ nani-4b at 4 ticks/s)")
IMMIGRANTS = typer.Option(300, help="every how many ticks a new family arrives (0 = never)")


def _build(
    seed: int, size: int, cells: int, immigrants: int, mind: MindKind, latency: int, ollama: str, model: str
) -> tuple[World, Society | None]:
    world = World(Rules(width=size, height=size, immigrants=immigrants), seed=seed)
    world.seed_cells(cells)
    if mind is MindKind.none:
        return world, None
    brain = OllamaMind(ollama, model) if mind is MindKind.llm else RulesMind(seed, latency)
    return world, Society(world, brain)


def _step(world: World, society: Society | None) -> None:
    world.step()
    if society:
        society.after_step()


@app.command()
def run(
    seed: int = typer.Option(1, help="seed: the same seed repeats the same world"),
    size: int = typer.Option(32, help="side of the grid"),
    cells: int = typer.Option(30, help="cells to seed"),
    fps: float = typer.Option(None, help="frames per second (10; 4 with llm, so they get to think)"),
    ticks_per_frame: int = typer.Option(1, "--speed", help="ticks per frame"),
    immigrants: int = IMMIGRANTS,
    mind: MindKind = MIND,
    latency: int = LATENCY,
    ollama: str = OLLAMA,
    model: str = MODEL,
) -> None:
    """Seeds a culture and shows it live."""
    world, society = _build(seed, size, cells, immigrants, mind, latency, ollama, model)
    fps = fps or (4 if mind is MindKind.llm else 10)
    viewer = Viewer(world, society)
    viewer.record()
    try:
        with Live(viewer.render(), console=console, auto_refresh=False, screen=True) as live:
            while world.cells:
                for _ in range(ticks_per_frame):
                    _step(world, society)
                    viewer.record()
                live.update(viewer.render(), refresh=True)
                time.sleep(1 / fps)
    except KeyboardInterrupt:
        pass
    _report(world, society)


@app.command()
def headless(
    seed: int = typer.Option(1),
    size: int = typer.Option(32),
    cells: int = typer.Option(30),
    ticks: int = typer.Option(5000, help="maximum ticks (stops earlier if they go extinct)"),
    every: int = typer.Option(250, help="print a line every this many ticks"),
    tps: float = typer.Option(None, help="ticks per second (unlimited; 4 with llm)"),
    immigrants: int = IMMIGRANTS,
    mind: MindKind = MIND,
    latency: int = LATENCY,
    ollama: str = OLLAMA,
    model: str = MODEL,
) -> None:
    """Runs the culture without a viewer and prints how it evolves."""
    world, society = _build(seed, size, cells, immigrants, mind, latency, ollama, model)
    tps = tps or (4 if mind is MindKind.llm else 0)
    encounters = births = 0
    peak = len(world.cells)
    try:
        while world.tick < ticks and world.cells:
            _step(world, society)
            encounters += world.last.encounters
            births += world.last.births
            peak = max(peak, len(world.cells))
            if world.tick % every == 0:
                s = world.summary()
                genes = " ".join(f"{k[:5]}={v:.2f}" for k, v in s["genes"].items())
                console.print(f"t={s['tick']:>5} pop={s['population']:>3} lin={s['lineages']:>2} "
                              f"gen={s['max_generation']:>3} {genes} {_actions(society)}")
            if tps:
                time.sleep(1 / tps)
    except KeyboardInterrupt:
        pass
    genes = " ".join(f"{k[:5]}={v:.2f}" for k, v in world.summary()["genes"].items())
    console.print(f"[bold]end[/] t={world.tick} pop={len(world.cells)} peak={peak} births={births} "
                  f"encounters/tick={encounters / max(1, world.tick):.2f} {genes} {_actions(society)}")


@app.command()
def serve(
    seed: int = typer.Option(1),
    size: int = typer.Option(32),
    cells: int = typer.Option(30),
    ticks: int = typer.Option(0, help="stop after this many ticks (0 = until Ctrl+C or extinction)"),
    tps: float = typer.Option(None, help="ticks per second (4; 10 without llm)"),
    host: str = typer.Option("127.0.0.1", help="only localhost: open it through an ssh tunnel"),
    port: int = typer.Option(8780),
    fps: float = typer.Option(4, help="dashboard updates per second"),
    immigrants: int = IMMIGRANTS,
    mind: MindKind = MIND,
    latency: int = LATENCY,
    ollama: str = OLLAMA,
    model: str = MODEL,
) -> None:
    """Runs the culture with a live web dashboard."""
    world, society = _build(seed, size, cells, immigrants, mind, latency, ollama, model)
    tps = tps or (4 if mind is MindKind.llm else 10)
    hub = Hub()
    meta = {"seed": seed, "tps": tps}
    hub.publish(world, society, meta)
    serve_web(hub, host, port, fps)
    console.print(f"petri · seed {seed} · {mind} mind · dashboard at http://{host}:{port}")
    try:
        while world.cells and (not ticks or world.tick < ticks):
            start = time.monotonic()
            _step(world, society)
            hub.publish(world, society, meta)
            if world.tick % 500 == 0:
                s = world.summary()
                console.print(f"t={s['tick']:>5} pop={s['population']:>3} lin={s['lineages']:>2} "
                              f"trust={s['genes'].get('trust', 0):.2f} {_actions(society)}")
            time.sleep(max(0.0, 1 / tps - (time.monotonic() - start)))
    except KeyboardInterrupt:
        pass
    _report(world, society)


def _actions(society: Society | None) -> str:
    if not society:
        return ""
    total = sum(society.actions.values()) or 1
    shares = " ".join(f"{ACTIONS[a][0]}={100 * society.actions[a] / total:.0f}%" for a in ACTIONS)
    return f"decisions={sum(society.actions.values())} {shares}"


def _report(world: World, society: Society | None) -> None:
    s = world.summary()
    status = "extinct" if not world.cells else f"{s['population']} cells, {s['lineages']} lineages"
    console.print(f"tick {s['tick']}: {status}, max generation {s['max_generation']} {_actions(society)}")


def main() -> None:
    app()
