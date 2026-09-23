# CMP-1 — Leobot frente a un subagente Claude con la misma información

Fecha: 2026-09-23. Preregistro previo a la corrida. Motor `estable-G-2:leobot` = `df4c9e96ae803c2fc25475d69be9b8e73013e621`, congelado.

## Pregunta

¿Es Leobot, hoy, inferior a un subagente de Claude cuando ambos reciben exactamente la misma información? El usuario pidió seguir trabajando mientras el subagente sea superior. Esta prueba mide esa condición; no es el experimento decisivo de la Fase G, que exige modelos frontier con versiones verificadas y evaluación externa.

## Baterías (fijas, elegidas antes de ver respuestas)

1. **MLQA español**: los 20 casos fijos del tablero AGI (`experiments/agi_board.py`, semilla `0x644c5552`, archivo con SHA fijado). Cada caso entrega el párrafo y la pregunta; se quitan las respuestas antes de dárselos al subagente.
2. **Sonda de lectura del repositorio**: las 4 frases y 4 preguntas de `experiments/user_text_probe.py`.

No se agregan tareas elegidas por ser favorables a ninguno de los dos. Son visibles y no son held-out: cuentan como diagnóstico (regla 5.2).

## Protocolo

- Leobot: bot fresco, la misma ruta del tablero (`evaluate_spanish`) y de la sonda; motor congelado y huella comprobada antes y después.
- Subagente: un subagente nuevo de Claude (herramienta Agent, `isolation: "worktree"`), sin contexto de la sesión. Recibe solo un archivo JSON con párrafos y preguntas (sin respuestas) y la instrucción de responder con un fragmento breve del texto, o «no sé» si no lo encuentra. No puede leer `results_v3/`, `leobot/` ni el tablero.
- Puntuación, igual para ambos: coincidencia exacta tras normalizar (`canonical` del tablero) con cualquiera de las respuestas de referencia, y F1 de palabras (máximo sobre referencias). Para la sonda, un revisor humano no está disponible: se reporta la respuesta de cada uno, y se cuenta como acierto solo si coincide con el contenido literal de la frase leída.
- Costo: CPU y pared de Leobot; tiempo de pared y fichas del subagente según los informa la herramienta.

## Criterio

El subagente es **superior** si supera a Leobot en exactitud MLQA por ≥3 casos de 20 o en F1 media por ≥0,15. Si es superior, el trabajo continúa según `MISION.md` (sección 9), atacando la causa general del fallo, no las 20 preguntas. Queda prohibido optimizar contra estos casos (5.2, 5.7).

## En palabras fáciles de entender

Le damos a Leobot y a un asistente de Claude los mismos textos y las mismas preguntas, sin ayudas. Contamos cuántas contesta bien cada uno. Si el asistente gana, seguimos mejorando a Leobot, pero no enseñándole esas respuestas: arreglando lo que le impide entender textos.
