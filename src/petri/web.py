"""Live dashboard: the simulation runs here and a small web page watches it.

Standard library only: a threaded HTTP server with two routes, `/` (the page, static/index.html) and
`/events` (Server-Sent Events). The simulation loop publishes a snapshot after every tick; each open page
gets the newest one at most `fps` times per second, plus the whole history when it connects, so it can
be opened (or reloaded) at any point of a run. It listens on 127.0.0.1 only: from the PC, open it
through an ssh tunnel.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

from .society import Society
from .world import World

HISTORY_EVERY = 5  # ticks between history points
HISTORY_MAX = 4000  # points kept (then every other one is dropped)


class Hub:
    """The latest snapshot and the history, shared between the simulation and the page connections."""

    def __init__(self) -> None:
        self.changed = threading.Condition()
        self.version = 0
        self.snapshot: dict = {}
        self.history: list[dict] = []
        self.every = HISTORY_EVERY

    def publish(self, world: World, society: Society | None, meta: dict) -> None:
        snapshot = _snapshot(world, society, meta)
        with self.changed:
            snapshot["every"] = self.every
            if world.tick % self.every == 0:
                self.history.append(snapshot["point"])
                if len(self.history) > HISTORY_MAX:
                    self.history = self.history[::2]
                    self.every *= 2
            self.snapshot = snapshot
            self.version += 1
            self.changed.notify_all()


def _snapshot(world: World, society: Society | None, meta: dict) -> dict:
    s = world.summary()
    cells = [[c.x, c.y, c.lineage, int(c.energy < c.genome.repro_threshold / 2), round(c.genome.trust, 2)]
             for c in world.cells.values()]
    families: dict[int, list[float]] = {}
    for c in world.cells.values():
        families.setdefault(c.lineage, []).append(c.genome.trust)
    actions = dict(society.actions) if society else {}
    point = {
        "t": world.tick,
        "pop": s["population"],
        "lin": s["lineages"],
        "trust": round(s["genes"].get("trust", 0.0), 3),
        "actions": actions,
    }
    log = []
    if society:
        log = [{"t": e.tick, "a": e.cell, "al": e.lineage, "b": e.other, "bl": e.other_lineage,
                "action": e.action, "say": e.say, "outcome": e.outcome} for e in society.log]
    return {
        **meta,
        "tick": world.tick,
        "width": world.rules.width,
        "height": world.rules.height,
        "food": [round(f / world.rules.food_max * 9) for f in world.food],
        "cells": cells,
        "summary": {**s, "genes": {k: round(v, 3) for k, v in s["genes"].items()}},
        "families": sorted(([lin, len(t), round(sum(t) / len(t), 2)] for lin, t in families.items()),
                           key=lambda f: -f[1]),
        "mind": society.mind.status if society else "none",
        "thoughts": society.thoughts if society else 0,
        "unthought": society.unthought if society else 0,
        "late": society.late if society else 0,
        "log": log,
        "point": point,
    }


def serve(hub: Hub, host: str, port: int, fps: float) -> ThreadingHTTPServer:
    page = files("petri").joinpath("static/index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet: the terminal shows the run, not every request
            pass

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", page)
            elif self.path == "/events":
                self._events()
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code: int, kind: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            seen = -1
            try:
                with hub.changed:
                    first = {"history": list(hub.history)}
                self._emit(first)
                while True:
                    with hub.changed:
                        hub.changed.wait_for(lambda seen=seen: hub.version != seen, timeout=15)
                        snapshot, seen = hub.snapshot, hub.version
                    if snapshot:
                        self._emit(snapshot)
                    time.sleep(1 / fps)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _emit(self, data: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(data, separators=(",", ":")).encode() + b"\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="petri-web", daemon=True).start()
    return server
