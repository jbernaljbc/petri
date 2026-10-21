"""Las mentes: quién decide qué hace una célula en un encuentro.

- RulesMind: sin modelo, con la confianza y el hambre. Es el grupo de control del experimento (¿cambia
  algo que piense un modelo?) y la que usan los tests: misma semilla, mismo cultivo. Con `latency`
  contesta de a una y tarda esos ticks en cada respuesta, como el modelo: así el control piensa en los
  mismos pocos encuentros y la comparación es justa.
- OllamaMind: nani-4b en el Ollama de nani en alfred. Un hilo aparte hace los pedidos de a uno, así nani
  espera a lo más una respuesta corta si le hablan mientras tanto. No manda num_ctx ni keep_alive (si
  no coinciden con los de nani, Ollama recargaría el modelo) y se pausa si la GPU tiene otro modelo
  cargado, para no sacarlo.
"""

from __future__ import annotations

import json
import queue
import random
import threading
import time
from collections import deque

import httpx

from .society import ACTIONS, Decision, Request


class RulesMind:
    def __init__(self, seed: int, latency: int = 0) -> None:
        self.rng = random.Random(seed)
        self.latency = latency  # ticks por respuesta; 0 = contesta al tiro y piensan todos los encuentros
        self.slow = latency > 0
        self.status = f"reglas, {latency} ticks por respuesta (como el modelo)" if self.slow else "reglas (sin modelo)"
        self._queue: deque[Request] = deque()
        self._out: list[Decision] = []
        self._clock = 0

    def submit(self, request: Request) -> None:
        if self.slow:
            self._queue.append(request)
        else:
            self._out.append(Decision(request, self._decide(request)))

    def poll(self) -> list[Decision]:
        """Se llama una vez por tick: con latencia, cada `latency` ticks sale una respuesta."""
        if self._queue:
            self._clock += 1
            if self._clock >= self.latency:
                self._clock = 0
                request = self._queue.popleft()
                self._out.append(Decision(request, self._decide(request)))
        out, self._out = self._out, []
        return out

    def backlog(self) -> int:
        return len(self._queue)

    def _decide(self, r: Request) -> str:
        hungry = r.energy < 0.4 * r.threshold
        if hungry and r.other_energy > r.energy and self.rng.random() > r.trust:
            return "atacar"
        if not hungry and self.rng.random() < r.trust * (0.6 if r.same_family else 0.25):
            return "compartir"
        return "ignorar"


SCHEMA = {
    "type": "object",
    "properties": {
        "accion": {"type": "string", "enum": list(ACTIONS)},
        "dice": {"type": "string"},
    },
    "required": ["accion", "dice"],
}

SYSTEM = """Eres una célula que vive en una placa de Petri, una grilla con pasto. Comes pasto para tener energía; si te quedas sin energía, mueres. Cuando juntas bastante energía te divides en dos y tu hija hereda tu forma de ser.

Acabas de encontrarte con otra célula. Decide qué haces:
- compartir: le regalas el 20% de tu energía.
- atacar: intentas quitarle el 30% de su energía. Ganas más fácil si tienes más energía que ella; si pierdes, pierdes el 10% de la tuya.
- ignorar: sigues tu camino.
- hablar: solo le dices algo.

Actúa según tu forma de ser y tu situación. Contesta solo con JSON: "accion" y "dice" (una frase corta en español, máximo 10 palabras, lo que le dices a la otra; puede ir vacía)."""


def describe_trust(trust: float) -> str:
    if trust < 0.2:
        return "muy desconfiada: crees que las demás solo quieren robarte"
    if trust < 0.4:
        return "desconfiada"
    if trust < 0.6:
        return "cautelosa"
    if trust < 0.8:
        return "confiada"
    return "muy confiada: crees que lo que das siempre vuelve"


def _amount(value: float) -> str:
    return "mucho" if value > 0.6 else "algo" if value > 0.25 else "poco"


def prompt(r: Request) -> list[dict]:
    hunger = "mucha" if r.energy < 0.4 * r.threshold else "algo" if r.energy < r.threshold else "nada"
    lines = [
        f"Tu forma de ser: {describe_trust(r.trust)}.",
        f"Tu energía: {r.energy:.0f} (te divides al llegar a {r.threshold:.0f}). Hambre: {hunger}.",
        f"La otra célula es {'de tu familia' if r.same_family else 'de otra familia'} y tiene {r.other_energy:.0f} de energía.",
        f"Pasto a tu alrededor: {_amount(r.food_near)}.",
    ]
    if r.memory:
        lines.append("Lo último que te pasó:\n" + "\n".join(f"- {m}" for m in r.memory))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


class OllamaMind:
    def __init__(self, url: str, model: str, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.status = "esperando"
        self.slow = True
        self.latencies: deque[float] = deque(maxlen=20)
        self.errors = 0
        self._client = httpx.Client(base_url=self.url, timeout=timeout)
        self._in: queue.Queue[Request | None] = queue.Queue()
        self._out: queue.Queue[Decision] = queue.Queue()
        self._working = False
        self._checked = 0.0
        self._thread = threading.Thread(target=self._loop, name="petri-mind", daemon=True)
        self._thread.start()

    def submit(self, request: Request) -> None:
        self._in.put(request)

    def poll(self) -> list[Decision]:
        out = []
        while True:
            try:
                out.append(self._out.get_nowait())
            except queue.Empty:
                return out

    def backlog(self) -> int:
        return self._in.qsize() + self._working

    def close(self) -> None:
        self._in.put(None)

    def mean_latency(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def _loop(self) -> None:
        while (request := self._in.get()) is not None:
            self._working = True
            try:
                self._wait_for_gpu()
                self._out.put(self._think(request))
            finally:
                self._working = False

    def _wait_for_gpu(self) -> None:
        """Si la GPU tiene cargado otro modelo, no se lo quita: espera a que se desocupe o vuelva el suyo."""
        while time.monotonic() - self._checked > 5:
            try:
                loaded = [m.get("name", "") for m in self._client.get("/api/ps").json().get("models", [])]
            except (httpx.HTTPError, ValueError) as e:
                self.status = f"sin Ollama: {type(e).__name__}"
                return  # el pedido mismo va a fallar y quedará como error
            if not loaded or any(name.split(":")[0] == self.model.split(":")[0] for name in loaded):
                self._checked = time.monotonic()
                return
            self.status = f"en pausa: la GPU tiene {', '.join(loaded)}"
            time.sleep(5)

    def _think(self, request: Request) -> Decision:
        start = time.monotonic()
        try:
            response = self._client.post("/api/chat", json={
                "model": self.model,
                "messages": prompt(request),
                "format": SCHEMA,
                "stream": False,
                "options": {"temperature": 0.8, "num_predict": 60},
            })
            response.raise_for_status()
            answer = _parse(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            self.errors += 1
            self.status = f"error: {type(e).__name__}"
            time.sleep(min(10, self.errors))
            return Decision(request, "ignorar", error=type(e).__name__)
        seconds = time.monotonic() - start
        self.latencies.append(seconds)
        self.errors = 0
        self.status = f"{self.model} · {self.mean_latency():.2f} s por decisión"
        return Decision(request, answer["accion"], answer["dice"], seconds)


def _parse(content: str) -> dict[str, str]:
    data = json.loads(content)
    action = data.get("accion", "ignorar")
    return {
        "accion": action if action in ACTIONS else "ignorar",
        "dice": " ".join(str(data.get("dice", "")).split()[:12]),
    }
