"""Línea de comandos de Petri.

  petri run        el cultivo en vivo en la terminal (Ctrl+C para terminar)
  petri headless   sin visor, una línea de cifras cada tanto: para afinar el equilibrio

--mind elige quién decide en los encuentros: llm (nani-4b), rules (sin modelo, el grupo de control) o
none (los encuentros no hacen nada, como en la fase 1).
"""

from __future__ import annotations

import time
from enum import StrEnum

import typer
from rich.console import Console
from rich.live import Live

from .mind import OllamaMind, RulesMind
from .society import Society
from .viewer import Viewer
from .world import Rules, World

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


class MindKind(StrEnum):
    llm = "llm"
    rules = "rules"
    none = "none"


MIND = typer.Option(MindKind.rules, envvar="PETRI_MIND", help="quién decide en los encuentros")
OLLAMA = typer.Option("http://127.0.0.1:11434", envvar="PETRI_OLLAMA", help="Ollama de nani")
MODEL = typer.Option("nani-4b", envvar="PETRI_MODEL")


def _build(seed: int, size: int, cells: int, mind: MindKind, ollama: str, model: str) -> tuple[World, Society | None]:
    world = World(Rules(width=size, height=size), seed=seed)
    world.seed_cells(cells)
    if mind is MindKind.none:
        return world, None
    brain = OllamaMind(ollama, model) if mind is MindKind.llm else RulesMind(seed)
    return world, Society(world, brain)


def _step(world: World, society: Society | None) -> None:
    world.step()
    if society:
        society.after_step()


@app.command()
def run(
    seed: int = typer.Option(1, help="semilla: la misma semilla repite el mismo mundo"),
    size: int = typer.Option(32, help="lado de la grilla"),
    cells: int = typer.Option(30, help="células al sembrar"),
    fps: float = typer.Option(None, help="cuadros por segundo (10; 4 con llm, para que alcancen a pensar)"),
    ticks_per_frame: int = typer.Option(1, "--speed", help="ticks por cuadro"),
    mind: MindKind = MIND,
    ollama: str = OLLAMA,
    model: str = MODEL,
) -> None:
    """Siembra un cultivo y lo muestra en vivo."""
    world, society = _build(seed, size, cells, mind, ollama, model)
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
    ticks: int = typer.Option(5000, help="ticks como máximo (para antes si se extinguen)"),
    every: int = typer.Option(250, help="cada cuántos ticks imprime una línea"),
    tps: float = typer.Option(None, help="ticks por segundo (sin límite; 4 con llm)"),
    mind: MindKind = MIND,
    ollama: str = OLLAMA,
    model: str = MODEL,
) -> None:
    """Corre el cultivo sin visor e imprime la evolución."""
    world, society = _build(seed, size, cells, mind, ollama, model)
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
                console.print(f"t={s['tick']:>5} pob={s['population']:>3} lin={s['lineages']:>2} "
                              f"gen={s['max_generation']:>3} {genes} {_actions(society)}")
            if tps:
                time.sleep(1 / tps)
    except KeyboardInterrupt:
        pass
    console.print(f"[bold]fin[/] t={world.tick} pob={len(world.cells)} pico={peak} nacimientos={births} "
                  f"encuentros/tick={encounters / max(1, world.tick):.2f} {_actions(society)}")


def _actions(society: Society | None) -> str:
    if not society:
        return ""
    total = sum(society.actions.values()) or 1
    shares = " ".join(f"{a[:4]}={100 * n / total:.0f}%" for a, n in sorted(society.actions.items()))
    return f"decisiones={sum(society.actions.values())} {shares}"


def _report(world: World, society: Society | None) -> None:
    s = world.summary()
    status = "extinto" if not world.cells else f"{s['population']} células, {s['lineages']} linajes"
    console.print(f"tick {s['tick']}: {status}, generación máxima {s['max_generation']} {_actions(society)}")


def main() -> None:
    app()
