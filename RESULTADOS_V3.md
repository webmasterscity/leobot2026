# Resultados de Leobot V3.6

## Estado

La V3 mejora de forma medible la escalabilidad y amplitud del prototipo, pero **no demuestra AGI ni ASI**.

## Pruebas automatizadas

**117/117 aprobadas** en la ejecución final incluida.

Las 58 pruebas heredadas de V2 siguen pasando y se añadieron pruebas para:

- referencias de habilidades sin expansión;
- invalidación transitiva de dependencias;
- 3.000 capas de habilidades sin desbordar la pila;
- selección relacional frente a 250 predicados irrelevantes;
- cierre transitivo de 6.000 nodos;
- paráfrasis composicional;
- descubrimiento genérico de factorial;
- descubrimiento genérico de Fibonacci;
- persistencia de recurrencias y conceptos;
- backend SQLite;
- persistencia del bot escalable.

## Benchmark V3

| Prueba | Resultado |
|---|---:|
| DAG de habilidades | 10.000 capas correctas |
| Tiempo DAG 10.000 capas | ~25,7 ms |
| Tamaño de la expresión de la capa 10.000 | 12 caracteres |
| Habilidades irrelevantes con routing conceptual | 50.000 |
| Candidatas recuperadas | 2 |
| Aprendizaje de habilidad compuesta | ~2,2 ms |
| Predicados relacionales irrelevantes | 5.000 |
| Predicados seleccionados | 1 (`signal`) |
| Aprendizaje relacional | ~0,40 ms |
| Cierre transitivo | 20.000 nodos |
| Trabajo del cierre | 19.999 aristas |
| Tiempo del cierre | ~314 ms |
| Memoria factual SQLite | 200.000 hechos |
| Consultas puntuales correctas | 500/500 |
| Mediana consulta SQLite | ~0,051 ms |
| p95 consulta SQLite | ~0,070 ms |
| Factorial | descubierto |
| Fibonacci | descubierto |
| Recurrencia con `f(n-3)` | descubierta |
| Tribonacci | descubierto |
| Recurrencia real de orden 4 | sin solución (control) |
| Paráfrasis composicionales nuevas | 3/3 |
| Peticiones abiertas no enseñadas | 0/5 |

Los tiempos son de una única máquina de prueba y no deben presentarse como garantías de producción. El archivo `results_v3/v3_results.json` contiene los valores exactos de la ejecución.

## Mejora 1 — de árbol exponencial a DAG compartido

V2 copiaba el programa previo dentro del siguiente programa. Una cadena de duplicaciones podía crecer como árbol.

V3 guarda:

```text
s10000 = @s9999 + 1
```

en vez de expandir todo `s9999` dentro de `s10000`.

El benchmark construyó 10.000 niveles y mantuvo una representación superior constante. La evaluación usa un recorrido iterativo del DAG y memoización, por lo que la profundidad ya no depende de la pila de Python.

## Mejora 2 — selección de conocimiento relevante

### Relaciones

La memoria mantiene un índice entidad→predicado. Con 5.000 predicados irrelevantes cuyas entidades no participaban en el problema, el aprendiz no los enumeró: seleccionó únicamente `signal`.

### Habilidades

V3 añade un índice concepto→habilidad. Con 50.000 habilidades etiquetadas como no relacionadas y dos habilidades dentro del contexto relevante, el router recuperó 2 candidatas y aprendió correctamente la composición.

Control: sin contexto conceptual, 2.000 habilidades requirieron ~305 ms de escaneo. El fallback sigue siendo lineal y se reporta como tal. Esto es un límite real, no una regresión escondida.

## Mejora 3 — algoritmos recursivos

Se añadió un meta-sintetizador de recurrencias: para cada retardo permitido transforma la secuencia en un nuevo problema de síntesis cuyo cuerpo recibe `n, f(n-1), f(n-2), f(n-3)` según corresponda. No enumera nombres de secuencias.

Con los ejemplos 1→1, 2→2, 3→6, 4→24, 5→120, 6→720 descubrió:

```text
f(n)=(n * f(n-1)); base={1:1}
```

y produjo `f(8)=40320`.

Para Fibonacci descubrió:

```text
f(n)=(f(n-1) + f(n-2)); base={0:0,1:1}
```

y produjo `f(12)=144`.

No existen ramas llamadas `factorial`, `fibonacci`, `lag3` o `tribonacci`. El mismo sintetizador descubrió además `f(n)=f(n-1)+f(n-3)` y `f(n)=f(n-1)+f(n-2)+f(n-3)`.

