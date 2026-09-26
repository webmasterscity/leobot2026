# G-58 — el kiosco con honestidad graduada: responder, citar lo más cercano avisando de la duda, o decir que no se sabe

Fecha: 2026-09-26. Preregistro previo al código. Base: `freeze-G-57r` (árbol `15cfba45`). Prioridad del usuario en `MISION.md` («Prioridad actual»). Guía:
- las ideas de la sesión coordinadora tras medir `freeze-G-57` en el examen privado del usuario (solo cifras): un modo «cita» y elegir el punto de operación según la curva;
- el plan 2 del investigador, en la parte de preguntas completadas con el turno anterior y estado por cliente.

## Fallo medido

**G-57 (juez, banco congelado de 24 negocios):** con silencio calibrado al 2 % no se admite ninguna celda, y calla siempre: 0/276 útiles. Contestando siempre acierta 140/276, pero contesta mal el 59 % de lo que dice y no calla ninguna de las 166 sin respuesta. En el examen privado, lo mismo: 0/54 tal cual.

**Rasgos probados en el banco de G-57, ya gastado (557 respuestas con veredicto del juez):**

| Rasgo | Precisión |
|---|---|
| Ventaja ≥ 8 sobre la segunda unidad | 84 % (19 casos) |
| Ventaja ≥ 4 | 67 % |
| Otros (δ sin explicar, cobertura, palabras de δ alto) | por debajo |

**Ningún rasgo acerca al 98 %:** la búsqueda por palabras no sabe con certeza cuándo acertó. Pero la unidad más cercana sí es útil muchas veces:
- en las celdas donde el juez la da por correcta o incompleta en al menos la mitad de los casos, sirve en el 74 % (69 de 93);
- solo muestra algo en 18 de las 166 preguntas sin respuesta.

**Otros dos defectos:**
- El eco de G-57 devuelve cualquier turno sin pregunta y sin palabras del documento, aunque lleve datos personales («Me llamo Ana y mi tarjeta es…» → lo repite).
- El seguimiento de G-57 nunca actuó, porque solo aceptaba celdas admitidas y no había ninguna.

## Cambio (5.8)

Todo en `leobot/context.py`. Es una capacidad general de autoconocimiento: decir con qué seguridad se sabe algo y no afirmar más de lo que se sabe.

**1. Tres niveles de respuesta** (interruptor `closest`):
- `answered`, respuesta plana: solo en celdas admitidas con la regla de G-57 (Clopper–Pearson 95 %, error acumulado ≤ 2 %).
- `closest`, lo más cercano avisando de la duda: en las celdas donde lo más cercano es útil al menos la mitad de las veces (correcta o incompleta según el juez), con al menos 5 casos. El texto es «No lo tengo seguro. Lo más cercano que dice el texto es: «…».» Solo se cita texto del documento. La frase de aviso es voz del motor, como «No lo sé»: no depende del negocio ni de la pregunta.
- `unknown`: «No lo sé…» en el resto. La candidata va aparte, como en G-57.

La tabla por celda se cuenta en el banco de G-57, ya gastado: 629 turnos redactados por modelos de lenguaje y calificados por el juez. Se declara, y solo se guardan cuentas por celda.

**2. Seguimiento** (interruptor `follow_up`, reintroducido con otro disparo). Si la pregunta sola queda en `unknown` y el historial trae un turno anterior del cliente que pregunta, se busca de nuevo con las palabras de los dos. Se usa si la celda resultante es `closest` o `answered`. El seguimiento de G-57 se retiró por no actuar nunca; este puede actuar.

**3. Eco solo de saludos cortos** (interruptor `short_echo`). Un turno sin pregunta y sin palabras del documento se devuelve solo si tiene como mucho 4 palabras y ninguna cifra. Si no, se trata como pregunta: nunca se repiten datos de la persona.

**Qué se elimina si funciona:** nada. El silencio calibrado de G-57 queda como el nivel `answered`.

