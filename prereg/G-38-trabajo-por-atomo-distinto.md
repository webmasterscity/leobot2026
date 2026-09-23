# G-38 — que el demostrador trabaje por hecho distinto, no por cada vez que se afirmó

Fecha: 2026-09-23. Preregistro previo al cambio del motor. Base: `estable-G-7` (`49c45e06`).

## Fallo medido

La auditoría 5.10 de G-37 lo señaló, y la [línea base](../results_v3/g38/baseline_estable-G-7_hashseed0.json) lo amplía (5 repeticiones, `experiments.g38_distinct_atoms`):

| Memoria adversa | Consulta | `estable-G-7` en memoria | `estable-G-7` en disco |
|---|---|---|---|
| `padre(a,b)` desde 100 000 fuentes | `padre(a,b)`, `!padre(a,b)`, `padre(a,?x)`, `padre(?x,b)` | `incomplete`, 745–857 ms | `incomplete`, 2,2–5,3 s |
| `padre(a,b)` y `padre(b,c)` desde 50 000 fuentes cada uno, más la regla abuelo | `abuelo(a,c)`, `abuelo(a,?z)` | `incomplete`, 800–848 ms | `incomplete`, 2,2–3,8 s |
| 50 000 negados en cada posición | `padre(a,b)`, `!padre(a,b)` | 0,06–0,10 ms | 46–47 ms |

Un hecho afirmado explícitamente no debería quedar «incompleto», y el disco supera el tope absoluto de 1 s (regla 5.6).

## Causa

1. **Una prueba por afirmación.** El demostrador recorre cada hecho que coincide, aunque 100 000 hechos digan lo mismo desde fuentes distintas. Solo sobrevive la primera prueba de cada átomo: todas tienen el mismo rango y `_put` exige mejora estricta. El resto es trabajo sin efecto que agota el presupuesto.
2. **Los hechos se vuelven a leer en cada ronda.** El punto fijo repite la lectura de hechos de cada consulta en todas las rondas, aunque los hechos no cambian durante una consulta.
3. **El disco no tiene índice por átomo exacto.** Solo tiene índices por (predicado, un argumento).

## Cambio (5.8)

1. **Memoria.** Los índices secundarios (por predicado y por argumento) guardan átomos distintos, no identificadores de hechos. Los hechos de cada átomo quedan en `atom_facts`, en orden de identificador.
   - `matches` conserva exactamente su resultado y su orden: todos los hechos, por identificador.
   - Nuevo `distinct_matches(patrón)`: el hecho más antiguo de cada átomo distinto, en orden de ese identificador.
2. **Disco.** Índice compuesto (predicado, a0…a7) para búsquedas por átomo exacto, y `distinct_matches` con el menor identificador por átomo.
3. **Demostrador.** Lee los hechos de cada consulta una sola vez por consulta (no en cada ronda) y con `distinct_matches`. Las reglas siguen evaluándose por rondas.

Ninguna respuesta debe cambiar: el hecho elegido para cada átomo es el mismo que elegía antes, porque era el primero en orden de identificador.

5.8:
- **Qué fallo resuelve:** respuestas incompletas o lentas sobre hechos afirmados por muchas fuentes.
- **Por qué no bastan los actuales:** el índice de G-37 solo resuelve `contains`; el demostrador sigue recorriendo afirmaciones.
- **Qué lo distingue:** los casos adversos más la prueba diferencial contra `estable-G-7`.
- **Qué se elimina:** los índices por identificador de hecho y la relectura de hechos por ronda.
- **No se sube ningún presupuesto** (regla 8).

## Pruebas y puerta

**Prueba focal nueva** (`tests/test_distinct_atoms.py`):
- `padre(a,b)` desde 2 000 fuentes, con el presupuesto de trabajo del motor reducido a 1 000, sigue siendo `supported` y completo;
- `distinct_matches` y `matches` después de añadir, retirar, guardar y cargar.

**Prueba diferencial** (`experiments/g38_differential.py`) contra `estable-G-7` cargado en un proceso aparte:
- 300 bases al azar con duplicados de fuente, negaciones, reglas (incluidas recursivas), altas y bajas;
- por base se comparan `matches` (contenido y orden), `contains` y `Engine.answer` de 20 consultas: estado, y átomo, tipo, identificador, hipótesis y disputa de cada prueba;
- los casos en que `estable-G-7` quedó incompleto se informan aparte.

| Criterio | Umbral |
|---|---|
| Casos adversos en memoria | todos completos, estado correcto, p95 ≤ 10 ms |
| Casos adversos en disco, consultas concretas | completos, estado correcto, p95 ≤ 10 ms |
| Casos adversos en disco, consultas con variables | completos, estado correcto, p95 ≤ 200 ms |
| Diferencias con `estable-G-7` donde ese motor quedó completo | 0 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-7` | mediana de cada p95 sin empeorar más de un 20 %, en 3 rondas |
| RAM pico de la latencia fija | ≤ `estable-G-7` + 5 % |

Los estados correctos son:
- `padre(a,b)` y `abuelo(a,c)`: `supported`;
- `!padre(a,b)` con el afirmado: `refuted`;
- consultas con variables: `bindings`;
- en los negados por posición: los mismos de la línea base.

Se informa también el tamaño del archivo en disco con y sin el índice nuevo.

Los controles de 5.4 propios de aprendizaje (bot fresco, renombrado, señal confundida) no aplican: el cambio no aprende nada. Su control es la prueba diferencial.

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Si cien mil personas le dicen a Leobot el mismo dato, él revisaba las cien mil veces antes de responder y se quedaba sin tiempo, como si no supiera. Ahora mirará cada dato distinto una sola vez, sin importar cuántas veces se lo dijeron. Las respuestas no cambian; solo deja de perder el tiempo repitiendo.
