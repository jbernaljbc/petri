# Petri

Un cultivo de células en una grilla: comen, se dividen, mutan, compiten por espacio y mueren. Es un
experimento, aparte de nani: más adelante las células pensarán en sus encuentros con el mismo modelo
chico que usa nani en alfred (nani-4b en el Ollama de la GPU, `127.0.0.1:11434`), sin cargar otro.

```
uv sync
uv run petri run                 # en vivo en la terminal (Ctrl+C para terminar)
uv run petri run --seed 3 --speed 5
uv run petri headless --ticks 5000   # sin visor: cifras cada 250 ticks, para afinar el equilibrio
uv run pytest
```

## El mundo (fase 1, sin modelo)

- Grilla toroidal de 32×32 con manchas fértiles: la comida vuelve a crecer según la fertilidad.
- Cada célula tiene energía, edad y un **genoma**: velocidad, visión, umbral para dividirse y fracción
  de energía que le pasa a la hija. Correr y ver lejos cuestan energía en cada tick.
- Va hacia la comida más rica que ve, come, gasta, se divide al llegar a su umbral (la hija hereda el
  genoma con mutaciones y el linaje) y muere sin energía o a los 500 ticks; lo que le quedaba vuelve
  al suelo como comida. Una célula por casilla.
- Los **encuentros** (dos células que pasan a ser vecinas) se cuentan: en la fase 2 son el momento en
  que piensan con el modelo.

En el visor el fondo verde es la comida, el color del punto es el linaje y `○` es una célula con hambre.
Misma semilla, mismo cultivo.

## Fases

| Fase | | |
|---|---|---|
| 1. Mundo sin modelo: comida, energía, genoma, mutación, visor de terminal | ✅ | |
| 2. Encuentros con nani-4b: cola con prioridad para nani, respuestas JSON con esquema | ⏳ | compose en alfred |
| 3. Personalidad heredada al dividirse, huellas (mensajes en las casillas) | ⏳ | |
| 4. Historia en SQLite y gráficos de evolución | ⏳ | |
