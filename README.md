# Petri

Un cultivo de células en una grilla: comen, se dividen, mutan, compiten por espacio y mueren, y cuando
se encuentran deciden qué hacer pensando con el mismo modelo chico que usa nani en alfred (nani-4b en
el Ollama de la GPU, `127.0.0.1:11434`), sin cargar otro. Es un experimento, aparte de nani.

En alfred, con el modelo (deploy: `git push alfred main`, que construye la imagen):

```
ssh -t alfred 'cd ~/Projects/petri && docker compose run --rm petri run'
ssh -t alfred 'cd ~/Projects/petri && docker compose run --rm petri headless --ticks 2000'
```

En el PC, sin modelo o con un túnel al Ollama de alfred:

```
uv sync
uv run petri run                      # mente "rules": sin modelo, el grupo de control
uv run petri run --mind none --speed 5   # como la fase 1: los encuentros no hacen nada
uv run petri headless --ticks 5000    # sin visor: cifras cada 250 ticks
ssh -N -L 11435:127.0.0.1:11434 alfred &
uv run petri run --mind llm --ollama http://127.0.0.1:11435
uv run pytest
```

## El mundo (fase 1, sin modelo)

- Grilla toroidal de 32×32 con manchas fértiles: la comida vuelve a crecer según la fertilidad.
- Cada célula tiene energía, edad y un **genoma**: velocidad, visión, umbral para dividirse y fracción
  de energía que le pasa a la hija. Correr y ver lejos cuestan energía en cada tick.
- Va hacia la comida más rica que ve, come, gasta, se divide al llegar a su umbral (la hija hereda el
  genoma con mutaciones y el linaje) y muere sin energía o a los 500 ticks; lo que le quedaba vuelve
  al suelo como comida. Una célula por casilla.

## Los encuentros (fase 2)

Cuando dos células quedan vecinas, cada una decide por su cuenta: **compartir** (le regala el 20% de su
energía), **atacar** (intenta quitarle el 30%; gana más fácil la que tiene más energía, y si pierde
pierde el 10% de la suya), **ignorar** o **hablar**, y puede decirle una frase. Al pensar sabe:

- su **forma de ser**, del gen nuevo **confianza** (0 = muy desconfiada, 1 = muy confiada), que se
  hereda y muta como los demás: la selección dirá qué conviene;
- su energía y su hambre, la de la otra, si es de su familia, cuánto pasto hay cerca;
- lo último que le pasó (le regalaron, la atacaron, le dijeron algo): las 3 últimas cosas.

nani-4b contesta en ~0,75 s (JSON con esquema), así que no piensan todos los encuentros: una pareja
piensa si no lo hizo hace poco, si la mente da abasto (4 pedidos en cola) y si las dos van a vivir hasta
la respuesta; primero las de familias distintas. Mientras piensan se quedan quietas. Con 4 ticks por
segundo eso da ~80 decisiones por minuto, casi todas aplicadas. Los pedidos van de a uno: si le hablas a
nani mientras tanto, espera a lo más una respuesta corta; y si la GPU tiene cargado otro modelo, petri se
pausa en vez de sacarlo.

`--mind rules` decide sin modelo, con la confianza y el hambre, en todos los encuentros: es el grupo de
control (¿cambia algo que piense un modelo?) y la mente de los tests.

En el visor el fondo verde es la comida, el color del punto es el linaje y `○` es una célula con hambre;
abajo, lo último que decidieron. Misma semilla y mente `rules`, mismo cultivo.

## Fases

| Fase | | |
|---|---|---|
| 1. Mundo sin modelo: comida, energía, genoma, mutación, visor de terminal | ✅ | |
| 2. Encuentros con nani-4b, gen de confianza, memoria corta, compose en alfred | ✅ | |
| 3. Personalidad heredada al dividirse, huellas (mensajes en las casillas) | ⏳ | |
| 4. Historia en SQLite y gráficos de evolución | ⏳ | |
