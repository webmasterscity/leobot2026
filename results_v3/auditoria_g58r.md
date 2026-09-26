# Auditoría independiente 5.10 de G-58 y `freeze-G-58r`

- Fecha: 2026-09-26.
- Auditor: Claude (Opus 5.5), subagente nuevo, sin el razonamiento de la sesión.
- Copia propia: worktree en `freeze-G-58r` (commit `0fc21df`, motor `7c8bb1bc`). La huella del motor no cambió durante la auditoría; no se tocaron `leobot/` ni `tests/`.
- Python 3.12.3. `PYTHONHASHSEED=0` salvo donde se indica.

## Veredicto

**Las cifras declaradas se reproducen exactamente.** No encontré hardcodeo ni filtraciones del banco de G-58. Las decisiones están razonadas y declaradas.

`freeze-G-58r` es apto como tag estable, con dos condiciones:
- ejecutar antes las medidas de la sección 7 que faltan: tablero, prueba fija de latencia y sonda (las pedía el preregistro y no aparecen en el resultado);
- declarar las objeciones de la sección 7 de este informe.

La más importante: el eco todavía repite datos personales breves («Me llamo Ana.»). Además, en el control con el documento de otro negocio, el 28,8 % de las citas de G-58r son engañosas.

## 1. Orden en git

La historia es lineal, y cada paso depende del anterior en el grafo de commits.

| Paso | Commit | Hora | Contenido |
|---|---|---|---|
| Preregistro | `dcb9681` | 01:37:50 | solo `prereg/G-58-…md` |
| Código = `freeze-G-58` | `577ddf6` | 01:40:03 | `leobot/context.py`, `g58_calibrar_cercano.py`, prueba y veredictos del juez de G-57; árbol del motor `86684a21` ✔ |
| Evaluador y juez | `6bda15a` | 01:41:51 | `g58_evaluar.py`, `g58_juez.py` |
| Banco congelado | `1051ffd` | 01:55:38 | `results_v3/kiosco/congelado_g58` (24 negocios, 630 turnos) |
| Resultados automáticos | `306b825` | 01:58:18 | `evaluacion_g58/*.json` |
| Juez y retirada = `freeze-G-58r` | `0fc21df` | 02:05:07 | veredictos, resultado del preregistro; árbol del motor `7c8bb1bc` ✔ |

- **El preregistro precede al código**, y el código y `freeze-G-58` preceden al banco. El banco precede a los resultados.
- El archivo `base_freeze_g58.json` es de las 01:40, anterior al banco.
- **Entre `dcb9681` y `0fc21df` el preregistro solo recibió la sección «Resultado» añadida al final.** Los criterios no cambiaron.
- **`freeze-G-58r` frente a `freeze-G-58`:** en `leobot/` solo se quita el bloque de seguimiento y su ayudante `_client_turns` (la lista de nombres de rol que usaba el seguimiento), y se cambia la documentación de `answer`. En `tests/` se añade un `@unittest.expectedFailure` a la prueba del seguimiento. Nada más.
- **Observación:** los veredictos crudos del juez de G-57 (`evaluacion_g57/juez/juez*/`) no entraron en git al cerrar G-57 (`a705c64`), sino junto al código de G-58 (`577ddf6`). Comprobé que no se alteraron: `python3 -m experiments.g57_juez reunir …` con esos veredictos reproduce **byte a byte** `evaluacion_g57/juez_puertas.json`, que ya estaba en `a705c64`.

## 2. Base reproducible

| Paso | Salida | SHA-256 | Tiempo | RAM pico |
|---|---|---|---|---|
| `g57_educar_kiosco` desde `base_freeze_g55r.json` | `m.json` | `babf1f30…` | 15 s | 0,54 GB |
| `g57_calibrar_kiosco` (desarrollo A–D) | `c.json` | `3d6ae179…` = `base_freeze_g57r.json` ✔ | 6 s | 0,57 GB |
| `g58_calibrar_cercano` | `b.json` | **`1c0db7a6a23d7b58…` = `base_freeze_g58.json`** ✔ | 6 s | 0,80 GB |

Salida de la tabla de lo más cercano:
- celdas `closest`: `0,4 · 1,3 · 1,4 · 2,3 · 2,4 · 3,4`;
- 566 turnos etiquetados y 39 sin juicio, que se saltan;
- en esas celdas, 100 de 149 turnos útiles (67 %), contado sobre el mismo banco de G-57.

