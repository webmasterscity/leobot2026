# Auditoría independiente — G-66 y G-67 (regla 5.10, tipo auditor)

Encargo: decidir si los diseños de desarrollo G-66 (preferencia lineal entre
respuesta propia y rival) y G-67 (aprender solo de la unidad pertinente
seleccionada por el propio motor) se descartan. No se pide promover nada ni
refutar la fase G completa.

## Huella del motor

- Antes de reejecutar: `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
- Después de reejecutar ambos scripts en secuencia: `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
- Sin cambios en `leobot/` en ningún momento (`git status --porcelain -- leobot` vacío antes y después).

## Reejecución

Órdenes usadas, `PYTHONHASHSEED=1`, timeout 300 s cada una, BASE =
`/tmp/leobot2026_mfaq.json` (bot guardado, no confundir con el corpus pese al
nombre), corpus MFAQ = `/tmp/mfaq_es_train.jsonl`:

```
python3 -m experiments.g66_rivales /tmp/leobot2026_mfaq.json /tmp/mfaq_es_train.jsonl /tmp/leobot2026-g66-auditor.json
python3 -m experiments.g67_unidad_pertinente /tmp/leobot2026_mfaq.json /tmp/mfaq_es_train.jsonl /tmp/leobot2026-g67-auditor.json
```

Ambas terminaron dentro del presupuesto (ninguna llegó a 300 s) y sin errores.

| | `results_v3/*_desarrollo.json` (desarrollador) | Reejecución del auditor |
|---|---|---|
| G-66 `selected` | `words`/`phrases`: peso 0, hits [346,346,346], gate `false` | **idéntico byte a byte** |
| G-66 `phrase_retention` | `false` | igual |
| G-67 `selected` | `align_1` peso 0,25 → 349; `align_2` peso 0 → 346; `rank` peso 0 → [346,346,346], gate `false` en los tres | **idéntico byte a byte** |
| CPU / RAM | G-66: 152,7 s / 609 MiB · G-67: 174,7 s / 681 MiB | G-66: 199,9 s / 609 MiB · G-67: 150,6 s / 681 MiB |

Las métricas de precisión, pesos elegidos y compuertas coinciden exactamente
(confirmado programáticamente, `selected` idéntico). La CPU varía por la carga
de esta máquina, tal como se esperaba; la RAM pico coincide. No hay indicio de
que el desarrollador haya alterado el archivo de resultados a mano ni de que
la reproducción dependa de un orden de hash no fijado.

## Fuga de datos

- El corpus de aprendizaje (`/tmp/mfaq_es_train.jsonl`, verificado contra
  `MFAQ_SHA` con `hashlib.sha256`, o el script aborta) es un FAQ multilingüe
  externo; los negocios de evaluación (`results_v3/kiosco/desarrollo/{A..F}`,
  `congelado_g59`, `congelado_g60`) son textos de negocio distintos, escritos
  para el kiosco. No comparten archivos ni contenido: no hay ruta de código
  que mezcle ambos antes de entrenar.
- `calibration_domain()` excluye un 10 % de dominios de MFAQ por hash del
  nombre del dominio, igual que en G-65; no es una lista de dominios escrita
  a mano ni depende del contenido de las preguntas.
- Dentro de MFAQ, el muestreo por reservorio (semilla fija 57, máx. 100 pares
  por dominio) y la deduplicación son iguales a G-65; no se leyó el banco de
  evaluación para elegir qué pares de MFAQ entran a entrenar.
- G-67 reconstruye los pares de entrenamiento sustituyendo cada respuesta
  humana por la unidad que el propio `bot._rank` elegiría dentro de ella
  (`selected_examples`); usa el selector ya existente del motor, no una regla
  nueva escrita para este experimento, y sigue leyendo solo MFAQ, nunca los
  negocios de evaluación.

## Uso de desarrollo gastado (A-D) y separación E-F/G-59/G-60

