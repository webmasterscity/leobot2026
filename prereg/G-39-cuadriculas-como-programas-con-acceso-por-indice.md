# G-39 — aprender transformaciones de cuadrículas con la síntesis de programas existente

Fecha: 2026-09-23. Preregistro previo al código del motor. Base: `estable-G-9` (`b5d03377`).

## Fallo y causa

El tablero AGI exige medir el aprendizaje con pocos ejemplos (ARC-AGI), y hoy no hay medición.
- **Referencia pública verificada:** Claude Opus 5.5, esfuerzo alto, 98,5 % en ARC-AGI-1 y 93,3 % en ARC-AGI-2, en los conjuntos semiprivados ([ARC Prize](https://arcprize.org/results/anthropic-claude-opus-5-5), consultado el 2026-09-23).
- **Leobot:** 0 %. No tiene cómo recibir cuadrículas. Su síntesis de programas solo trabaja con tuplas de enteros.

Exploración ya hecha, que se declara: un [prototipo fuera del motor](../experiments/g39_grid_prototype.py) resolvió 17 de las 400 tareas de entrenamiento de ARC-AGI-1 ([resultado](../results_v3/g39_grid_prototype_training.json)).
- Usa aritmética, acceso por índice a la entrada, igualdad y condicional.
- Ninguna solución usó igualdad ni condicional.
- En 11 tareas eligió un programa que encajaba con los ejemplos pero fallaba en la prueba: tomaba la primera solución sin detectar la ambigüedad.
- No se miró ninguna tarea de `evaluation`.

## Cambio (5.8)

Una sola operación nueva en el DSL de `leobot/programs.py`: **`at(i, j)`, el acceso por índice a la cuadrícula de contexto** (vale -1 fuera de rango). Es sustrato genérico (Fase B: «acceso por índice»), no una operación de ARC.
- No se añade rotación, espejo, objeto, simetría ni repetición.
- No se añaden igualdad ni condicional.

Nueva interfaz de `ProgramLearner`:

**`add_grid_example(habilidad, entrada, salida)`** guarda un par de ejemplo.

**`fit_grid(habilidad, entradas_de_prueba)`** aprende con la búsqueda existente (`fit`, de abajo arriba con equivalencia observacional):
- **Alto y ancho de la salida:** cada uno es una habilidad entera sobre (alto, ancho) de la entrada.
- **Color de cada celda:** es una habilidad entera sobre (fila, columna, alto, ancho), evaluada con la cuadrícula de entrada de su ejemplo como contexto.
- **Sondas:** las entradas de prueba, que son información dada y no la respuesta, se usan como puntos sin etiqueta, igual que las sondas actuales. Así, dos programas que coinciden en los ejemplos pero difieren en la prueba no se funden en uno.

**`predict_grid(habilidad, entrada)`** evalúa todas las soluciones mínimas conservadas:
- si todas coinciden en todas las celdas, responde;
- si difieren, responde `ambiguous` y se abstiene, en vez de elegir en silencio (Fase A).

5.8:
- **Qué fallo resuelve:** no hay forma de aprender transformaciones de estructuras nuevas desde pocos ejemplos.
- **Por qué no bastan los actuales:** el DSL no tiene acceso a una estructura de contexto.
- **Qué lo distingue:** la ablación sin `at`.
- **Qué se elimina:** el prototipo externo queda solo como registro.

## Datos

- Fuente: ARC-AGI-1 público, `fchollet/ARC-AGI@399030444e0ab0cc8b4e199870fb20b863846f34`.
- Desarrollo: las 400 tareas de `training`.
- Reserva: 200 tareas de `evaluation`, elegidas con la semilla de los primeros 8 hexadecimales de `git rev-parse freeze-G-39:leobot`. No se miran antes de congelar.
- Una tarea cuenta como acierto si todas sus salidas de prueba son exactas.

## Controles

- **Ablación:** sin `at`, con el mismo presupuesto.
- **Sin sondas:** el mismo motor sin las entradas de prueba como puntos sin etiqueta. Mide cuántos errores evita la detección de ambigüedad.
- **Pares barajados:** las salidas de entrenamiento se reparten entre entradas de otras tareas.
- **Renombrado total de colores:** una permutación de los colores 1–9, igual en entrenamiento y prueba. El 0 queda fijo, porque el fondo sale del borde (-1) y de las constantes.
- **Reinicio:** guardar, cargar y predecir de nuevo.
- **Fresco:** sin ejemplos, no responde.

## Presupuesto

El actual de `ProgramLearner`: tamaño 7 y 120 000 candidatos. Tiempo por habilidad: 6 s.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva | ≥ 3/200 |
| Precisión (aciertos entre respuestas) | ≥ 0,8 |
| Ablación sin `at` | ≤ 1 acierto |
| Pares barajados | 0 aciertos |
| Renombrado de colores | aciertos a ±1 del tratamiento |
| Reinicio | predicciones idénticas |
| Fresco | sin respuesta |
| Predicción ya aprendida, p95 | ≤ 200 ms por tarea |
| Aprendizaje | ≤ 20 s de CPU por tarea |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-9` | sin empeorar más de un 20 % |

Se informan además los aciertos con hashseed 0 y 1, las abstenciones, los errores y el costo por etapa. Se informa la brecha con la referencia pública, 98,5 %; no se afirma superioridad.

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

En ARC hay rompecabezas de cuadrículas de colores: se ven dos o tres ejemplos de cómo cambia una cuadrícula y hay que adivinar el cambio en una nueva. Leobot ni siquiera podía mirarlos. Ahora podrá leer una casilla por su posición y, con las cuentas que ya sabe hacer, buscar la regla que explica los ejemplos. Si encuentra dos reglas que funcionan con los ejemplos pero dan resultados distintos en la prueba, dirá que no está seguro en vez de adivinar.
