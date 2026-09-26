# G-57 — el kiosco: contestar con la unidad del documento, un puente de vocabulario contado y un silencio calibrado

Fecha: 2026-09-26. Preregistro previo al código. Base: `estable-G-15` (árbol `ef07ab31`). Prioridad del usuario escrita en `MISION.md` (sección 2, «Prioridad actual»). Guía: plan 1 del investigador de la sesión coordinadora (`leobotFinal/coordinacion/planes/2026_plan_1.md`), propuestas 1 y 2, y la parte de seguimiento de la 3.

## Fallo medido

- Examen privado de kiosco de la sesión coordinadora (3 negocios, 67 preguntas, no leído): `estable-G-15`, con la información contada como conversación, contesta bien **1 de 54** preguntas con el dato en el texto y acierta las 13 que deben ser «no lo sé». No inventa, pero casi no encuentra nada.
- Sonda propia de diagnóstico (un hotel de 20 líneas escrito por mí; no cuenta como medida): con `ingest_document_text` y `respond`, 4 de 8 preguntas con dato bien respondidas. Se pierden las cifras («$250.000 por noche» → «250»), el dato que está en otra línea que su título («Dirección: …» a «¿Dónde queda?» → «Andina») y las paráfrasis («perro» → «mascotas»).

Causas en el código (el investigador las señala y las compruebo):
1. La búsqueda exige que la oración contenga todas las palabras de contenido de la pregunta (`answer_by_structure`).
2. La unidad es la oración: se pierden el título de la sección, el nombre de la columna de una tabla y la pregunta de una sección de preguntas frecuentes.
3. La respuesta se recorta a un tramo: el recorte falla (F1 de tramos 0,24 desde hace muchos ciclos) y un kiosco no lo necesita.
4. No hay una interfaz para cargar el negocio y responder con historial; un turno con saludo y pregunta devuelve un mensaje interno («Procesé 2 segmentos del documento en orden.»).

## Cambio (5.8)

Módulo nuevo `leobot/context.py` (mezcla `ContextMixin` de `Bot`). Es una capacidad general de lectura: sirve para cualquier documento, no solo para negocios.

**1. Interfaz.**
- `Bot.load_context(text, instructions='')` parte el texto en unidades y las indexa. Las instrucciones se guardan aparte: en G-57 no se usan para contestar, se miden.
- `Bot.answer(question, history=None)` devuelve `{'text', 'status', 'evidence', 'confidence'}`. `status` es `answered`, `unknown` o `phatic`.
- Nunca devuelve un mensaje interno.

**2. Unidades por la forma del texto, sin palabras escritas a mano.** Convenciones de formato (como el corte por líneas de `document.py`):
- línea no vacía;
- elemento de lista (guion, asterisco, viñeta, número con punto o paréntesis), sin la marca;
- fila de tabla (celdas separadas por `|` o tabulaciones), con la primera fila de la tabla como nombres de columna, guardada como «columna: valor»;
- la línea larga se parte en oraciones con el separador que ya existe.

Cada unidad guarda el **título** que la gobierna: la línea corta anterior sin puntuación final, la línea que termina en «:» sin nada después, o una línea que es una pregunta (sección de preguntas frecuentes). La primera línea del documento es el título del documento. Interruptor `unit_headings`.

**3. Búsqueda por razón de verosimilitud aprendida.** Cada palabra se reduce a su lema aprendido de AnCora (G-44). Para cada palabra q de la pregunta y cada unidad u:
- si q está en u (o en su título), suma log(π(q) / p₀(q));
- si no está, suma log((1 − π(q)) / (1 − p₀(q))).

Aquí:
- π(q) es la probabilidad **contada** de que la respuesta contenga una palabra que la pregunta contiene, en los pares pregunta–respuesta de MFAQ en español (`train`, 475 307 pares de 75 099 páginas escritas por personas; cada par se cuenta una vez por dominio web);
- p₀(q) es la fracción de unidades del documento que contienen q, suavizada.

Las palabras interrogativas y gramaticales pesan poco sin ninguna lista: su π es bajo. Las palabras que no se vieron en MFAQ toman el π medio de las palabras raras (también contado).

