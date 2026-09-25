# Auditoría 5.10 — ¿`freeze-G-55r` puede pasar a `estable-G-15`?

Encargo de tipo auditor. Fecha: 2026-09-25, de 08:04 a 08:27 (unos 23 minutos).
- Auditor: subagente nuevo de Claude (Opus), en un worktree aislado con el HEAD en `1392e24`. El motor de ese commit es `ef07ab31…`, igual al de `freeze-G-55r`.
- No se modificó `leobot/` ni ninguna prueba, y no se hizo ningún commit ni tag. La huella del motor y el árbol quedaron iguales antes y después de cada ejecución.
- Scripts y salidas: `…/scratchpad/aud55r/` (`medida_55r.json`, `semilla1.json` y los registros de ejecución).

## Veredicto: **confirma**, con las salvedades de abajo

- **Cifras.** Reproduje exactas todas las que se me pidieron: la base, byte a byte; 101/21/36; 100 sin `kind_contrast`; y la regresión.
- **Sin trampas.** No hay hardcodeo ni filtración del material nuevo.
- **Diferencia con `estable-G-14`.** En las 235 preguntas nuevas, `freeze-G-55r` responde distinto en **una sola**, que ahora acierta. No hay ninguna regresión.
- **Qué es el tag.** Es una consolidación, no un avance de fase: las puertas de G-55 y de G-56 **no se superaron**, y eso tiene que quedar dicho.
- **Antes del tag conviene arreglar cuatro cosas** (detalle en las secciones siguientes):
  - una desviación del preregistro de G-55 que no se declaró;
  - un defecto de los conectores aprendidos;
  - tres huecos de trazabilidad;
  - una prueba que se borró cuando debió quedar como fallo esperado.

## 1. Cifras guardadas frente a reproducidas

| Qué | Guardada | Reproducida |
|---|---|---|
| SHA-256 de la base (motor 55r, `PYTHONHASHSEED=0`) | `8d27a05c…` (declarada en el encargo; **no figura en el repositorio**) | `8d27a05c80082544ca7815953f0bd7408860c9fa8b942144cbee598a4bc59183`: **igual**, y también igual a `scratchpad/base_freeze_g55r.json`. Tiempo: 222 s de CPU; memoria pico 443 MB |
| Reserva cuádruple: tratamiento, sin `role_check`, sin `kind_contrast` | 101 / 101 / 100 | **101 / 101 / 100**. «no» 14/22 frente a 13/22; afirma lo falso 1 en las tres |
| Referencias doble: las mismas tres variantes | 21 / 21 / 21 | **21 / 21 / 21** |
| Charla doble: las mismas tres variantes | 36 / 36 / 36 | **36 / 36 / 36** |
| Respuestas de 55r frente a las de `estable-G-14` (en `scratchpad/g55/g14_*.json`) | 100 / 21 / 36 = 157 | 1 respuesta distinta de 235: «¿Consuelo vende huevos los domingos?». Antes «No lo sé», ahora «No: …los sábados» (clave: no) |
| Con `PYTHONHASHSEED=1` | — | 235/235 respuestas idénticas a las de la semilla 0 |
| Regresión completa | 642 / 2 / 0 (169 s) | **642 / 2 / 0 (168,2 s)** |
| Pruebas rápidas + `test_g55_g56` + `test_g54_conversation` | — | 23, todas pasan |
| Renombrado y reinicio de 55r (116/48/64 y 100 %) | guardados | **no los repetí** (por tiempo) |
| Latencia y tablero | guardados | **no los repetí** |

## 2. Hardcodeo (regla 5.7)

**Resultado: no encontré ninguno.** Revisé los dos diffs desde `estable-G-14`: el que lleva a `freeze-G-55r` y el que lleva a `freeze-G-55`.
- **Literales del código.** Los únicos literales nuevos en `leobot/reading.py` y `leobot/syntax.py` son:
  - etiquetas de Universal Dependencies (UD): `nsubj`, `obj`, `iobj`, `conj`, `cc`, `advmod`, `obl`, `discourse`, `cop`…;
  - categorías gramaticales de UD (UPOS);
  - nombres de claves internas.
