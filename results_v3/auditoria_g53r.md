# Auditoría 5.10 de `freeze-G-53r` (candidato a `estable-G-13`)

- Auditor: subagente Claude Opus 5.5, copia aislada (worktree `agent-ac3ab01692185a81d`), 2026-09-24/25, unos 47 min.
- Encargo: auditor (regla 5.10). No se tocó `leobot/`, ni las pruebas, ni se hicieron commits o tags. Scripts y salidas en `scratchpad/aud53r/`.
- Motores: `freeze-G-52` (árbol `f3e63c7e…`, con G-49) y `freeze-G-53r` (árbol `0066ff79b18df6dbdb40dcdb82684b5c4bf27a1a`, sin G-49). Python 3.12.3.

## Veredicto

**Confirma, con salvedades**: `freeze-G-53r` puede promoverse a `estable-G-13`, a condición de corregir antes el registro del estado en un punto (salvedad 1).

- Todas las cifras se reproducen exactamente: la base, las tres conversaciones (con cada ablación y control), la lectura SQuAD-es y la regresión.
- No hay hardcodeo ni filtración del held-out al motor.
- El orden de git es correcto, y el experimento se ejecutó después de la nota previa.
- **Pero la mitad B de la reserva no es limpia**: su redactor incorporó a propósito la sugerencia del usuario. Por tanto, la puerta de G-53 solo puede juzgarse con los dos conjuntos de referencias. Con ellos **sigue pasando, pero por una sola pregunta** (26 frente a 25).

## 1. Cifras guardadas frente a reproducidas

Base reconstruida con el motor de `freeze-G-53r`:
- `PYTHONHASHSEED=0 python3 -m experiments.base_educada /media/leonardo/data/corpus_ud …`;
- 136 s de CPU, 93,1 MiB, RSS pico 411 MiB.

| Qué | Guardado | Reproducido |
|---|---|---|
| SHA-256 de la base | `5a97f23151a69a40…` | `5a97f23151a69a4027224dd55f59762a3533dc0cc39d97fd78b18795f414277f`: **idéntica byte a byte** a la declarada y a `base_freeze_g53r.json` (y a `base_freeze_g52.json`) |
| Cuádruple (129), `freeze-G-52`: tratamiento / sin las tres / sin G-53 / sin las cuatro / sin G-51 / sin G-49 | 85 / 85 / 81 / 81 / 83 / 86 | **85 / 85 / 81 / 81 / 83 / 86** (las 11 variantes coinciden en todos los campos, salvo los tiempos) |
| Cuádruple: sin memoria / barajada / renombrado / reinicio / afirmaciones falsas / abiertas equivocadas | 32 / 32 / 126/129 / 129/129 / 0 / 5 | **idéntico** |
| Referencias (48), `freeze-G-52`: tratamiento / sin las tres / sin G-53 / sin G-51 / sin G-49 | 26 / 26 / 25 / 23 / 26 | **idéntico**; renombrado 47/48, reinicio 48/48, 0 falsas, abiertas equivocadas 1 (sin G-53: 2) |
| Mitad B (32), `freeze-G-52`: tratamiento / sin G-53 / sin G-51 | 26 / 24 / 25 | **idéntico**; conjunto `7310483c6feea1d0` = líneas 81-151 de la cuádruple |
| SQuAD-es `dev` 2400 (semilla 4091952254 = `0xf3e63c7e`): G-52 / ablación / sin G-53 / sin las cuatro / lector solo | 0,2385 / 0,2385 / 0,2378 / 0,2378 / 0,2364 | **idéntico** (exact y respondidas también) |
| `freeze-G-53r`, `PYTHONHASHSEED=0`: cuádruple / referencias / B | 86 / 26 / 26 (declarado) | **86 / 26 / 26**; 0 falsas; abiertas equivocadas 5 / 1 / 0 |
| `freeze-G-53r`: sin G-53 (cuádruple / referencias / B) | — | 82 / 25 / 24 |
| `freeze-G-53r`: sin las tres de G-52 | — | 86 / 26 / 26 (**aporte de G-52: 0 también sin G-49**) |
| `freeze-G-53r`: sin G-51 | — | 84 / 23 / 25 (aporte +2 / +3) |
| `freeze-G-53r`, `PYTHONHASHSEED=1` (tratamiento) | — | 86 / 26 / 26, con **respuestas idénticas una a una** a las de semilla 0 en los tres conjuntos |
| Regresión completa en `freeze-G-53r` | 632 / 2 esperados / 0 | **632 / 2 / 0**, 97,7 s |