**4. Puente de vocabulario contado** (interruptor `bridge`). Si q no está en u pero hay una palabra a de u asociada a q, se usa la asociación en lugar de la ausencia: log(P(a en la respuesta | q en la pregunta) / P(a en la respuesta)). La asociación se cuenta en los mismos pares de MFAQ, una vez por dominio, y se poda así:
- apoyo ≥ 20 dominios;
- elevación ≥ 4;
- como mucho 12 palabras por q.

**5. Silencio calibrado** (interruptor `calibrated`). La mejor unidad se contesta solo si su celda de calibración lo permite. La celda la fijan dos rasgos:
- el mayor π entre las palabras de la pregunta que la unidad no cubre (5 tramos);
- la ventaja sobre la segunda unidad (5 tramos).

Cada celda guarda la precisión **contada** en páginas de MFAQ `train` de dominios que no se usaron para π ni para el puente (10 % de los dominios, elegido por el resumen del nombre del dominio). En esas páginas:
- el documento son las respuestas partidas en oraciones, y se quita la mitad de las respuestas;
- las preguntas son las de la página;
- es correcta una oración de la respuesta de esa pregunta; con la respuesta quitada, lo correcto es callar.

Las celdas se admiten en orden de precisión mientras la cota superior de Clopper–Pearson al 95 % del error acumulado entre lo contestado no pase del **2 %** (idea de «aprender y luego probar», Angelopoulos et al.). Si no se admite, el estado es `unknown` y el texto es la abstención del motor. En G-57 no se cita ninguna instrucción.

**6. Qué se contesta.**
- El texto de la unidad tal como está en el documento, sin la marca de lista.
- Se antepone el título si alguna palabra de la pregunta solo se encontró en el título.
- La fila de una tabla se da como «columna: valor; …».
- No se recorta ni se genera texto.

**7. Seguimiento** (interruptor `follow_up`). Si la pregunta no se admite sola y el historial trae una pregunta anterior del cliente, se busca otra vez con las palabras de las dos. Se contesta solo si la celda se admite.

**8. Turno sin pregunta ni contenido** (saludo, gracias, despedida: ninguna palabra con π ≥ el π medio y ninguna interrogativa aprendida). Estado `phatic`: se devuelve el mismo saludo de la persona, con el principio general de reciprocidad y sin lista de saludos. Si el turno trae además una pregunta, se contesta la pregunta y se antepone el saludo.

**9. `respond` sin mensaje interno.** Un turno de varias partes devuelve la respuesta a la última parte que es pregunta, o a la última parte si ninguna lo es. El mensaje «Procesé N segmentos…» desaparece.

**Por qué no bastan los mecanismos actuales.** Exigen todas las palabras en una oración, recortan tramos y no conocen títulos, columnas ni paráfrasis de clientes (causas 1 a 3).

**Qué experimento distingue.** El banco de kiosco congelado, con cada interruptor apagado y los controles de abajo.

**Qué se elimina si funciona.** Nada todavía: `respond` sigue para la conversación general, y la interfaz nueva es la vía del documento cargado. Si el puente o el silencio calibrado no aportan, se retiran (5.9).

## Educación (fuera del motor)

`experiments/g57_educar_kiosco.py` añade `context_model` a la base de `estable-G-15`, contando en MFAQ `es` `train` (SHA-256 `c985eb09…`, descargado de `huggingface.co/datasets/clips/mfaq`):
- π y el π de las palabras raras;
- el puente;
- la tabla de calibración.

Todo es conteo; no hay gradiente ni redes. MFAQ son páginas web escritas por personas. Solo se cuentan palabras: no se guarda ningún texto de MFAQ en la base.

## Medida

Congelado `freeze-G-57`; la semilla sale de su huella.

**A. Banco de kiosco congelado.** Redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), al menos 4, de al menos 3 modelos distintos. Escriben después del congelado:
- al menos 24 negocios de al menos 12 sectores **distintos de los de desarrollo**, de varios países;
- `negocio.txt`, `instrucciones.txt` y conversaciones con clave y evidencia literal;
- 25 % sin respuesta, con el mismo encargo neutral de desarrollo (`results_v3/kiosco/encargo_redactor.md`).

Los redactores no reciben este preregistro, mensajes del usuario ni ejemplos. El banco entra a git antes de ejecutar nada.

