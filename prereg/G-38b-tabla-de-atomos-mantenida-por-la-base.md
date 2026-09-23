# G-38b — que la propia base de datos mantenga al día la tabla de átomos

Fecha: 2026-09-23. Preregistro previo al cambio. Base: `estable-G-8` (`0c55e325`).

## Fallos (auditoría 5.10 de G-38)

1. **Tabla desactualizada.** La tabla `atoms` del disco se mantiene desde Python y se rellena solo si está vacía. Si otro programa, o un motor anterior, añade o borra hechos en el archivo, la tabla queda desactualizada y las respuestas salen mal: `unknown` sobre hechos presentes.
2. **Choque de claves.** La clave une el predicado y los argumentos con `\x1f` y aplica un hash. `p('a\x1fb','c')` y `p('a','b\x1fc')` chocan: `contains` responde falso y `remove` falla.
3. **Tamaño sin informar.** El preregistro de G-38 pedía el tamaño del archivo y no se informó: +73 % con 100 000 átomos distintos.

## Causa

La tabla derivada se mantiene fuera de la base, y la clave se calcula con una codificación ambigua.

## Cambio (5.8)

**La tabla `atoms` tiene clave compuesta, sin hash.**
- La clave es (predicado, aridad, k0…k7), donde `kᵢ` es el argumento i o `''` cuando i ≥ aridad.
- Con la aridad en la clave, la correspondencia es de uno a uno: los argumentos vacíos reales solo ocurren en posiciones menores que la aridad.

**Disparadores de SQLite sobre `facts`.**
- Al insertar, borrar o actualizar un hecho, los disparadores mantienen el conteo y el hecho más antiguo de cada átomo.
- Viven dentro del archivo, así que cualquier programa que escriba en él (también un motor anterior) deja la tabla al día.
- Python ya no mantiene la tabla.

**Versión del archivo** (`PRAGMA user_version = 2`). Un archivo anterior se migra una sola vez, dentro de una transacción: se borra la tabla antigua y se reconstruye desde `facts`.

**Índices redundantes.**
- Se quitan `ix_facts_pred` e `ix_facts_pred_a0`: el índice de átomo exacto los cubre como prefijo.
- En `atoms` no se crea índice para k0: la clave primaria lo cubre.

**Enmienda antes del código (2026-09-23):** la clave de duplicados de `facts` (`fact_key`) une predicado, fuente y argumentos con el mismo `\x1f`. Por eso `p('a\x1fb','c')` y `p('a','b\x1fc')` con la misma fuente se toman por el mismo hecho y el segundo no se guarda (defecto ya presente en `estable-G-7`). Se codifica sin ambigüedad (JSON de la lista) y la migración recalcula la clave de todas las filas. Criterio añadido: ese caso guarda los dos hechos. Donde `estable-G-8` guarda mal ese caso, la diferencial no lo cuenta como diferencia, porque las memorias al azar no usan `\x1f`.

**Enmienda del mecanismo antes de congelar (2026-09-23), sin cambiar criterios:** el primer diseño en desarrollo falló el criterio de tamaño: 70,3 MiB frente a 69,5 de `estable-G-8`, con construcción de 7,5 s frente a 3,6 s. En una tabla sin identificador de fila, cada índice secundario copia la clave de 10 columnas. Cambios:
- la tabla `atoms` pasa a tener identificador de fila y clave única;
- `facts` conserva solo el índice de átomo exacto (se quitan los ocho índices por posición);
- `matches` con variables busca los átomos y, desde ellos, sus hechos por ese índice exacto, en orden de identificador.

Medido en desarrollo: 49,3 MiB y 4,3–4,6 s.

**Qué se elimina:** el hash `_atom_key`, el mantenimiento desde Python y dos índices.

## Pruebas y puerta

**Pruebas focales** (se amplía `tests/test_distinct_atoms.py`):
- un archivo creado por este motor y modificado después con SQL directo (altas y bajas sin pasar por el motor) responde bien al reabrirlo;
- el caso de choque de la auditoría responde como `estable-G-7`, y `remove` no falla;
- un archivo de `estable-G-7` y uno de `estable-G-8` se abren y responden bien.

**Prueba diferencial ampliada** (`experiments/g38b_differential.py`), contra `estable-G-8` en proceso aparte:
- 300 memorias con semilla tomada de la huella de `freeze-G-38b`;
- aridades 1 a 4, hasta 12 fuentes por átomo, `replace`, variables repetidas y bajas del hecho más antiguo;
- en todas las memorias: memoria, disco, disco reabierto, y disco escrito en parte con SQL directo.

**Criterios:**

| Criterio | Umbral |
|---|---|
| Diferencias con `estable-G-8` donde ese motor quedó completo (memoria y disco sin SQL directo) | 0 |
| Disco escrito con SQL directo frente a la memoria equivalente | 0 diferencias |
| Casos adversos de G-38 | los mismos estados, todos completos; consultas concretas en disco p95 ≤ 10 ms; con variables ≤ 200 ms |
| Tamaño del archivo con 100 000 átomos distintos | ≤ el de `estable-G-8` |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-8` | mediana de cada p95 sin empeorar más de un 20 % |

**Se informan:**
- tamaño y tiempo de construcción frente a `estable-G-7` y `estable-G-8`;
- tiempo de migración de un archivo de 100 000 hechos.

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot guarda en disco una lista resumida de sus datos distintos. Hasta ahora esa lista la actualizaba Leobot a mano. Si otro programa tocaba el archivo, la lista quedaba vieja y Leobot se equivocaba. Ahora el propio archivo se encarga de actualizarla, lo toque quien lo toque, y además se corrige una forma de nombrar los datos que podía confundir dos datos distintos.