- `fitting = results_v3/kiosco/desarrollo/{A,B,C,D}` (n=181) se usa **solo**
  para elegir el peso de mezcla en ambos scripts (`report['fit']` alimenta el
  `max(WEIGHTS, ...)` en `g66_rivales.main` y en `g67_unidad_pertinente.main`).
- `separate = {E,F} + congelado_g59/X* + congelado_g60/Y*` (n=633) se usa solo
  para medir, nunca para elegir pesos. El preregistro declara explícitamente
  que este material ya fue usado en G-65 ("desarrollo reutilizado, nunca se
  le llamará reserva nueva"), y el código respeta esa etiqueta: no se genera
  ninguna reserva nueva en estos dos experimentos.
- Confirmado por inspección de código, no solo por el preregistro: no hay
  ninguna ruta donde `separate` alimente `WEIGHTS` o el entrenamiento.

## Igualdad del control con producción

`g65_correspondencias.evaluate()` recalcula la selección de unidad con
`baseline_scores()` (reimplementación explícita de `ContextMixin._rank`) y
compara contra `bot._rank(...)` real con un `assert` que aborta la ejecución
si difieren ("El control no reproduce la selección de la base"). Las dos
reejecuciones terminaron sin disparar esa excepción: el control de producción
coincide con el motor real en las 633+181 preguntas evaluadas.

## Precisión de localizar un texto vs. respuesta útil con abstención

Importante para no sobrevalorar estas cifras: **346/633, 349/633, etc. miden
si la unidad de texto con más puntaje contiene las claves correctas**, no si
`Bot.answer` produce una respuesta útil al cliente. `evaluate()` llama
directamente a `bot._rank` / `alignment_scores` / `linear_scores` sobre todas
las unidades candidatas y compara con `good[index]`; en ningún punto se pasa
por la calibración de confianza ni por la lógica de abstención/derivación que
sí usa `Bot.answer` en producción (los estados `unknown`, `closest`,
`ambiguous`, etc. de `g57_kiosco.judge`). No hay opción de "no sé" en este
bucle de evaluación: siempre se fuerza una elección entre unidades.

Esto es consistente con lo que dicen los propios preregistros: ambos tratan
esta cifra como una puerta de desarrollo previa, y solo si se superara se
repetiría "el protocolo de reserva y puertas finales de G-65, incluida la
meta del usuario de ≥60 % útil, cero invenciones y p95<5 ms" con el `Bot`
completo. Como ninguna puerta se superó, ese protocolo con abstención nunca
se ejecutó — correctamente, ninguno de los dos preregistros afirma haberlo
hecho. No hay que atribuir la latencia medida aquí (`p50_ms`/`p95_ms` del
bucle `alignment_scores`/`linear_scores`, del orden de 0,2–1,1 ms) a la
latencia de `Bot.answer` completo: es solo el costo de puntuar unidades con
el modelo candidato, sin el resto del pipeline de respuesta.

## Aprendizaje sin reglas léxicas manuales ni redes neuronales

- G-66: preferencia lineal dispersa sobre conjuntos de n-gramas de pregunta y
  palabras de respuesta, actualización acotada por pérdida y norma (estilo
  perceptrón con margen), sin retropropagación ni pesos densos/neuronales.
  Todas las asociaciones nacen de los pares de MFAQ, ninguna se escribe a
  mano; el único parámetro fijo es la geometría del algoritmo (vueltas,
  paso máximo), no el contenido lingüístico.
- G-67 no introduce ningún algoritmo nuevo: reimporta y reutiliza tal cual
  `g65_correspondencias.train`/`evaluate` (`align`) y `g66_rivales.train`/
  `representation` (`rank`); el único cambio es qué texto se les entrega como
  respuesta de entrenamiento (la unidad seleccionada en vez del texto humano
  completo). No hay reglas por palabra ni por negocio.

## Controles no corridos (por no pasar la puerta de desarrollo)

Ambos preregistros son explícitos: los controles de G-65 (bot fresco,
memoria literal, datos incompatibles, renombrado total, reinicio,
contraevidencia, señal confundida, retirada) están reservados "para
cualquier integración posterior" y "no se cuentan como pasados si el
experimento se detiene antes". Como ninguna puerta de desarrollo se superó
en G-66 ni en G-67, **ninguno de esos controles se ejecutó**, y no debe
leerse el silencio sobre ellos como que pasaron. Los únicos controles que sí
corrieron y con qué resultado:

- igualdad del control con producción: corrió y pasó (ver arriba);
- elección de mezcla restringida a A–D: corrió y se cumple por construcción
  del código;
- comparación entre variantes «palabras» vs. «pares»/«frases»: corrió;
  ninguna aventaja alcanzó el umbral de +2 puntos exigido para preferir la
  variante más cara.

No corrieron: bot fresco, memoria literal, datos incompatibles, renombrado
total, reinicio, contraevidencia, señal confundida, held-out estructural
nuevo (todo lo evaluado es desarrollo reutilizado, según lo declarado).

## Conclusión

Ambos diseños reproducen exactamente sus cifras declaradas con el motor
congelado en la misma huella antes y después; no se detectó fuga de datos,
hardcodeo, mezcla elegida fuera de A–D, ni confusión entre localizar texto y
responder con abstención (el prototipo mide solo lo primero, y así lo declara
el preregistro). El aprendizaje en ambos es lineal/dispares sobre n-gramas,
sin reglas léxicas manuales ni redes neuronales.

Con esa auditoría, **la recomendación es descartar G-66 y G-67 como diseños
de mezcla lineal/selección de unidad sobre esta representación**, siguiendo
la propia puerta preregistrada: ninguna variante alcanzó el 60 % ni la
ventaja de +5 puntos sobre la base (346/633) en el material de desarrollo
reutilizado, y G-66 prefirió peso cero en las tres semillas mientras G-67
repitió casi los mismos resultados que G-65/G-66 originales, confirmando que
cambiar la unidad de aprendizaje (G-67) no resolvió lo que G-65/G-66 ya
habían dejado sin resolver. Esto cuenta como el tercer y cuarto diseño
distintos sobre la misma familia de tareas (tras G-65 y sus dos variantes);
si la sesión que continúe quiere declarar refutada esta vía de "aprender
puntajes de mezcla sobre n-gramas de MFAQ", debe listar los cuatro diseños
(G-65 alineación, G-65 pares, G-66 preferencia, G-67 unidad pertinente) en
`LEOBOT_STATE.md`, no solo estos dos. Ruta recomendada: no seguir puliendo la
familia de mezcla lineal por n-gramas; si se insiste en aprender de MFAQ,
cambiar de representación (p. ej. una que no dependa de la longitud/ruido de
la respuesta completa) antes de gastar más presupuesto en esta misma línea.

## En palabras fáciles de entender

Se probaron dos maneras de enseñarle a Leobot a preferir la respuesta
correcta entre varias parecidas, usando preguntas y respuestas de un banco
público de preguntas frecuentes. Repetí exactamente los mismos experimentos
que hizo la sesión anterior, con el cerebro de Leobot congelado (comprobé que
no cambió ni una línea antes ni después), y me dieron los mismos números:
ninguna de las dos formas de enseñar mejoró lo suficiente. No encontré
trampas: los datos de entrenamiento y los de examen están bien separados, el
código de control funciona igual que el de producción, y no se usaron reglas
escritas a mano ni redes neuronales. Sí es importante aclarar una cosa: el
número que se mide aquí (por ejemplo 349 de 633) dice si Leobot ubica el
trozo de texto correcto, no si le da al cliente una respuesta completa y
sabe cuándo decir "no lo sé"; eso se mide después, con un experimento
distinto, y en este caso ni siquiera se llegó a intentarlo porque estas dos
ideas no pasaron la primera prueba. Mi recomendación: descartar estas dos
maneras concretas de aprender y probar una idea distinta la próxima vez.