**Juez ciego.** Jueces nuevos califican cada turno sin saber qué sistema contestó, en una de estas categorías:
- correcta y respaldada;
- abstención o derivación correcta;
- incompleta;
- equivocada;
- inventada;
- abstención indebida.

El conteo automático (clave contenida y estado) se reporta al lado.

**B. MFAQ `valid`** (390 páginas, texto de personas, nunca usado para educar). Mismo montaje que la calibración, con la mitad de respuestas quitada según la semilla del congelado. Se reportan:
- acierto entre lo contestado;
- cobertura de las preguntas con respuesta;
- silencio en las quitadas.

**C. Pruebas generales, que no pueden retroceder:**
- material de conversación de G-55 (reserva cuádruple 123, referencias 48, charla 64) con `respond`: ≥ 158, lo de `estable-G-15`;
- SQuAD-es 2400 casos nuevos: F1 no más de 0,005 por debajo de `estable-G-15`;
- tablero: MLQA fresco y sonda;
- latencia fija de la regla 5.6;
- regresión completa.

**Latencia del kiosco:** p95 de `answer` con cada documento del banco cargado.

**Controles:**
- cada interruptor apagado (`unit_headings`, `bridge`, `calibrated` —contesta siempre la mejor unidad—, `follow_up`);
- puente barajado (las asociaciones se reasignan al azar entre palabras);
- documento de otro negocio (las preguntas de un negocio contra el texto de otro);
- renombrado total de los nombres propios en documento y preguntas (la respuesta debe ser la misma con el nombre cambiado);
- reinicio (guardar y cargar: respuestas idénticas);
- `estable-G-15` con el mismo documento (`ingest_document_text` + `respond`);
- bot sin educación de kiosco (`context_model` vacío).

**Tamaño:** con unos 600 turnos, un cambio de 15 puntos en ~300 preguntas con respuesta es muy superior al error típico (~2,9 puntos).

## Umbrales de éxito (banco congelado, juez)

1. Preguntas con respuesta de tipo `directa` y `si_no`: **≥ 50 %** correctas y respaldadas, y **≥ 15 puntos** sobre `estable-G-15`.
2. Entre todo lo contestado: equivocadas + inventadas **≤ 4 %**; inventadas **0**. El diseño apunta al 2 %; el margen cubre el ruido del tamaño.
3. Preguntas sin respuesta: calladas o derivadas **≥ 80 %**.
4. Controles:
   - otro negocio: ≤ 5 % de aciertos y ≥ 80 % de silencio;
   - renombrado: ≥ 95 % de respuestas invariantes;
   - reinicio: 100 %.
5. Pruebas generales sin retroceso (C) y latencia: p95 de `answer` ≤ 10 ms; el resto de la regla 5.6.

**Retención (5.9):**
- el puente se queda si suma ≥ 3 puntos en (1) sin subir (2) más de 1 punto, y no baja el acierto entre lo contestado en MFAQ `valid`;
- los títulos se quedan si suman ≥ 3 puntos en (1);
- el silencio calibrado se queda si baja (2) al menos a la mitad frente a contestar siempre, sin perder más de 10 puntos en (1);
- el seguimiento se queda si suma en `seguimiento` sin subir (2).

Se reportan aparte, sin puerta, los tipos que G-57 no ataca: combinada (cuentas), instrucción y charla.

## Presupuesto

Educación ≤ 30 min con hasta 16 procesos y RAM total ≤ disponible − 2 GB. Evaluación ≤ 1 h. Desarrollo con material escrito por 6 redactores antes del congelado:
- 4 partes abiertas (A–D), que puedo leer;
- 2 partes ciegas (E, F): solo miro los totales.

## Enmienda previa al congelado (2026-09-26, desarrollo con las partes A–D abiertas y E–F ciegas)

Todo lo de abajo se decidió con el material de desarrollo, antes de `freeze-G-57`. Las puertas no cambian.

**1. La verosimilitud es una mezcla, no π/p₀.** Con π/p₀, las palabras presentes en casi toda respuesta («ser») pesaban como contenido: «¿Cuál es su horario?» → «Somos un restaurante…». Ahora el modelo es de mezcla:
- δ(q) = (π(q) − P_A(q)) / (1 − P_A(q)), donde P_A es la fracción de respuestas de MFAQ que contienen q; δ es la probabilidad de que la respuesta tenga q *porque* la pregunta la tiene;
- presente: log(δ/p₀ + 1 − δ); ausente: log(1 − δ);
- el puente usa el mismo δ con P(a | q);
- el rasgo de calibración usa el mayor δ no explicado.