`c.json` y `b.json` solo difieren en `context_model.closest`, `closest_cells` y `source`, es decir, en cuentas por celda y rutas.

## 3. Cifras en el banco congelado

Orden: `python3 experiments/g57_kiosco.py b.json … congelado_g58/V1 … V6 --respuestas`.

| Comprobación | Resultado |
|---|---|
| Frente a `evaluacion_g58/sin_seguimiento.json` (respuesta, estado, celda, veredicto y candidata) | **630/630 idénticas** con `PYTHONHASHSEED=0` |
| Lo mismo con `PYTHONHASHSEED=1` | **630/630 idénticas**, y semilla 0 = semilla 1 |
| Frente a `tratamiento.json` (G-58 con seguimiento) | 570/630 iguales: las 60 que cambian son las del seguimiento |
| Conteo automático | útiles 61/266; sin respuesta 174/174 con «No lo sé» o cita (igual que lo declarado) |
| Tiempo por turno en esta corrida | p50 0,11 ms · p95 0,21 ms |

Controles adicionales con el motor de G-58r. El proyecto no los tenía para G-58r porque `g58_evaluar.py` exige el árbol de `freeze-G-58`:
- **reinicio:** 630/630 idénticas;
- **renombrado estricto:** 615/630 (97,6 %) de respuestas iguales tras deshacer el cambio de nombres (≥ 95 %: pasa). Con la misma definición reproduzco el 611/630 declarado para G-58; esa cifra no la produce ningún guion en git;
- **otro negocio:** 0 útiles, 530/630 «No lo sé», 73 citas. Con los veredictos ya dados por el juez (todas estaban juzgadas), **21 de las 73 citas son engañosas (28,8 %)**, por encima del 22,7 % declarado para G-58.
- **Regresión completa:** 661 pruebas, 6 fallos esperados, 0 fallos (99,6 s). `tests/test_g57_kiosco.py` da 18 pruebas y 3 fallos esperados; las pruebas rápidas pasan.

## 4. Puertas con el juez

`python3 -m experiments.g58_juez reunir …` reproduce **byte a byte** `evaluacion_g58/juez_puertas.json`. Las cifras coinciden con el «Resultado» del preregistro:

| | G-58 (tratamiento) | G-58r (= sin seguimiento) | Otro negocio (G-58) | Tabla barajada |
|---|---|---|---|---|
| Útiles en directa + sí/no | 65/266 (24,4 %) | 62/266 (23,3 %) | 0/266 | 22/266 (8,3 %) |
| Inventadas | 0 | 0 | 0 | 0 |
| Sin respuesta bien llevadas | 169/174 (97,1 %) | 169/174 (97,1 %) | 172/174 | 174/174 |
| Citas engañosas | 9/212 (4,2 %) | 6/152 (3,9 %) | 22/97 (22,7 %) | 4/189 (2,1 %) |
| Citas útiles entre las citas | 48,1 % | 59,9 % | 0 % | 19,6 % |
| Ecos de datos | 0 | 0 | 0 | 0 |

Desglose del seguimiento, en las preguntas de tipo `seguimiento`:
- útiles 13 → 18 y engañosas 1 → 3;
- en todo el banco, útiles 62 → 65 y engañosas 6 → 9.

Coincide con lo declarado.

**Muestra revisada a mano.** Tomé 30 veredictos de G-58r con la semilla 58, estratificados: 12 `util`, 10 `honesta`, 6 `enganosa` y 2 «No lo sé» en preguntas con respuesta. Los leí con el texto del negocio, la evidencia y la respuesta ideal.
- **De acuerdo en 29 de 30.**
- `util`: las 12 citan de verdad el dato pedido. Por ejemplo, «¿Hasta qué día del mes puedo pagar sin recargo?» → «…los primeros 5 días de cada mes…».
- `honesta`: 9 claras, como «que formas de pago tienen?» → «FORMAS DE PAGO», un título solo, o «¿La evaluación médica tiene costo?» → «Evaluación médica de ingreso realizada por la Dra. Perdomo».
- **1 dudosa:** «y para desempleados teneis alguna tarifa?» → «No, de momento no tenemos tarifa de residente». El juez la llama honesta. Yo la llamaría engañosa, porque el «No,» inicial invita a leer un no a lo que se preguntó.
- `enganosa`: las 6 lo son. Precio nacional de maleta citado para un vuelo a Bogotá. «Bajos de pantalón: 8 €» ante una prenda comprada en otra tienda. «Sí, para teoría musical y canto…» ante «¿y si cancela el profesor?».
- Los 2 «No lo sé» eran preguntas con respuesta. En una, la candidata guardada aparte era justo el dato: «Exceso de peso (de 23,1 a 32 kg): USD 30», en la celda `3,3`, que no está admitida.

