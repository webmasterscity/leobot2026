# Auditoría independiente (5.10) — G-65, ensayo de desarrollo

Encargo: auditor. Worktree `/tmp/leobot2026-verif-g65`, HEAD `e55755b`. Solo se decide si el
candidato de G-65 debe descartarse; no se promueve tag estable ni se toca `leobot/`,
pruebas ni preregistros.

## Qué se auditó

- `prereg/G-65-correspondencias-competitivas.md`
- `experiments/g65_correspondencias.py`
- `results_v3/g65_desarrollo.json` (informe original)
- Reejecución: `PYTHONHASHSEED=1 timeout 180s python3 -m experiments.g65_correspondencias /tmp/leobot2026_mfaq.json /tmp/mfaq_es_train.jsonl /tmp/leobot2026-g65-auditor.json`

## Huella del motor

- Antes: `git rev-parse HEAD:leobot` = `11a1ef5836382d81a643cad0b217a8669ce0f2d1`, árbol `leobot/` limpio (congelado).
- El propio script vuelve a comprobarlo (`engine`/`engine_after`/`engine_unchanged`): idéntico antes y después, en la corrida original y en la reejecución.

## Reproducción

La reejecución con `PYTHONHASHSEED=1` reproduce **exactamente** el informe original, entero:
mismos `examples` (31 762), `q_features`/`a_features`/`candidates`/`kept`/`minimum_pair_count`
por modelo, mismos `fit` (181, techo 173, base 102) y `separate` (633, techo 592, base 346),
mismos aciertos por peso para `words` y `phrases`, mismos `chosen_weights` (words=1,
phrases=0,5), mismos `chosen_hits` (361 y 351) y misma `development_gate` (falso/falso).
Solo cambian los tiempos de CPU (ruido normal de máquina, ~56–58 s totales en ambas
corridas). Esto confirma que el resultado no depende del orden de hashes ni de detalles
de la ejecución: los conteos usan `sorted()` en todos los puntos donde el orden de un
`dict`/`set` importaría.

## Separación entrenamiento / desarrollo

- El material de enseñanza son 31 762 pares pregunta–respuesta de MFAQ `es/train`
  (SHA-256 verificado por el propio script, coincide con el registrado: `c985eb0...`),
  excluyendo los dominios de calibración de G-57 (`calibration_domain`, hash del nombre
  del dominio).
- El "desarrollo" son bancos de negocios de kiosco (`results_v3/kiosco/desarrollo/A-F`,
  `congelado_g59`, `congelado_g60`), de dominio y formato totalmente distintos a MFAQ:
  no hay superposición de contenido entre lo que se enseña (pares MFAQ) y lo que se mide
  (conversaciones de negocios). No se tocó `duxiV2` (reservado), consistente con la nota
  del proyecto.
- Dentro del desarrollo, la mezcla de pesos se elige **solo** con A–D (`fit`, 181 turnos)
  y se comprueba aparte en E–F + G-59 + G-60 (`separate`, 633 turnos), tal como fija el
  preregistro. El encargo pide explícitamente no tratar esto como reserva, y el propio
  preregistro lo llama "diagnóstico, no reserva" — correcto: ninguna de las dos particiones
  es el material ciego de 24 negocios que exige la puerta final (esa solo se pediría si
  el desarrollo hubiera pasado, y no pasó).

## Igualdad del control con el motor

`evaluate()` calcula `baseline_scores()` de forma independiente y exige
`ours == baseline` (con `AssertionError` si no), comparando contra `bot._rank()` real.
La aserción no falló en ninguna corrida: el control de peso 0 reproduce bit a bit el
ranking de producción, y en el propio informe `correct["0"]` = 346 = `baseline` en las
dos tablas (`words` y `phrases`) para `separate`, y 102 = `baseline` en `fit`. Esto es
una comprobación interna adicional de que la mezcla con peso 0 es indistinguible del
motor sin candidato (ablación implícita correcta).

## Puertas y resultado

Según el preregistro (≥60 % de útiles y ≥+5 puntos sobre la base en desarrollo separado):

| modelo | peso elegido (A–D) | aciertos en separado (E–F+G59+G60, n=633) | % útil | ganancia vs. base (346) | puerta |
|---|---|---|---|---|---|
| words | 1 | 361 | 57,0 % | +2,4 % (+15) | **no pasa** (falta % y falta ganancia) |
| phrases | 0,5 | 351 | 55,5 % | +0,8 % (+5) | **no pasa** |