**2. El título del documento** no entra en los índices (sus palabras estaban en todas las unidades y anulaban la búsqueda): sus palabras cuentan como explicadas en todas.

**3. Los títulos también son unidades.** Si la pregunta da con un título, o con una unidad solo a través de su título, se contesta la **sección** entera (hasta 8 unidades). Es título, además de la línea corta seguida de contenido:
- una línea en mayúsculas o que termina en «:» (tipografía);
- la pregunta de una sección de preguntas frecuentes, cuya respuesta termina en la línea en blanco.

**4. Lemas sin tildes y reglas de terminación.** El lema aprendido de AnCora se busca sin tildes («cuanto», «alcoholicas»). Las palabras que AnCora no vio toman la regla de terminación inducida de sus anotaciones: la que sigue al menos el 80 % de 20 o más formas con esa terminación.

**5. Forma de las cifras** como palabra más: «9», «9:9», «9.9», «9,9», «$», «€», «£» y «%». El puente contado aprende así que «cuánto» pide «$» y que «hora» pide «9:9».

**6. Las oraciones solo se parten** tras una palabra de 4 o más letras, una cifra o un cierre. No se parte tras «Av.» ni tras puntos de relleno.

**7. Calibración.**
- **Con MFAQ no se admite ninguna celda:** la mejor acierta el 84 % (páginas de viajes con plantilla y respuestas casi iguales). Resultado negativo registrado; las cuentas quedan en `cells_mfaq`.
- **La tabla se cuenta en las partes abiertas del banco de desarrollo (A–D)**, con la misma regla (Clopper–Pearson al 95 %, error acumulado ≤ 2 %). Ese texto lo redactaron modelos de lenguaje; se declara, y solo se guardan cuentas por celda.
- **Tampoco se admite ninguna celda:** la mejor acierta el 79 % (391 turnos, conteo automático).
- **Otros rasgos probados en A–D, sin ninguno que aísle un grupo fiable:**
  - fracción de δ explicada;
  - estabilidad al quitar cada palabra;
  - todas las palabras de δ alto explicadas.

  Lo mejor fue un 92 % en solo 12 casos.
- **Consecuencia (se mantiene la meta):** el motor congelado contesta `unknown` («No lo sé…») a toda pregunta con contenido. La interfaz entrega aparte, en `candidate`, la mejor unidad y la precisión contada de su celda, sin afirmarla.
- **El experimento mide la búsqueda con el control «contesta siempre»** (`calibrated` apagado), y la regla de retención 5.9 del silencio calibrado se aplica como está escrita.

**8. `respond`** devuelve la respuesta a la última parte que es pregunta, o a la última parte. El resto del resultado se conserva (`sentences`, `total`) y el estado del documento va en `document_status`.

**Cifras de desarrollo, conteo automático** (clave contenida; subestima: una respuesta buena a la que le falta una clave de otra línea cuenta como equivocada):

| Sistema | Abiertas A–D: directa + sí/no | Ciegas E–F: directa + sí/no |
|---|---|---|
| `estable-G-15` (`ingest_document_text` + `respond`) | 5/181 | 5/95 |
| G-57, contestando siempre | 103/181 (57 %) | 55/95 (58 %) |

- Error entre lo contestado, contestando siempre: 65 % en A–D (incluye las 112 preguntas sin respuesta).
- `estable-G-15` se equivoca en el 96,5 % de lo que contesta en A–D y en el 93 % en E–F.
- p95 de `answer`: 0,16–0,27 ms.

Lo ganado en la parte abierta se sostiene en la ciega: 57 % frente a 58 %.

## Resultado (2026-09-26, banco congelado de 24 negocios y 629 turnos; juez ciego de 11 jueces nuevos, Opus)

**Puertas (juez) · G-57 congelado, con el silencio calibrado:** no se admite ninguna celda, así que calla siempre.