Tiempos:
- p95 de la conversación en esta copia: 37 ms en la cuádruple y 46 ms en referencias, en todas las variantes.
- El 62 ms guardado para el tratamiento de la cuádruple es ruido de esa corrida: aquí G-53 no añade latencia medible.
- No repetí la prueba fija de latencia de la regla 5.6.

## 2. Hardcodeo (regla 5.7)

Revisé `git diff freeze-G-51 freeze-G-53r -- leobot` (`syntax.py`, `reading.py`, `reference.py`, `entities.py`).

**Nada que sea hardcodeo.**
- No hay ramas según el benchmark ni según el contenido de las preguntas.
- No hay tablas de pregunta y respuesta.
- No hay palabras españolas escritas en el código: los únicos literales nuevos son etiquetas y rasgos del formato UD —el esquema de anotación del corpus— (`cop`, `nsubj`, `conj`, `NOUN`, `PROPN`, `Polarity=Neg`, `Number=Plur`…) y nombres de tablas. Los ejemplos en español solo aparecen en docstrings.
- No hay expresiones regulares nuevas por construcción.
- No hay referencias a SQuAD, MLQA ni a los conjuntos desde `leobot/`.

**Lo que el preregistro dice aprendido sale de los datos** (comprobado en la base):
- **Negadores marcados:** `['no']`.
- **Negadores por concordancia**, aprendidos de los conteos de AnCora (después del verbo con negador / antes del verbo con negador):
  - `nada` 98/75 · 28/1;
  - `nadie` 26/17 · 74/0;
  - `ni` 15/13 · 75/0;
  - `ninguno` 11/10 · 15/0;
  - `nunca` 22/15 · 66/0;
  - `tampoco` 5/5 · 42/0.
  - «jamás» no entra: solo 4 casos después del verbo, por debajo de 5.
  - Se cumple el criterio de la puerta: «no» y «nunca».
- **Clases de respuesta** (2664 claves, contadas en SQuAD-es `train` con SHA fijado):
  - «qué color»: n = 98, Good-Turing 0,34 (cerrada); sus miembros son verde, blanco, rojo, azul…
  - «qué mes»: 0,21 (cerrada).
  - «qué ciudad»: 0,44 (cerrada, pero los nombres propios quedan exentos).
  - «qué hora»: 0,65 (abierta).
  - «cuántos»: NUM en el 81 %.
  - Nada escrito a mano.

**Umbrales fijados antes de congelar:** 5, 0,5, 10, 0,05, 30, 0,1, 10, 0,5 y 2/3.

**Conocimiento programado que conviene registrar**, general y no léxico:
- (a) `MEMBER_LABELS` y las etiquetas de cópula y sujeto: una elección estructural sobre el esquema UD.
- (b) La **exención de nombres propios** (`tag == 'PROPN'` → cabe siempre; `reading.py`, dentro de `_kind_fits`), añadida en la enmienda.
  - Tiene un efecto visible: con G-53, «¿De qué color es Trueno?» pasa de «un perro grande» a **«Alejandra»**, y «¿De qué color es la casa?» pasa de «grande en Popayán» a **«Ignacio»**.
  - Es el mismo tipo de error que G-53 quería evitar: un nombre dado como color. Pasa porque en «qué color» ninguna clase llega a 2/3 (ADJ 52 %), así que no se comprueba la clase de palabra, y el nombre propio está exento de ser miembro.