Control negativo: una recurrencia de orden 4 (Tetranacci) quedó sin solución porque el meta-DSL actual limita el retardo a 3. Esto delimita la capacidad demostrada.

## Mejora 4 — recursión lógica larga

Las clausuras transitivas aprendidas con el patrón compatible se compilan a BFS indexado para consultas con un extremo conocido.

En 20.000 nodos visitó 19.999 aristas y respondió correctamente, eliminando el límite anterior de profundidad de Python para este patrón.

No transforma una consulta inherentemente de todos-contra-todos en una operación constante. El coste sigue dependiendo del subgrafo alcanzable.

## Mejora 5 — memoria en disco

`SQLiteKnowledgeBase` almacena hechos e índices en SQLite. En la prueba de 200.000 hechos:

- inserción total: ~5,25 s;
- 500/500 consultas puntuales correctas;
- mediana: ~0,051 ms;
- p95: ~0,070 ms;
- archivo: ~104 MB (~521 bytes/hecho incluyendo índices).

Esto elimina el requisito de mantener todos los hechos como objetos Python en RAM. El límite práctico pasa a almacenamiento, índices y coste de la consulta, no a un JSON monolítico cargado completo.

## Mejora 6 — lenguaje composicional limitado

Después de enseñar:

```text
¿Dónde vive Ana?
¿Dónde reside Bruno?
¿En qué ciudad vive Carla?
```

el sistema aprendió sustituciones locales y pudo interpretar, sin haberla visto:

```text
¿En qué ciudad reside Diego?
```

La prueba dio 3/3 en combinaciones equivalentes no enseñadas.

Sin embargo, cinco peticiones generales de resumen, explicación, planificación, comparación y diseño experimental quedaron 0/5. Por tanto, esta mejora no debe confundirse con comprensión general del español.

## ¿Más información lo hace más inteligente?

La evidencia de V2 y V3 respalda una afirmación limitada:

> información correcta, discriminante y bien representada puede ampliar las clases de problemas que el sistema resuelve y las habilidades que puede reutilizar.

No respalda:

> cualquier cantidad de datos adicionales produce inteligencia ilimitada.

Información irrelevante debe ser indexada/ruteada; información contradictoria puede degradar una hipótesis; y nuevas clases de problemas pueden requerir ampliar el espacio de programas representables.


## Ciclo V3.1 — adquisición lingüística contrastiva

Se encontró primero un fallo real: con un único hecho `trabaja(bruno, acme)`, la versión anterior podía oír «Bruno odia Acme», inferir por coincidencia que `odia -> trabaja` y transferir después ese significado falso. También fallaba al adquirir una negación cuando una construcción positiva podía absorber «no» dentro de un slot.

La corrección introduce: (1) mínimo de dos apoyos independientes, (2) espacios de hipótesis por intersección, (3) hechos negativos como candidatos, (4) preferencia por construcciones con mayor estructura fija y (5) reutilización de equivalencias léxicas entre actos comunicativos del mismo predicado.

Resultados de `v31_grounding_experiment.py` con el aprendiz congelado durante cada condición:

- candidato de dos apoyos: **6/6** afirmaciones nuevas correctas y **2/2** consultas de la batería V3.1;
- control con grounding deshabilitado: **0/6** y **0/2**;
- coincidencia semántica de un solo episodio: el candidato quedó pendiente y no creó el hecho falso; la ablación de un solo apoyo sí lo creó;
- dos episodios ambiguos `{vive, trabaja}` y `{vive, posee}`: el version-space promovió `vive` y transfirió; la ablación `unique-only` quedó sin aprender;
- SQLite con 20.000 hechos de ruido: dos episodios de grounding promovieron la construcción y la transferencia fue correcta;
- 5.000 predicados distractores en el benchmark V3: primer apoyo ~4 ms, segundo apoyo ~0,22 ms en esta ejecución;
- una pregunta con 100 significados compatibles quedó `grounding_pending`, con **0 cambios en la gramática activa**.

Estas pruebas son internas y diseñadas durante el desarrollo; no constituyen evaluación independiente de lenguaje general ni AGI. La petición abierta de resumir y comparar ideas continúa `unrecognized`.

## Ciclo V3.2 — grounding de procedimientos

Código congelado durante la evaluación: `8b02a560907cc90944460d29b23604558c11a9c955c7d325f9a3b89d9b06f5a1` (SHA-256 sobre `leobot/*.py`).

