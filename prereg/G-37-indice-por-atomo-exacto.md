# G-37 — índice por átomo exacto para preguntar si un hecho existe

Fecha: 2026-09-23. Preregistro previo al cambio. Base: `estable-G-6` (`5dc07f52`).

## Fallo medido (auditoría 5.10 de G-36b)

`KnowledgeBase.contains` usa `matches`, que elige el índice por argumento más pequeño, lo **ordena** y lo recorre. Con memorias adversas, una respuesta rompe la regla 5.6 (≤10 ms para conocimiento ya adquirido):

| Caso adverso | Tiempo en G-36b | Tiempo en G-5 |
|---|---|---|
| 50 000 hechos negados en cada posición del átomo | 227 ms | 241 ms |
| El mismo átomo afirmado desde 100 000 fuentes | 1,2 s | 2,4 s |

## Cambio

En memoria, se mantiene un conteo por átomo exacto que se actualiza al añadir, retirar y cargar hechos. Con él, `contains(átomo_concreto)` responde en tiempo constante y no recorre índices.

La base en disco no cambia en este ciclo; se informa su tiempo.

Ninguna respuesta cambia: `contains` debe dar lo mismo que antes para todo átomo.

## Pruebas y puerta

**Prueba focal nueva** (`tests/test_exact_atom_index.py`):
- `contains` coincide antes y después de añadir y retirar;
- después de guardar y cargar;
- con el mismo átomo desde varias fuentes.

**Medición**, con p95 sobre 50 repeticiones en cada uno de los dos casos adversos:

| Operación | Umbral |
|---|---|
| `contains` | ≤ 1 ms |
| `answer_atom` del átomo negado | ≤ 10 ms |

Se informa `answer_atom` del átomo afirmado desde 100 000 fuentes. Si sigue por encima de 10 ms por la construcción de la prueba (la demostración recorre las 100 000 fuentes), se registra como límite restante y no se oculta.

**Además:**
- regresión completa sin fallos nuevos;
- prueba diferencial de `contains` frente a `estable-G-6` en 300 bases al azar, sin diferencias;
- latencia fija intercalada con `estable-G-6`, sin empeorar más de un 20 % en la mediana.

## En palabras fáciles de entender

Para saber si ya conoce un dato, Leobot a veces revisaba una lista larga de datos parecidos. Ahora tendrá un índice exacto, como el de un diccionario, para responder al instante si el dato existe, tenga los datos que tenga.