**Tendencia del juez:** es algo indulgente con citas que empiezan por «Sí»/«No» y responden otra pregunta. Clasifiqué la forma de las 152 citas de G-58r:
- 11 empiezan por «sí» o «no»: 5 útiles, 4 honestas y 2 engañosas;
- 10 tienen cuatro palabras o menos: 8 honestas y 2 útiles;
- 131 son el resto: 84 útiles, 43 honestas y 4 engañosas.

No cambia ninguna puerta: aun contando la dudosa como engañosa, quedan 7/152 = 4,6 %.

## 5. Hardcodeo y filtraciones (5.7)

**`leobot/context.py` desde `estable-G-16`.** Solo se añadió esto:
- las constantes `CLOSEST_TEXT` y `ECHO_WORDS = 4`;
- `_level`, que elige el nivel por la pertenencia de la celda a la lista contada `closest`;
- el filtro del eco: más de 4 palabras o alguna cifra;
- el formato de la cita.

No hay listas de palabras, reglas por negocio ni ramas según el contenido de la pregunta. El resto del archivo, de G-57 y ya auditado, solo usa marcas de forma (títulos, listas, tablas, puntuación) y cuentas aprendidas (δ y puente de MFAQ, lemas de AnCora, interrogativos aprendidos). Las funciones cambiadas solo se usan dentro de `context.py`: `respond` no cambia.

**Texto de los bancos en la base.**
- La única diferencia entre la base de G-57r y la de G-58 son 6 identificadores de celda, 25 pares de cuentas y rutas.
- Nombres propios del banco de G-58 (KALLPA, Farallones, Nevada Serrana, Olas Locas, Bonetti, «frigorías», etc.): 0 apariciones en `b.json`.
- Algunas cadenas aparecen: «Marina Real» 1 vez, «Mirador» 2 y «TICO» 2. Aparecen las mismas veces en `base_freeze_g55r.json`, del 2026-09-25, anterior a los dos bancos: vienen de corpus antiguos.
- Tampoco aparece ningún texto del motor ni de las citas.

**La tabla usa solo el banco de G-57.**
- `g58_calibrar_cercano.py` lee `results_v3/kiosco/congelado/W*` y los veredictos de `evaluacion_g57/juez`.
- Reconstruí `b.json` byte a byte en una copia que ya contiene el banco de G-58, así que la base no depende de él.
- El banco de G-57 estaba gastado: su resultado estaba en git (`a705c64`) antes del preregistro de G-58.

**¿La frase de aviso es una plantilla prohibida?** Mi opinión: **es voz del motor aceptable, como «No lo sé»**, por cuatro razones:
- es una sola frase fija que no depende del negocio, de la pregunta, del tipo de pregunta ni del examen;
- no contiene conocimiento ni respuesta: envuelve texto literal del documento y comunica un estado del propio motor, la confianza contada de su celda;
- lo prohibido por `CLAUDE.md` (n.º 1) son plantillas «para casos concretos»; esta es el canal con que el motor dice «no estoy seguro», del mismo tipo que el «No lo sé» que la misión exige preferir a inventar;
- el diccionario de salida ya lleva `status: 'closest'` y `evidence`, así que quien integre podría presentarlo de otra forma.

Pasaría a ser un problema:
- si se multiplicaran las frases escritas a mano según el tipo de pregunta o la celda («para precios, lo más cercano…»);
- si se usara para imitar respuestas naturales en vez de declarar un estado.

Detalle menor: si la cita ya trae comillas «», quedan anidadas.

## 6. Decisiones