- **Español.** Solo aparece en comentarios y docstrings.
- **Aislamiento.** El motor no lee `experiments/`, los conjuntos ni ningún archivo de resultados.

**Lo que se usa sale de conteos**, que verifiqué en la base reconstruida:
- **Clases y miembros** (`reading.py:709-731`):
  - clases de SQuAD-es `train` con apoyo ≥ 30;
  - se descartan las clases abiertas (prueba de Good-Turing) y las que suelen llevar complemento (≥ 50 %);
  - un miembro es un par (lema, categoría) visto ≥ 2 veces.
  - Salen 40 clases cerradas, entre ellas «qué año», «qué país», «qué día», «qué color» y «qué mes».
  - Se excluyen 14 porque suelen llevar complemento, por ejemplo: «qué tipo» (2041 de 2099), «qué porcentaje» (703 de 765), «qué parte» (251 de 287) y «qué clase» (265 de 296).
- **Caso del complemento** (`possessor_case`): se aprende de las `nmod` de AnCora (`syntax.py:555-557`, ya estaba en `estable-G-14`). Sale «de».
- **Posición del complemento** (`reading.py:1546-1549`): la palabra que se mira es la que va dos posiciones después de la interrogativa. Es una suposición de estructura, no de léxico, y solo se aplica cuando la clave tiene sustantivo.
- **Conectores** (`syntax.py:216-240` y `562-563`): 33 aprendidos de AnCora.
- **Solo en `freeze-G-55`:**
  - las barreras de puntuación (conteo en AnCora);
  - las palabras opcionales (`question_presence`, contadas en SQuAD-es y MLQA).
  - La base de 55r ya no las tiene: `base_educada.py` las protege con `hasattr` (comprobado: no están `question_presence`, `barrier_counts` ni `modifier_barriers`).
- **`experiments/base_educada.py`** solo prepara texto:
  - `answer_sentence` corta por «. »;
  - comprueba el SHA de SQuAD-es;
  - usa la misma muestra de educación MLQA que G-28b.
  - No toca ningún conjunto de evaluación.

**Defectos que no son hardcodeo, pero deben registrarse:**
1. **Desviación del preregistro de G-55, no declarada** (`reading.py:785`).
   - El punto 2 exige, para comparar dos nombres propios, que «en la clase de pregunta aprendida para ese hueco los nombres propios [sean] una clase de respuesta (≥ 10 %)».
   - El código solo pide dos nombres propios con la misma preposición. Esa condición nunca se implementó (desde `ed148a9`) y la enmienda no la menciona.
   - Efecto en el material nuevo: ninguno. El +1 viene de la clase cerrada «qué día», y no hay ningún «no» falso de más.
   - Mi sonda de diagnóstico sí la usa: «¿El primo de Ana vive en Quito?» da «No» (correcto en este caso).
   - Hay que declararla en el preregistro o implementar la condición.
2. **Los conectores aprendidos incluyen días de la semana:** «domingo», «lunes», «martes», «miércoles», «viernes». Parecen restos de las fechas que encabezan las noticias de AnCora.
   - La voz quita esas palabras al comienzo de una oración si les sigue un signo de puntuación.
   - Sonda: «Domingo, el primo de Ana, vive en Cali.» y luego «¿El primo de Ana vive en Cali?» → «Sí, me contaste que el primo de Ana, vive en Cali.» Se pierde el nombre.
   - Solo afecta al texto de la voz, no a la calificación. En el material nuevo no se activó.
   - Debe quedar como resultado negativo. Un arreglo general: exigir que el conector no encabece un sustantivo.
3. **La persona del verbo coordinado** no actúa si el analizador etiqueta el verbo como sustantivo.
   - Sonda: «Me llamo Tomás y trabajo en…» → «te llamas Tomás y trabajo en…».
   - Es un límite, no una regresión.