## Medida

Congelado `freeze-G-58`; semilla de su huella.

**A. Banco congelado nuevo.**
- 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), de 4 modelos (Opus, Sonnet 5, Haiku 4.5, Fable 5.1), después del congelado.
- 24 negocios de 24 sectores distintos de los de desarrollo y de G-57, de varios países.
- El mismo encargo neutral (`results_v3/kiosco/encargo_redactor.md`).
- En git antes de ejecutar.

**B. Juez ciego** (jueces nuevos, Opus). Califica G-58 y los controles que cambian respuestas, mezclados y sin decir qué sistema contestó:
- respuesta plana: `correcta`, `incompleta`, `equivocada`, `inventada`;
- cita avisada:
  - `util`: el texto citado responde lo pedido o su parte principal;
  - `honesta`: no lo responde, pero el aviso deja claro que no es el dato y nada engaña;
  - `enganosa`: aun con el aviso, llevaría al cliente a creer algo falso;
- «No lo sé»: se califica solo (correcta si la acción esperada es abstenerse o derivar).

## Umbrales de éxito (banco congelado, juez)

| Puerta | Umbral |
|---|---|
| 1. Útiles en directa + sí/no (plana correcta o cita `util`) | ≥ 20 % (G-57: 0 %; desarrollo: 25 %) |
| 2. Respuestas planas equivocadas + inventadas | ≤ 2 % |
| 2. Inventadas en todo el banco | 0 |
| 3. Sin respuesta: «No lo sé», o cita `honesta` o `util` | ≥ 90 % |
| 4. Citas `enganosa` | ≤ 15 % de las citas |
| 5. Eco de turnos con cifras o más de 4 palabras | 0 |

**6. Controles:**
- documento de otro negocio: citas `util` ≤ 5 % y «No lo sé» ≥ 80 %;
- reinicio: 100 % idénticas;
- renombrado **estricto** (solo palabras que nunca aparecen en minúscula en el negocio; se corrige el control de G-57, que renombraba «No» o «Precio»): ≥ 95 % invariantes;
- sin `closest` (debe dar 0 útiles);
- sin seguimiento (el seguimiento se queda si suma citas útiles en `seguimiento` sin subir las `enganosa`);
- tabla barajada (las cuentas de las celdas se reasignan al azar): debe dar menos útiles o más engañosas.

**7. Pruebas generales sin retroceso:**
- conversación de G-55: 158;
- SQuAD-es: los mismos 1570 casos que G-57, solo como regresión (no quedan casos nuevos en `dev`);
- tablero y sonda;
- regresión completa;
- latencia 5.6: p95 de `answer` ≤ 10 ms.

**Retención 5.9:**
- `closest` se queda si pasa las puertas 1, 3 y 4;
- `short_echo`, si la 5;
- el seguimiento, según su control.

## Presupuesto

Implementación ≤ 1 h; banco y juez ≤ 1 h; medidas generales ≤ 30 min. Hasta 16 procesos, con al menos 2 GB de RAM libres.

## Resultado (2026-09-26, banco congelado de 24 negocios nuevos y 630 turnos; juez ciego de 8 jueces nuevos, Opus)

| Puerta | Umbral | G-58 | ¿Pasa? |
|---|---|---|---|
| 1. Útiles en directa + sí/no | ≥ 20 % | **65/266 (24,4 %)** (G-57r: 0 %) | sí |
| 2. Respuestas planas | error ≤ 2 % | ninguna (ninguna celda admitida) | vacía |
| 2. Inventadas en todo el banco | 0 | **0** | sí |
| 3. Sin respuesta bien llevadas | ≥ 90 % | **169/174 (97,1 %)**: 114 «No lo sé» y 55 citas honestas o útiles | sí |
| 4. Citas engañosas | ≤ 15 % | **9/212 (4,2 %)**; el 48 % de las citas son útiles | sí |
| 5. Ecos de turnos con cifras o de más de 4 palabras | 0 | **0** (G-57r: 3) | sí |

