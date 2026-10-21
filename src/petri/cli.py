"""Línea de comandos de Petri.

  petri run        el cultivo en vivo en la terminal (Ctrl+C para terminar)
  petri headless   sin visor, una línea de cifras cada tanto: para afinar el equilibrio
"""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.live import Live

from .viewer import Viewer
from .world import Rules, World

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _world(seed: int, size: int, cells: int) -> World:
    world = World(Rules(width=size, height=size), seed=seed)
    world.seed_cells(cells)
    return world


@app.command()
def run(
    seed: int = typer.Option(1, help="semilla: la misma semilla repite el mismo cultivo"),
    size: int = typer.Option(32, help="lado de la grilla"),
    cells: int = typer.Option(30, help="células al sembrar"),
    fps: float = typer.Option(10, help="cuadros por segundo"),
    ticks_per_frame: int = typer.Option(1, "--speed", help="ticks por cuadro"),
) -> None:
    """Siembra un cultivo y lo muestra en vivo."""
    world = _world(seed, size, cells)
    viewer = Viewer(world)
    viewer.record()
    try:
        with Live(viewer.render(), console=console, auto_refresh=False, screen=True) as live:
            while world.cells:
                for _ in range(ticks_per_frame):
                    world.step()
                    viewer.record()
                live.update(viewer.render(), refresh=True)
                time.sleep(1 / fps)
    except KeyboardInterrupt:
        pass
    _report(world)


@app.command()
def headless(
    seed: int = typer.Option(1),
    size: int = typer.Option(32),
    cells: int = typer.Option(30),
    ticks: int = typer.Option(5000, help="ticks como máximo (para antes si se extinguen)"),
    every: int = typer.Option(250, help="cada cuántos ticks imprime una línea"),
) -> None:
    """Corre el cultivo sin visor e imprime la evolución."""
    world = _world(seed, size, cells)
    encounters = births = 0
    peak = len(world.cells)
    while world.tick < ticks and world.cells:
        stats = world.step()
        encounters += stats.encounters
        births += stats.births
        peak = max(peak, len(world.cells))
        if world.tick % every == 0:
            s = world.summary()
            genes = " ".join(f"{k[:5]}={v:.2f}" for k, v in s["genes"].items())
            console.print(f"t={s['tick']:>5} pob={s['population']:>3} lin={s['lineages']:>2} "
                          f"gen={s['max_generation']:>3} enc/t={encounters / world.tick:.2f} {genes}")
    console.print(f"[bold]fin[/] t={world.tick} pob={len(world.cells)} pico={peak} nacimientos={births} "
                  f"encuentros/tick={encounters / max(1, world.tick):.2f}")


def _report(world: World) -> None:
    s = world.summary()
    status = "extinto" if not world.cells else f"{s['population']} células, {s['lineages']} linajes"
    console.print(f"tick {s['tick']}: {status}, generación máxima {s['max_generation']}")


def main() -> None:
    app()