**a) Retirada del seguimiento: bien razonada y declarada.**
- Aplica la regla preregistrada al pie de la letra: debía sumar útiles en `seguimiento` sin subir las engañosas, y las subió de 1 a 3.
- Verifiqué las cifras. Además, el seguimiento se disparaba en 60 turnos. 19 eran preguntas sin respuesta que pasaron de «No lo sé» a una cita honesta: más ruido sin ganancia, lo que apoya la retirada.
- La muestra es pequeña (+2 engañosas); la decisión es por regla, no por significación, y eso es lo correcto.
- `freeze-G-58r` es una variante posterior a medir, pero idéntica (630/630) a una variante ya medida y juzgada a ciegas. Es legítimo, y lo verifiqué directamente.
- Menor: marcar como `expectedFailure` la prueba de una función retirada adrede no es del todo el uso previsto. Ese marcador documenta límites abiertos; aquí sería más claro borrar la prueba o probar con `follow_up` como parámetro. No debilita ninguna prueba anterior a G-58.

**b) El banco de G-57, con veredictos del juez, para contar la tabla: aceptable y declarado.** Tiene cuatro matices:
1. La regla (celdas con utilidad ≥ 50 % y 5 casos o más) se diseñó mirando esos mismos veredictos. El preregistro dice «74 % (69 de 93)» en las celdas útiles. La tabla que se implementó da 67 % (100/149) sobre el mismo banco. La diferencia no se declara. Fuera de muestra, en el banco de G-58, las citas útiles son el 59,9 % (91/152): el umbral del 50 % se sostiene.
2. Las etiquetas son juicios de un modelo de lenguaje sobre preguntas escritas por modelos de lenguaje. No son una fuente de respuestas (solo 25 pares de cuentas), pero la calibración hereda ese criterio. Es el mismo precedente que G-57 con el banco de desarrollo.
3. Dos celdas admitidas están al borde: `0,4` con 5/9 y `2,3` con 26/48.
4. La tabla barajada (8,3 % de útiles frente a 23,3 %) demuestra que las cuentas importan.

**c) Que no haya respuestas planas: correcto y honesto.**
- Ninguna celda alcanza la cota del 2 % de error: la mejor precisión en desarrollo es 81 %.
- La puerta 2 queda **vacía**, no superada, y así se declara.
- Consecuencia práctica: todo lo útil llega con «No lo tengo seguro», también cuando es exacto.
- «0 inventadas» se cumple por construcción (solo se cita texto literal). El riesgo real se desplaza a las citas engañosas.

**d) Lo que falta para un kiosco real.** El resultado no lo discute; lo reúno con cifras de G-58r:
1. **Cobertura.**
   - De 400 preguntas con respuesta, 286 (71,5 %) acaban en «No lo sé» y 89 (22,3 %) en una cita útil.
   - En las preguntas de seguimiento: 13 útiles de 71.
   - En la charla: 23 de 56 turnos reciben «No lo sé: no encontré esa información…» (por ejemplo, «Perfecto, muchísimas gracias por la info»). Otro recibe una cita del correo del negocio, porque «info» coincide.
2. **Siempre con duda:** no hay respuesta directa.
3. **Forma de las citas.** Varios defectos de la segmentación de G-57, que la cita deja al descubierto:
   - títulos solos: «FORMAS DE PAGO», «SALA VIP», «TARJETA REGALO»;
   - la pregunta de unas preguntas frecuentes citada como si fuera la respuesta: «¿Tienen parqueadero?»;
   - la respuesta de unas preguntas frecuentes sin su pregunta, cuando ambas van en la misma línea: «Sí, para teoría musical y canto…» es 2 de las 6 engañosas;
   - una tabla con tabuladores y sin fila de encabezado: la primera fila de datos se toma como encabezado y mezcla precios. En V4/n4 sale «Visita y diagnóstico a domicilio: Instalación de aire split hasta 3000 frigorías; $ 18.000: $ 85.000 + materiales», juzgada engañosa.
4. **El eco repite a la persona.**
   - El filtro de G-58 solo corta turnos de más de 4 palabras o con cifras. En el banco, el motor dice como propias frases del cliente: «Perfecto, voy pa'ya.», «Ya, gracias señorita.», «Mi hijo tiene asma. No lo sé…», «No, no tengo. No lo sé…» (esta última puede leerse como «no lo tenemos»).
   - Con una sonda propia (no es material reservado): «Me llamo Ana» → **«Me llamo Ana.»** en V6/n2.
   - La puerta 5 pasa tal como se definió, pero la frase del preregistro «nunca se repiten datos de la persona» no es cierta para datos breves.
5. **Instrucciones:** los casos de «derivar» reciben una cita o «No lo sé», no el contacto al que derivar.
6. **Preguntas fuera del texto:**
   - con el documento de otro negocio, el 28,8 % de las citas de G-58r son engañosas;
   - en el negocio correcto, 5 de las 35 citas dadas a preguntas sin respuesta (14,3 %) son engañosas.