## 3. Filtraciones y procedimiento

**Orden de git.**
- Preregistro de G-52: `4434461`, 18:25.
- Enmienda de G-52 y preregistro de G-53: `f93f547`, 19:11.
- Código: `fe8cd93`, 20:15:00 (= `freeze-G-52` = `freeze-G-53`).
- Correcto: los preregistros preceden al código.
- **Salvedad menor:** la enmienda de G-53 va en el mismo commit que el código, así que git no demuestra que la precediera. Esa enmienda cambia el mecanismo: núcleo de la respuesta, dominancia de 2/3, exención de nombres, Good-Turing sobre toda la clase de pregunta y orden de la educación. Sí es anterior al congelado de hecho y al material reservado, y la puerta no cambió.

**Material reservado escrito después de congelar.** Según los registros del arnés (`subagents/workflows/wf_6f46c2d1-b38/`):
- los 6 redactores se lanzaron a las 20:15:17, 17 s después del commit congelado, y terminaron entre 20:17 y 20:18;
- los validadores terminaron entre 20:20 y 20:24.

**Ejecución después de la nota.**
- La nota «antes de ejecutar» es `0bc85be`, 20:25:34.
- El primer uso de `experiments/g52_conversacion.py` fue a las **20:25:51**: es la hora de su `.pyc`, y la fuente no cambió desde las 19:19.
- La lectura SQuAD se corrió entre 20:18 y 20:21; no depende de la reserva.
- **Salvedad:** los conjuntos solo entraron a git junto con los resultados (`57979a5`). La regla 5.10 pide hacer su commit antes de ejecutar Leobot. El orden correcto se comprueba por los registros, no por git.

**HALLAZGO PRINCIPAL: la mitad B no está limpia.**
- La nota dice que el redactor de B no incorporó la sugerencia. Es falso.
- Su informe final (`agent-ae728581ecbe3da82`, «write:reserva_g52_b») dice: *«it fit naturally within the required "no lo sé" quota, so I took it — 4 of the 8 "no lo sé" questions are specifically of that type-mismatch shape (asking for a color that was never stated: la casa de Valentina, Rayo, la bicicleta, el reloj del abuelo)»*.
- La cabecera del propio archivo lo dice también (líneas 83-85 de `reserva_g52_cuadruple.tsv`: «Varias preguntas "no lo sé" piden un dato de una clase (color, número, lugar, persona, día)…»).
- Solo los **dos redactores de referencias** declinaron la sugerencia; esto está verificado en sus informes.
- La sugerencia llegó a todos porque el arnés reenvía el mensaje del usuario a cada subagente del flujo de trabajo («Workflow harness — user request»).

**Consecuencia para la puerta de G-53.**
- En el material que se dio por limpio (B + referencias), G-53 gana 3 preguntas.
- **Dos de ellas son justamente preguntas sembradas en B**: «¿De qué color es la bicicleta?» y «¿De qué color es el reloj de mi abuelo?», que pasan de «grande» y «antiguo» a «No lo sé».
- La tercera es la única ganancia en material limpio: referencias, «¿En qué ciudad compró la casa Andrés?», que pasa de «el año pasado» a «en Mérida».
- Con el principio de la propia nota aplicado bien (solo material cuyo redactor no incorporó la sugerencia), el material limpio son **solo las referencias (48)**:

| Criterio | Resultado | Puerta |
|---|---|---|
| Aciertos | 26 frente a 25 | pasa |
| Abiertas equivocadas | 1 frente a 2 (≤ 1,33) | pasa |
| Afirma lo falso | 0 = 0 | pasa |
| SQuAD, base, renombrado, reinicio, barajada | — | pasan |

- **G-53 pasa, pero por una sola pregunta de 48**: una diferencia que no se distingue del ruido.
- En el estado no debe citarse «52 frente a 49 en material limpio».

