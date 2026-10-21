"""Visor de terminal: la grilla (fondo verde = comida, punto de color = célula por linaje), las cifras y
lo último que decidieron las células en sus encuentros."""

from __future__ import annotations

from collections import deque

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .society import Society
from .world import World

LINEAGE_COLORS = [
    "bright_red", "bright_yellow", "bright_cyan", "bright_magenta", "bright_white", "orange1",
    "deep_pink2", "dodger_blue1", "gold1", "plum1", "turquoise2", "salmon1",
]
SPARK = "▁▂▃▄▅▆▇█"
GENE_LABELS = {
    "speed": "velocidad", "vision": "visión", "repro_threshold": "umbral div.", "child_share": "% a la hija",
    "trust": "confianza",
}
ACTION_STYLES = {"compartir": "green", "atacar": "red", "ignorar": "dim", "hablar": "cyan"}


def lineage_color(lineage: int) -> str:
    return LINEAGE_COLORS[lineage % len(LINEAGE_COLORS)]


class Viewer:
    def __init__(self, world: World, society: Society | None = None, history: int = 60) -> None:
        self.world = world
        self.society = society
        self.population: deque[int] = deque(maxlen=history)
        self.encounters: deque[int] = deque(maxlen=history)

    def record(self) -> None:
        self.population.append(len(self.world.cells))
        self.encounters.append(self.world.last.encounters)

    def render(self) -> Group:
        parts = [self._grid(), self._stats()]
        if self.society:
            parts.append(self._log())
        return Group(*parts)

    def _grid(self) -> Panel:
        w = self.world
        text = Text()
        for y in range(w.rules.height):
            for x in range(w.rules.width):
                level = w.food[w.index(x, y)] / w.rules.food_max
                bg = f"rgb(0,{int(25 + 140 * level)},0)"
                cell = w.cell_at(x, y)
                if cell:
                    glyph = "●" if cell.energy >= cell.genome.repro_threshold / 2 else "○"  # ○ = con hambre
                    text.append(glyph, style=f"{lineage_color(cell.lineage)} on {bg}")
                    text.append(" ", style=f"on {bg}")
                else:
                    text.append("  ", style=f"on {bg}")
            text.append("\n")
        text.rstrip()
        return Panel(text, title=f"petri · semilla {w.seed} · tick {w.tick}", expand=False)

    def _stats(self) -> Table:
        s = self.world.summary()
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()
        table.add_row("población", f"{s['population']}  {_spark(self.population)}")
        table.add_row("encuentros/tick", f"{self.world.last.encounters}  {_spark(self.encounters)}")
        table.add_row("linajes · generación", f"{s['lineages']} · {s['max_generation']}")
        table.add_row("comida · energía", f"{s['food']:.0f} · {s['energy']:.0f}")
        genes = "  ".join(f"{GENE_LABELS[k]} {v:.2f}" for k, v in s["genes"].items())
        table.add_row("genes (media)", genes or "—")
        if soc := self.society:
            table.add_row("mente", soc.mind.status)
            total = sum(soc.actions.values()) or 1
            actions = "  ".join(f"[{ACTION_STYLES[a]}]{a} {100 * soc.actions[a] / total:.0f}%[/]"
                                for a in ACTION_STYLES)
            table.add_row("decisiones", f"{sum(soc.actions.values())}  {actions}")
            table.add_row("sin pensar · tarde", f"{soc.unthought} · {soc.late}")
        return table

    def _log(self) -> Panel:
        text = Text()
        for e in reversed(self.society.log):
            text.append(f"{e.tick:>5} ", style="dim")
            text.append(f"#{e.cell}", style=lineage_color(e.lineage))
            text.append(" → ")
            text.append(f"#{e.other}", style=lineage_color(e.other_lineage) if e.other_lineage >= 0 else "dim")
            text.append(f"  {e.action}", style=ACTION_STYLES.get(e.action, ""))
            if e.say:
                text.append(f"  «{e.say}»", style="italic")
            if e.outcome:
                text.append(f"  {e.outcome}", style="dim")
            text.append("\n")
        text.rstrip()
        return Panel(text or Text("todavía nadie ha decidido nada", style="dim"), title="encuentros", expand=False)


def _spark(values: deque[int]) -> str:
    if not values:
        return ""
    top = max(values) or 1
    return "".join(SPARK[min(len(SPARK) - 1, v * len(SPARK) // (top + 1))] for v in values)