Resultados de `v32_procedure_grounding_experiment.py`:

- `Suma <n> al valor`: 200/200 casos con parámetros no vistos; memoria episódica 0/200.
- `Intercambia los valores`: 200/200 estados nuevos; memoria episódica 0/200.
- procedimiento `combina y duplica`: 200/200 con habilidad previa reutilizada; 0/200 con la misma habilidad previa pero composición desactivada; 0/200 sin experiencia previa; memoria episódica 0/200.
- adquisición de la tarea compuesta con reutilización: 1 candidato; ablación sin biblioteca: no solución dentro de `max_size=3`.
- repetir siete veces el mismo episodio conserva apoyo independiente = 1.
- el hash del código fue idéntico antes y después de la evaluación.

Esto es validación interna diseñada por el desarrollador, no una prueba independiente de AGI/ASI.

## Ciclo V3.3 — paráfrasis procedurales, composición y planificación

Hash congelado de `leobot/*.py` durante la evaluación: `ed32eba1eb725b9064c1e74c42db881629b5a726bce4134e7b8bffeff4fcae82`.

La regresión final queda en **102/102 pruebas**. V3.1, V3.2 y el benchmark V3 fueron reejecutados después de los cambios.

Resultados de `v33_procedure_composition_experiment.py`:

| Prueba | V3.3 | Control |
|---|---:|---:|
| Paráfrasis procedural compuesta no observada | 200/200 | superficie exacta 0/200 |
| Secuencia `añadir → doblar` | 200/200 | sin composición 0/200 |
| Secuencia inversa `doblar → añadir` | 200/200 | — |
| Secuencia nueva de 3 pasos | 200/200 | — |
| Secuencia que requiere paráfrasis | 200/200 | sin reescritura 0/200 |
| Objetivos alcanzables con habilidades aprendidas | 200/200 | sin `duplicar` 48/200 |
| Español de objetivo calculado → plan | 200/200 | sin grounding del objetivo 0/200 |
| Referencia con objetivo estructurado | 200/200 | — |

La superficie `Añade <n> a la cantidad` nunca fue enseñada directamente. Surgió al recombinar dos sustituciones inferidas de procedimientos independently grounded: `añade↔suma` y `a la cantidad↔al valor`. La equivalencia solo se activa cuando la forma ejecutable canónica y probes independientes coinciden; sigue siendo una hipótesis operacional, no una prueba lingüística universal.

La orden `Añade N a la cantidad y luego dobla el resultado` se ejecuta como dos habilidades adquiridas, con estado intermedio explícito. Invertir el orden cambia correctamente el resultado. Una frase completa que ya tiene evidencia procedural propia pero no resuelta **no** se descompone para evadir esa incertidumbre.

El planner usa BFS acotado sobre procedimientos grounded de forma compatible con el estado. En V3.3 no inventa valores para parámetros de acciones: si únicamente existe `Suma <n>` y no hay propuesta de `n`, reporta que no dispone de acciones autónomamente enumerables. Esto es un límite deliberado y probado.

El grounding de objetivos sintetizó a partir de tres ejemplos la construcción `Lleva el valor a <n0> más que <n1>` y resolvió pares numéricos nuevos; después el planner alcanzó esos objetivos. Un control con las mismas acciones pero sin aprendizaje de esa construcción quedó 0/200.

Contraevidencia: al introducir una transición incompatible para una superficie que participaba en `añade↔suma`, el procedimiento dejó de estar promovido y la reescritura fue retirada. Esto evita conservar una equivalencia obsoleta tras cambiar la evidencia.

Estos resultados siguen siendo internos, en estados numéricos acotados y con problemas diseñados durante desarrollo. No demuestran AGI/ASI ni comprensión/planificación abierta.

## Ciclo V3.4 — modelos de acción simbólicos

| Prueba | Resultado |
|---|---:|
| Suite completa después de V3.5 | 111/111 |
| Planes held-out V3.4 | 200/200 |
| Verificador de referencia independiente | 200/200 |
| Memoria episódica | 0/200 |
| Ablación solo éxitos | 0/200 |
| Persistencia | PASS |

El control `positive_only` observa los mismos éxitos pero no los intentos fallidos. Conserva correlaciones espurias que aparecían en todos los éxitos y por eso no transfiere a los mundos reservados. Los contraejemplos permiten eliminar esas condiciones en el modelo completo.