7. **Sin medir para G-58:** el examen privado del usuario (G-57: 0/54).

## 7. Objeciones que conviene declarar antes del tag

1. **Medidas del preregistro sin informar:** SQuAD-es (1570 casos), tablero y sonda no aparecen en el «Resultado». El riesgo es bajo porque `respond` no cambió, pero la omisión no se declara. La misión (sección 7) pide además tablero, prueba fija de latencia y sonda antes de todo tag `estable-*`.
2. **Otro negocio con G-58r:** 21/73 citas engañosas (28,8 %). No se declaró para G-58r; para G-58 se declaró 22/97.
3. **Eco de datos personales breves:** «Me llamo Ana.», «Mi hijo tiene asma.». Choca con la promesa del preregistro, aunque la puerta 5 se cumpla.
4. **Cifra de la tabla:** 74 % (69/93) en el preregistro, frente al 67 % (100/149) de la tabla implementada.
5. **Reproducibilidad de dos cifras:** el 611/630 del renombrado no sale de ningún guion en git. `g58_evaluar.py` no puede ejecutarse sobre `freeze-G-58r` porque exige el árbol de `freeze-G-58`. Las cifras de G-58r dependen de la identidad con `sin_seguimiento`, que aquí queda comprobada.
6. **Veredictos crudos del juez de G-57** comprometidos con el código de G-58. Se comprobó que no cambiaron.
7. **La prueba del seguimiento marcada como fallo esperado** por una retirada, no por un límite abierto.

## Órdenes usadas

En la copia, con `PYTHONHASHSEED=0` y `PYTHONPATH=<copia>` para el evaluador:
- `python3 -m experiments.g57_educar_kiosco base_freeze_g55r.json m.json`
- `python3 -m experiments.g57_calibrar_kiosco m.json c.json results_v3/kiosco/desarrollo/A … D`
- `python3 -m experiments.g58_calibrar_cercano c.json b.json`
- `python3 experiments/g57_kiosco.py b.json r_hs{0,1}.json results_v3/kiosco/congelado_g58/V1 … V6 --respuestas`, también con `--reinicio`, `--otro-negocio` y `--renombrar --estricto`
- `python3 -m experiments.g58_juez reunir results_v3/kiosco/evaluacion_g58 results_v3/kiosco/evaluacion_g58/juez p.json`
- `python3 -m experiments.g57_juez reunir results_v3/kiosco/evaluacion_g57 results_v3/kiosco/evaluacion_g57/juez p57.json`
- `python3 -m experiments.regression_batches`

Los guiones auxiliares de la auditoría (desglose, muestra, citas, cobertura y sonda del eco) están en la carpeta temporal del auditor, fuera del repositorio.

## En palabras fáciles de entender

Revisé por mi cuenta el último cambio del «kiosco»: el programa que contesta a los clientes de un negocio usando solo el texto que el negocio le da. El cambio consiste en esto: cuando el programa no está seguro, ya no se queda callado siempre. Copia el trozo del texto que más se parece a la pregunta y avisa: «No lo tengo seguro. Lo más cercano que dice el texto es…». Si no tiene nada que valga la pena, dice «No lo sé».

Repetí todo desde cero y salieron exactamente los mismos números que el equipo había anotado. Ese trozo copiado le sirve al cliente en casi una de cada cuatro preguntas; antes no le servía en ninguna. El programa nunca se inventa nada. Solo 6 de cada 152 trozos copiados podrían confundir al cliente. No encontré trampas: el programa no guarda respuestas del examen ni reglas hechas a la medida de un negocio. Leí yo mismo 30 notas del evaluador y estoy de acuerdo con 29.

También encontré cosas que hay que decir con claridad. Casi tres de cada cuatro preguntas todavía terminan en «No lo sé». Incluso cuando acierta, el programa suena inseguro. A veces copia solo un título, como «FORMAS DE PAGO», o una frase suelta que lleva a error. Si alguien escribe «Me llamo Ana», el programa puede contestar «Me llamo Ana.», como si repitiera lo que oye. Y cuando le dan el texto de otro negocio, casi un tercio de lo que copia confunde. Se puede usar como versión estable. Pero antes hay que hacer las mediciones de rutina que faltan y anotar estos defectos. Todavía no está listo para atender clientes de verdad sin una persona al lado.
