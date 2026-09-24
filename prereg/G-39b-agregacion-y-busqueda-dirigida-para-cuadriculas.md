# G-39b — agregación genérica sobre la cuadrícula y búsqueda dirigida por el objetivo para `at`

Fecha: 2026-09-23. Preregistro previo al código del motor. Segundo diseño para ARC. Base: `freeze-G-39` (`03288750`), que no superó su puerta: 0/200 en la reserva. Último estable: `estable-G-9`.

## Fallo y causa

G-39 resolvió transformaciones geométricas de `training` (13/400) y nada de `evaluation`. De las tareas de la reserva, 169 no tenían programa de celda y 31 no tenían programa de tamaño.

Exploración de desarrollo ya hecha, que se declara. Son prototipos fuera del motor; no se miró `evaluation`.
1. **Agregación sobre la búsqueda plana:** 16/400, frente a 17. Gana tareas no geométricas y baja los fallos de tamaño de 31 a 6, pero pierde geométricas porque cada primitiva nueva multiplica la búsqueda plana ([resultado](../results_v3/g39b_aggregation_prototype_training.json)).
2. **Agregación con inversión de `at` como raíz:** una expresión de fila sobrevive solo si en esa fila de la entrada aparece el color pedido para cada celda, y después solo se prueban las columnas compatibles. Resultado: **31/400**, con 13 respuestas erróneas porque el prototipo no detecta ambigüedad ([resultado](../results_v3/g39b_goal_prototype_training.json)).
   - `at` aparece en 27 soluciones;
   - los agregados, en unas 10;
   - el tamaño de componente y los vecinos, en 1 cada uno;
   - igualdad y condicional, en 0.

## Cambio (5.8), en `leobot/programs.py`

**1. Sustrato de agregación e iteración sobre la cuadrícula de contexto.** Es genérico según la Fase B; el 0 se toma como fondo.
- **Datos de toda la cuadrícula, como variables del programa:**
  - color más frecuente;
  - colores distintos de cero más y menos frecuentes (empates por el color menor);
  - número de colores distintos de cero;
  - fila superior, columna izquierda, alto y ancho del recuadro de las celdas distintas de cero.
- **Operaciones de celda:**
  - `nb(i,j)`: vecinos distintos de cero entre los 8;
  - `comp(i,j)`: tamaño del componente conexo (4 vecinos) del mismo color.
  - Fuera de la cuadrícula valen -1.
- Las mismas variables de toda la cuadrícula entran en los programas de alto y ancho de la salida.
- No se añaden igualdad ni condicional.

**2. Inversión de `at` en la búsqueda dirigida por el objetivo de `fit`** (`goal_join`, que hoy invierte solo la aritmética). En cada tamaño, antes de la enumeración de abajo arriba, se prueba `at(i,j)` como raíz:
- las expresiones de fila se podan solas;
- las de columna se buscan por su primer valor.

No cambia qué programas son soluciones, solo el orden y el costo de encontrarlas. Se conservan todas las soluciones mínimas del tamaño ganador, y la abstención por ambigüedad de G-39 sigue igual.

**Enmienda del mecanismo antes de congelar (2026-09-23), sin cambiar criterios ni presupuesto:** en el motor, el tope de 120 000 candidatos, que el prototipo no tenía, se agota en menos de 1 s en la enumeración de tamaño 5 (15 variables y 10 operaciones), antes de llegar a la inversión de tamaño 7. Por eso, antes de enumerar cada tamaño, la inversión de `at` se prueba para **todos los tamaños alcanzables con los niveles ya completos**. Cada división se prueba una sola vez y todo sigue podado.
- Si la enumeración encuentra después una solución más pequeña, esta reemplaza a las mayores. Se conservan todas las soluciones del menor tamaño hallado.
- Si el presupuesto se agota, el informe lo marca como búsqueda incompleta.
- Para búsquedas sin cuadrícula el comportamiento es el mismo que antes.
- No se sube ningún límite.

5.8:
- **Qué fallo resuelve:** representación insuficiente (tamaño dependiente del contenido, agregados) y dilución de la búsqueda plana.
- **Por qué no bastan los actuales:** G-39 da 0/200.
- **Qué lo distingue:** dos ablaciones con el mismo presupuesto, sin inversión y sin agregación.
- **Qué se elimina:** nada. Si falla, se retira también `at`, porque G-39 tampoco lo justificó.

## Datos, controles y puerta

Los mismos de G-39:
- ARC-AGI-1 `fchollet/ARC-AGI@39903044`;
- desarrollo: `training`;
- reserva: 200 tareas de `evaluation` con la semilla de los primeros 8 hexadecimales de `git rev-parse freeze-G-39b:leobot`. Puede solaparse con la reserva de G-39, que solo se usó para medir aquel diseño.

Presupuesto: 6 s por habilidad, tamaño 7, 120 000 candidatos, 2 procesos.

Controles:
- los de G-39: sin `at`, sin sondas de prueba, pares barajados, colores renombrados, reinicio y fresco;
- **sin inversión:** el mismo sustrato con búsqueda plana;
- **sin agregación:** la inversión sin los agregados.

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva | ≥ 3/200 |
| Precisión | ≥ 0,8 |
| Aciertos frente a la mejor ablación (sin inversión o sin agregación) | ≥ +2 |
| Sin `at` | ≤ 1 acierto |
| Pares barajados | 0 aciertos |
| Colores renombrados | ±1 del tratamiento |
| Reinicio | idéntico |
| Fresco | sin respuesta |
| Predicción p95 | ≤ 200 ms |
| Aprendizaje | ≤ 30 s de CPU por tarea |
| RSS | ≤ 1500 MiB por proceso |
| Regresión | sin fallos nuevos |
| Latencia fija | ≤ +20 % frente a `estable-G-9` |

Se informan la brecha con la referencia pública (98,5 %) y el costo por etapa. Si falla, se registra sin relajarla. Sería el segundo diseño intentado para ARC.

## En palabras fáciles de entender

El primer intento solo sabía mover casillas de sitio (espejos, giros, recortes) y no resolvió ningún rompecabezas de examen. Ahora Leobot podrá contar (qué color hay más, cuántos colores, qué tamaño tiene cada figura, dónde está el dibujo) y buscará la regla empezando desde la respuesta: si una casilla debe ser roja, solo mira las casillas rojas. En la práctica eso casi duplicó los aciertos. Falta ver si funciona en rompecabezas que nunca vio.