La prueba de distractores mantuvo el mismo resultado con 10.000 hechos irrelevantes, aunque la canonización de todo el estado sigue teniendo coste lineal (~55 ms de mediana en esa corrida para 10.009 hechos). Esto es un límite medido, no escalabilidad ilimitada.

## Ciclo V3.5 — transferencia de lenguaje desde habilidades anteriores

| Prueba | Con habilidad previa | Desde cero con 2 episodios |
|---|---:|---:|
| Sintaxis reordenada de movimiento | 200/200 | 0/200 |
| Sintaxis reordenada de recoger | 200/200 | 0/200 |

Al tercer episodio, el control desde cero aprende el operador completo. Por tanto, la evidencia apoya **menor coste de adquisición debido a conocimiento previo**, no que el control sea incapaz por construcción. Contraevidencia posterior retiró el alias de movimiento sin borrar el de recogida.


## V3.6 — inducción jerárquica desde planes verificados

Código congelado del experimento: `d552e5c1a9bc1e66c149c72abba2496c62fe42c4b6ea5876ba868d3dc2f7b482`.

La macro evaluada no fue escrita a mano: surgió de tres planes primitivos independientes de 4 pasos con roles/entidades distintos. Repetir el mismo episodio no aumenta soporte. La abstracción conserva precondiciones/efectos netos, secuencia expandible y fingerprints de dependencias.

| Medición | Resultado |
|---|---:|
| Suite completa | **117/117** |
| Transferencia jerárquica, mundos nuevos | **200/200** |
| Control primitivo con profundidad 2 | **0/200** |
| Verificación por ejecutor de referencia | **200/200** |
| Coincidencias de caché episódica exacta | **0/200** |
| Mediana de nodos, jerarquía (misma profundidad suficiente) | **2** |
| Mediana de nodos, control primitivo | **23** |
| Mediana de transiciones, jerarquía | **2** |
| Mediana de transiciones, control primitivo | **37** |
| Horizonte probado | **256 macros = 1.024 primitivas** |
| Nodos/transiciones en ese horizonte | **256 / 256** |
| Tiempo de esa corrida | **~34,2 ms** |
| Macros después de invalidar operador base | **0** |

Escala con hechos distractores en un problema de dos entregas (mediana de 5 corridas): 0 → ~0,32 ms; 100 → ~2,25 ms; 500 → ~11,33 ms; 1.000 → ~23,92 ms; 2.000 → ~47,61 ms. Nodos y transiciones permanecieron en 2; el coste residual proviene principalmente de ingerir/indexar más hechos.

El rollout rápido **no adivina** ante ambigüedad. Se incluyó un mundo con dos macros inicialmente plausibles: el fast path se retiró y el planner completo encontró un plan correcto de dos macros.

Límites: las macros actuales abstraen secuencias fijas observadas; no descubren todavía bucles/recursión de acciones de longitud variable, el estado simbólico sigue materializándose en memoria y la comprensión abierta del benchmark base continúa fallando. Nada de esto demuestra AGI/ASI.

## V3.8 — invención grounded de conceptos

- Suite tras V3.8: 128/128.
- `parent ; parent`: 100/100 positivos held-out y 0/100 falsos positivos.
- Nueva formulación con concepto previo: 100/100 tras 2 ejemplos contrastivos; desde cero con los mismos 2 ejemplos: 0/100.
- Reserva estructural: `inverse(teach)` aprendido y transferido.
- Concepto aprendido usado como primitiva de un concepto de orden superior bajo el mismo límite de profundidad.
- Resultado: `results_v3/v38_concept_invention.json`.

## V3.9 — predicado auxiliar inventado y reutilizado

- Suite: 131/131.
- `r;s;r;s`, profundidad 2: invención 100/100; control sin invención 0/100.
- Auxiliar final: `r;s` (nombre opaco `invent_*`), descubierto en 2 intentos en la corrida final.
- Primera adquisición: ~19,8 ms / 178 candidatos acumulados; baseline profundidad 4: ~13,3 ms / 150 candidatos. No hay ventaja inicial de coste.
- Reutilización posterior para `r;s;t` con invención desactivada: 100/100; control profundidad 2 sin helper 0/100; baseline profundidad 3 100/100.
- Reutilización: ~14,8 ms / 168 candidatos frente a ~15,7 ms / 184 candidatos directos en esa corrida.
- Resultado: `results_v3/v39_predicate_invention.json`.