| Puerta | Umbral | Resultado | ¿Pasa? |
|---|---|---|---|
| 1. Directa + sí/no correctas | ≥ 50 % y ≥ 15 puntos sobre `estable-G-15` | 0/276 | **no** |
| 2. Error entre lo contestado | ≤ 4 %, 0 inventadas | nada contestado | vacía |
| 3. Sin respuesta calladas | ≥ 80 % | 166/166 | sí |
| 4. Otro negocio | ≤ 5 % de aciertos y ≥ 80 % de silencio | 1/413 contestando siempre (100 % de silencio con el tratamiento) | sí |
| 4. Renombrado | ≥ 95 % invariantes | 552/629 (87,8 %) | **no** |
| 4. Reinicio | 100 % idénticas | 629/629 | sí |
| 5. Pruebas generales y latencia | sin retroceso; p95 de `answer` ≤ 10 ms | sin retroceso; 0,34 ms | sí |

**G-57 no supera sus puertas.**

Detalles de las puertas 4 y 5:
- **Renombrado.** El control, heredado de G-45, renombra palabras con mayúscula que no abren la línea. En textos de negocio eso incluye «No», «Si», «Precio», «Sábados» y «Hola»: 47 palabras por negocio. Como diagnóstico posterior, no preregistrado, un renombrado estricto (solo palabras que nunca aparecen en minúscula, 31 por negocio) da 607/629 (96,5 %).
- **Pruebas generales:**
  - conversación de G-55: 101/21/36 = 158, igual que `estable-G-15`;
  - SQuAD-es: 1570 casos, los únicos que quedaban (el preregistro decía 2400). F1 0,2485 frente a 0,2483;
  - tablero MLQA fresco 0/20 y sonda 0/4, sin cambios;
  - regresión 657/3/0;
  - latencia intercalada: p95 entre −6,9 % y +11,7 %; RAM 220 MB.

**Control «contesta siempre» (juez):**
- **140/276 (50,7 %)** directa + sí/no correctas; `estable-G-15` 8/277 (2,9 %), es decir, +47,8 puntos;
- 578 contestadas: 194 correctas, 43 incompletas, 341 equivocadas y **0 inventadas** (59 % de error entre lo contestado);
- 0/166 sin respuesta calladas.
- `estable-G-15`: 237 contestadas con 91,6 % de error, **2 inventadas**, 126/166 calladas y 1 excepción (`ValueError` en `reading._subordinate`: defecto de `respond`).

**Otras medidas generales de lectura:**
- MFAQ `valid`, contestando siempre: cobertura 56,8 % (sin puente 56,3 %; puente barajado 54,6 %).
- SQuAD-es: la mejor unidad contiene la respuesta en el **79,9 %** de 1570 casos (p95 0,15 ms).

**Retención 5.9.** El juez califica las respuestas que cambian (203 respuestas distintas); las demás heredan su veredicto.

| Pieza | Aporte (juez) | Error entre lo contestado sin ella | Decisión |
|---|---|---|---|
| Puente | +5,4 puntos (140 frente a 125) | 61,9 % (con él, 59,0 %); MFAQ `valid` no baja | **se queda** |
| Títulos (términos del título, secciones y título antepuesto) | +1,4 (140 frente a 136) | — | **se retira** |
| Forma de las cifras | +1,4 | — | **se retira** (sin regla preregistrada; se aplica la de los títulos, la más estricta) |
| Seguimiento | nunca actuó (solo con celdas admitidas) | — | **se retira** |

**Silencio calibrado: se conserva contra su regla de retención.** La regla pedía retirarlo, porque pierde más de 10 puntos en (1). Pero retirarlo deja el motor contestando siempre, con 0/166 silencios. Eso choca con la misión («si el dato no está, lo dice o deriva»), y manda la más estricta. Se declara.

**Cambio en `freeze-G-57r` al retirar los títulos.** La línea de pregunta de unas preguntas frecuentes deja de ser candidata: una pregunta encabeza su respuesta, nunca es la respuesta. Sin las secciones, esa línea se habría dado como respuesta (lo detectó la prueba del puente).

**`freeze-G-57r`, contestando siempre, en el banco gastado (conteo automático):** 126/277 (G-57 136). Retirar las dos piezas juntas cuesta más que cada una por separado (−10 en conteo automático); se registra.

- Regresión 657/5 esperados/0: los dos fallos esperados nuevos documentan las piezas retiradas.
- MFAQ: ninguna celda admitida.