**6. Controles:**
- otro negocio: 0 útiles y 84 % de «No lo sé» (pasa). Aun así, 22 de sus 97 citas son engañosas.
- reinicio: 630/630 idénticas;
- renombrado estricto: 611/630 (97,0 %);
- sin `closest`: 0 útiles;
- tabla barajada: 22/266 útiles (8,3 %) y 19,6 % de citas útiles. La tabla contada importa.

**7. Pruebas generales:**
- conversación de G-55: 101/21/36 = 158, sin cambios;
- regresión 661/5/0;
- p95 de `answer`: 0,46 ms.

**G-58 supera sus puertas.**

**Retención 5.9:**
- `closest` se queda (puertas 1, 3 y 4);
- `short_echo` se queda (puerta 5);
- **el seguimiento se retira.** En las preguntas de seguimiento suma citas útiles (13 → 18), pero sube las engañosas (1 → 3), y la regla pedía no subirlas. En todo el banco: útiles 62 → 65 y engañosas 6 → 9.

**`freeze-G-58r` = G-58 sin seguimiento.** Sus respuestas en el banco son idénticas (630/630) a las de la variante `sin_seguimiento` ya juzgada, así que sus cifras con el juez son esas:
- útiles 62/266 (23,3 %);
- sin respuesta 169/174 (97,1 %);
- engañosas 6/152 (3,9 %);
- inventadas 0;
- ecos 0.

Pasa las mismas puertas. La base no cambia (`1c0db7a6`): la tabla de lo más cercano ya se contó sin seguimiento.

## Verificación independiente 5.10 (auditor nuevo, Opus, copia aislada; [informe](../results_v3/auditoria_g58r.md))

**Confirmado:**
- orden en git;
- base idéntica (`1c0db7a6…`), sin texto de los bancos, con la tabla contada solo en el banco de G-57;
- respuestas de `freeze-G-58r` idénticas a `sin_seguimiento` con `PYTHONHASHSEED` 0 y 1; reinicio 630/630;
- puertas del juez reproducidas byte a byte; el auditor coincide en 29 de 30 veredictos revisados a mano;
- regresión 661/6/0;
- sin hardcodeo ni filtraciones; la frase de aviso es voz del motor aceptable.

**Objeciones, declaradas aquí:**
1. **Medidas generales de `freeze-G-58r`:**
   - latencia intercalada con `estable-G-16`: p95 entre −1,5 % y +1,0 %, RAM 220 MB (commit 196727b);
   - tablero MLQA fresco 0/20 y sonda 0/4;
   - SQuAD-es no se volvió a correr: `dialogue.py` y `reading.py` no cambiaron desde `freeze-G-57` (la diferencia en `leobot/` entre `freeze-G-57` y `freeze-G-58r` está solo en `context.py`), así que vale el F1 de 0,2485.
2. **Con el texto de otro negocio, el 28,8 % de las citas de G-58r engañan.** El control pasa por sus umbrales (0 útiles y 84 % de «No lo sé»), pero cuando cita, cita cosas que confunden.
3. **El eco todavía repite datos personales breves** («Me llamo Ana» → «Me llamo Ana.»). La puerta 5 solo mide turnos con cifras o de más de 4 palabras.
4. **La tabla de lo más cercano es menos útil de lo anunciado:** el preregistro dice 74 %, la tabla contada da 67 % y, fuera de muestra, 59,9 %. Aun así supera el umbral del 50 %.
5. **Lejos de un kiosco real:**
   - el 71,5 % de las preguntas con respuesta acaban en «No lo sé»;
   - todo lo útil llega con duda;
   - hay citas que son solo un título (G-59 lo ataca) o una respuesta sin su pregunta;
   - una tabla sin encabezado mezcla precios.