## 3. Procedimiento

- **Los preregistros preceden al código.**
  - G-55 en `521e266` (00:53:50) y G-56 en `4f3911e` (01:55:24); el primer código es `ed148a9` (02:01:25).
  - `git log -S` lo confirma: `kind_contrast` y `_roles_swapped` aparecen por primera vez en código en `ed148a9`; los conectores y la persona coordinada, en `bce5920` (05:56).
  - La voz queda cubierta por el punto 6 de la enmienda de G-56.
- **Congelado.**
  - `freeze-G-55` es un tag ligero sobre `a4957c0` (06:35:23). La enmienda está **en el mismo commit**, no antes.
  - Los redactores se lanzaron después: según sus transcripciones, entre 06:38:16 y 06:38:58, con `claude-sonnet-5`.
  - Los validadores, entre 06:40:18 y 06:41:52.
  - Los conjuntos se guardaron en `9b6a021` (06:43:59). El contestador de Claude empezó a las 06:44:26, después del commit. Los resultados llegaron en `891b4d2` (07:33:00).
  - Leobot no corrió sobre el material nuevo antes de `9b6a021`. Ese commit también guarda `g55_lectura_squad_es.json`, que es otra medición (SQuAD-es) y no usa los conjuntos nuevos.
- **Los conjuntos.**
  - Los guardados en git son **idénticos byte a byte** a los del scratchpad.
  - La cuádruple es la unión de las mitades A a D validadas.
  - Sus hashes (`68d4910c…`, `bd85f08e…`, `014f40e4…`) coinciden con los de los JSON de resultados y no cambian hasta `1392e24`.
  - Las 2 claves corregidas por los validadores:
    - reserva C: «Luna» → una expresión regular que exige los dos nombres;
    - charla A: «Patricia» → «no lo sé».
- **Los encargos.** Los 8 son exactamente el encargo fijo correspondiente, más una sola línea con la ruta y la forma de responder.
  - Los encargos fijos son `validacion_comun_encargo.md`, `g47_encargo_referencias.md` y `g54_encargo_charla.md`.
  - El texto que recibió cada subagente es igual al archivo `prompt_*.txt`.
  - Ningún encargo, tampoco los de validadores y contestador, incluye el mensaje del usuario.
- **Las pruebas en la retirada** (`891b4d2`).
  - Se borran pruebas de este ciclo que nunca estuvieron en un tag estable. Son las de los mecanismos retirados.
  - La de roles gana una aserción de ablación.
  - **Objeción:** `test_a_coordinated_clause_does_not_lend_its_place` documenta la trampa que el preregistro registra como resultado negativo («Pedro nació en Bogotá y ahora vive en Medellín»). Debería conservarse como fallo esperado, no borrarse (espíritu de 5.2).
- **Trazabilidad incompleta:**
  - `results_v3/g55r_retirada_hashseed0.json` no guarda ni el hash de la base, ni la huella del motor, ni los hashes de los conjuntos. El script que lo produjo no está en git.
  - El SHA `8d27a05c…` no aparece en el repositorio.
  - Las cifras de `estable-G-14` en el material nuevo (157) solo están en `scratchpad/g55/g14_*.json`: fuera de git y sin huella.
  - `LEOBOT_STATE.md` no se actualizó después de `891b4d2` y `1392e24`.
  - Mis cifras lo respaldan todo, pero conviene guardarlo antes del tag.

## 4. Decisiones

- **Retirada de G-56.** Sigue la regla preregistrada («se retira cada punto con aporte ≤ 0 en los tres conjuntos juntos»): los cuatro interruptores dan 0. Es correcta.
- **Conservar `role_check`.**
  - Se aparta de la **letra** de la regla: en `freeze-G-55`, `_roles_swapped` dependía del interruptor `core_links`, que dio 0.
  - Es defendible como excepción declarada:
    - solo puede quitar «sí», nunca añadirlos;
    - evita una clase de «sí» falso comprobada en la prueba focal, que es el control preregistrado de roles invertidos;
    - en 55r se midió solo (sin la holgura) y es neutro en 235 preguntas;
    - la latencia está dentro de los límites;
    - hay precedente (G-52 en `estable-G-13`).
  - La única pregunta nueva con roles intercambiados («¿Ismael es el jefe de Daniela?», clave «no») da «No lo sé» con y sin la comprobación, así que no se le atribuye ninguna ganancia.
  - Debe registrarse como **«sin aporte confirmado»**.
