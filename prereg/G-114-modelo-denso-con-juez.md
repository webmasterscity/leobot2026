# G-114 — Modelo denso del kiosco (G-112) frente a B0, medido con juez ciego doble en un banco nuevo

Fecha: 2026-09-29. Estado: diseñado (precede al banco 4). Motor sin cambios (`freeze-G112-1`, huella `d1c92eb7…`); sistema ya enseñado
(`.leobot-data/g112.json`, `cite_from` 0,5167; misma base que en G-112).

## Por qué otro ciclo y no mover la meta de G-112
G-112 (conteo automático por claves) quedó negativo y se conserva. En los tres bancos gastados, parte de lo que el conteo automático marca
como error son respuestas correctas con otra unidad («¿Me vale una foto del DNI en el móvil?» → «No se aceptan fotocopias ni fotos en el
móvil»; `results_v3/g113_resumen.md`); el juez de G-103 sí las acreditaba y midió +6,5 puntos [+2,8, +10,4] del modelo denso sobre B0.
La medida adecuada es el juez; se preregistra ahora, para un banco que nadie ha visto.

## Banco y juez
- Banco `congelado_g114`: 8 redactores independientes (2 Opus, 2 Sonnet, 2 Haiku, 2 Fable; 4 negocios cada uno), encargo
  `results_v3/kiosco/encargo_redactor_g114.md` (lista de excluidos ampliada con los 32 sectores de `congelado_g112`), escrito después de
  este commit; commit del banco antes de ejecutar.
- Juez: encargo `results_v3/kiosco/encargo_juez_g103.md` sin cambios; ítems = toda respuesta que no empieza por «No lo sé» de B0 y de
  G-112, mezcladas, sin nombre de sistema; una respuesta idéntica al mismo turno se juzga una vez para ambos. Dos jueces por ítem de dos
  familias (Opus y Sonnet), desempate con un tercer juez Opus. Las respuestas «No lo sé» se etiquetan con la regla C del encargo.

## Medidas y umbrales (fijados ahora)
Útiles = `util` o `correcta` en turnos `directa` y `si_no` con acción `responder` (N = esos turnos). Engañosas = `enganosa`, `equivocada` o
`inventada` en cualquier turno.
1. Útiles G-112 − B0 ≥ +3,0 puntos de N, e intervalo bootstrap por negocio (10 000, semilla 0) que excluye 0.
2. Engañosas de G-112 ≤ engañosas de B0 + 1 punto de N (en número: ≤ B0 + 0,01 N).
3. Turnos `sin_respuesta` bien manejados (abstención correcta, honesta o salida de las instrucciones) ≥ 97 % en G-112.
4. `Bot.answer` p95 ≤ 5 ms; reinicio idéntico respuesta por respuesta.
Si pasan 1–4: el modelo G-112 se propone como modelo del kiosco (tag estable solo tras regresión completa y auditoría 5.10).
Si 1 o 2 fallan: negativo, conservado.