Retención de frases: `(351−361)/633 = −0,016 < 0,02` → tampoco se sostiene la ventaja de
pares contiguos sobre palabras aisladas; en `separate`, `words` supera a `phrases`.
Los cálculos de `development_gate` y `phrase_retention` en el JSON coinciden con esta
aritmética y con la fórmula exacta del preregistro.

## Costo y latencia

CPU total ~56–58 s (presupuesto: ≤20 min de prototipo), RSS pico ~966 MiB (presupuesto:
≤1,5 GB adicional). Latencia por unidad, muy por debajo de cualquier presupuesto de
la sección 5.6 (p95 ≈ 0,7–1,4 ms), aunque es irrelevante para la decisión porque el
candidato no se promueve.

## Atajos / hardcodeo (5.7)

No se encontró ramificación por nombre de negocio, pregunta o banco. El sustrato son
n-gramas contiguos de longitud 1–2 sobre términos ya lematizados por el motor
(`bot.context_terms`), con poda solo por soporte (apoyo en ≥5 apariciones, y un umbral
dinámico que solo sube si se excede el límite de 2 millones de pares, documentado como
truncamiento explícito, no oculto). No hay tablas pregunta→respuesta ni respuestas de
examen incrustadas; la tabla aprendida son probabilidades IBM-1, como declara el
preregistro.

## Limitaciones de esta auditoría (lo que no se comprobó, y por qué no hacía falta)

- No se ejecutaron los controles de barajado, bot fresco, documento incompatible,
  reinicio ni renombrado: el preregistro los reserva para la fase final ("solo si pasa
  desarrollo"), y este candidato no pasó desarrollo, así que esa fase no se abre.
- No se auditó la matemática interna del EM más allá de revisar el código y confirmar
  reproducibilidad exacta y la igualdad de control en peso 0; no se buscaron errores de
  implementación que no afecten el resultado agregado (p. ej. micro-sesgos internos de
  la tabla) porque no cambiarían la conclusión de la puerta.
- No se revisó `LEOBOT_STATE.md` como objeto de auditoría más allá de confirmar que el
  registro del ciclo coincide con el JSON y no exagera ni oculta el resultado.

## Conclusión

**CONFIRMADO.** El ensayo de desarrollo de G-65 (alineación competitiva de palabras y
pares contiguos, tipo IBM-1) es reproducible bit a bit con el motor congelado, separa
correctamente enseñanza (MFAQ) de desarrollo (bancos de kiosco), su control de peso 0
reproduce exactamente el ranking de producción, y sus puertas están bien calculadas
según el preregistro. Ambos modelos (`words` y `phrases`) **no alcanzan** el 60 % de
útiles ni la ganancia de +5 puntos exigida sobre la base (57,0 %/+2,4 % y 55,5 %/+0,8 %
respectivamente), y los pares contiguos no superan a las palabras aisladas en el banco
separado. No hay indicios de hardcodeo, fuga entre enseñanza y desarrollo, ni de que se
haya tratado el desarrollo como reserva. La decisión correcta es **descartar este
candidato tal como está** y no crear tag estable ni declarar refutada la fase G (el
propio registro del proyecto ya lo hace así, y esta auditoría no encuentra motivo para
cambiarlo).

## En palabras fáciles de entender

Alguien intentó enseñarle a Leobot a reconocer qué palabras y qué parejas de palabras
seguidas suelen "traducirse" entre una pregunta y su respuesta, usando miles de
preguntas y respuestas reales de internet. Volví a correr esa prueba desde cero, con el
cerebro de Leobot congelado exactamente igual que antes, y me dio números idénticos a
los que ya se habían anotado. Los datos con los que se le enseñó y los negocios con los
que se le examinó son cosas distintas, así que no hubo trampa de "verle las respuestas
antes". El resultado sigue siendo el mismo: esta idea mejora un poquito, pero no lo
suficiente como para las metas que se habían puesto de antemano, así que hicieron bien
en no usarla todavía. No encontré ningún truco escondido ni ningún error que cambie esa
conclusión.

Informe: `/tmp/leobot2026-auditoria-g65.md`