**Puerta de G-52 y retirada de G-49.**
- Se evaluaron sin relajar criterios.
- G-52 no pasa: aporte 0 + 0. También es 0 en el motor sin G-49.
- G-49 aporta −1 + 0 y se retira según su regla.
- G-51 aporta +2 + 3 y se queda.
- El motor `freeze-G-53r` equivale exactamente a `freeze-G-52` con G-49 apagado: mismas cifras y mismo desglose por tipo. Nota: sus 86/26 se eligieron después de ver esa misma reserva, así que no son una confirmación nueva.

## 4. Controles faltantes o compromisos pendientes

1. **G-53, «educación sin SQuAD-es (clases solo de MLQA)»**: estaba preregistrado como control que distingue, y no se corrió ni se informa.
2. **G-53, «respuestas equivocadas por clase de pregunta»**: estaba preregistrado y no aparece en los resultados.
3. **G-53, «qué se elimina si funciona: el filtro de G-47»**: sigue en el motor (`answer_type`). **G-52, «se elimina la paridad de negadores»**: sigue detrás del interruptor. Los dos compromisos de la regla 5.8 están pendientes.
4. **G-52 se queda con aporte 0 en la reserva.**
   - La misma regla que el preregistro aplicó a G-49 y G-51 («aporte ≤ 0 → se retira») y la regla 5.9 («no sobrevive al held-out») indicarían retirarlo, o al menos marcarlo como **no confirmado**.
   - La justificación registrada es razonable pero no está medida en reserva: evita un «sí» falso visto en desarrollo, y el hueco en el predicado solo es seguro junto con G-53.
   - Hay un precedente: G-47b en `estable-G-12`.
5. **Hueco del evaluador:** una respuesta con contenido a una pregunta cuya clave es «no lo sé» no cuenta ni como «afirma lo falso» ni como «abierta equivocada».
   - En la cuádruple, con `freeze-G-53r`, hay 3 respuestas así, dichas con seguridad y no contadas: «Alejandra» y «Ignacio» a preguntas de color, y «es con Renata» a «¿A qué hora es la reunión?».
   - Las cifras de «0 falsas / 5 abiertas equivocadas» subestiman los errores confiados.
6. **Contraevidencia y señal confundida:** G-52 los justifica como no aplicables. G-53 no los menciona; la educación con SQuAD traducido automáticamente podría actuar como señal confundida.

## 5. Salvedades para promover

1. **Obligatoria antes del tag:** corregir en `LEOBOT_STATE.md` y en `results_v3/g52_*` que la mitad B está contaminada. La puerta de G-53 se juzga con las referencias: 26 frente a 25, abiertas equivocadas 1 frente a 2. Pasa por una pregunta.
2. Registrar G-52 como mecanismo sin aporte confirmado dentro de `estable-G-13`, o retirarlo.
3. Anotar los controles faltantes (sección 4) y el hueco del evaluador.
4. La latencia fija de la regla 5.6 no se repitió en esta auditoría. El estado declara +1,5 % en general y +11,8 % en procedimientos, dentro del 20 %.

## En palabras fáciles de entender

Repetí todas las pruebas de esta versión de Leobot en una copia aparte y salieron exactamente iguales: el mismo «cerebro» educado, las mismas respuestas y las mismas notas. No encontré trampas: Leobot aprendió de libros y ejemplos qué palabras niegan y qué clase de respuesta pide cada pregunta, sin que nadie se lo escribiera. Pero una parte del examen, que se creía limpia, no lo era: quien la escribió ya sabía qué fallo se quería corregir y metió preguntas justo de ese tipo. Si se mira solo la parte de verdad limpia, el arreglo nuevo sigue aprobando, pero por una sola pregunta, lo que es muy poco para celebrar. La versión puede guardarse como estable si se corrige esa anotación y se deja dicho que uno de los arreglos (G-52) no mostró ninguna mejora en el examen.