- **Conservar `kind_contrast`.** Es compatible con 5.9:
  - aporta +1 en material nuevo, así que transfiere, aunque sea con una sola pregunta;
  - no aumenta los «afirma lo falso» (1 frente a 1) ni los errores confiados;
  - no degrada la cobertura ni cuesta más;
  - con las clases barajadas su aporte cae a 0, como pedía el control.
  - La puerta no se superó (+1 frente a +3 en total; «no» +1 frente a +5) y así debe constar.
  - Una sola pregunta no distingue efecto de ruido.
- **Correcciones de la voz.** No tienen interruptor ni ablación, y no cambiaron ninguna respuesta en el material nuevo. El preregistro las acepta «sin puerta», pero traen el defecto de los días de la semana (§2).
- **Controles que faltan:**
  - para 55r no se repitieron sin memoria, memoria barajada ni clases barajadas. Sí se corrieron en `freeze-G-55`: sin memoria 23 (solo abstenciones), y barajada igual;
  - no hay ablación de la voz ni prueba focal de la rama de nombres propios frente a la condición preregistrada;
  - la contraevidencia y la señal confundida no se justifican en G-55. Aplica la justificación de G-52: la memoria literal no retira lo dicho.

## 5. Salvedades que me pidieron valorar

1. **Nombres sustitutos añadidos al evaluador después de guardar los conjuntos** (`891b4d2`).
   - Solo cambian el control de renombrado, que antes fallaba por falta de nombres.
   - No tocan el tratamiento ni las ablaciones, y la lista es de nombres genéricos.
   - Riesgo bajo. El renombrado de 55r (116/123) no lo reproduje.
2. **Resúmenes de los validadores con contenido de la reserva.**
   - El de la reserva B citó «Daniela es la jefa de Ismael» ≠ «Ismael es el jefe de Daniela», «hermano» ≠ «padre» y temas de «no lo sé». El de la D también citó temas de «no lo sé».
   - Todo eso ocurrió después del congelado, así que el motor no pudo ajustarse a ello.
   - El único riesgo era sesgar la decisión sobre `role_check`, y en la pregunta filtrada su aporte es 0. Riesgo bajo.
3. **La última corrección de código y la enmienda están en el mismo commit** (`a4957c0`).
   - Ese código toca solo partes de G-56 que se retiraron (`_clause_head`, `_within_clause`, `named_conjuncts`). En 55r no queda nada de él.
   - Las puertas quedaron fijas antes de que existiera el material nuevo.
   - Para 55r no tiene efecto.

## En palabras fáciles de entender

- Repetí las cuentas de esta versión de Leobot desde cero y salieron **exactamente iguales**: el mismo archivo de aprendizaje, las mismas notas en los tres exámenes nuevos y las mismas 642 pruebas sin fallos.
- No encontré trampas. Lo que usa Leobot lo aprendió contando ejemplos, no se lo escribieron a mano, y los exámenes se escribieron después de congelar el programa.
- Frente a la versión anterior, solo cambia **una** respuesta de 235, y para bien. Las dos mejoras que se querían probar no llegaron a la meta fijada de antemano.
- Se puede guardar como versión estable, siempre que se diga eso claramente. Antes conviene:
  - anotar que un detalle del plan no se programó como se dijo;
  - arreglar o registrar que Leobot aprendió por error días de la semana como «muletillas»: puede borrar un nombre al repetir lo que se le contó;
  - guardar en el historial tres datos que ahora solo están en archivos temporales.
