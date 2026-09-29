# G-111b — Pares comunes a ≥ 25 negocios: prueba en un banco nuevo

Fecha: 2026-09-29. Estado: diseñado (precede al congelado y al banco). Motivado por G-111 en desarrollo (`congelado_g103`, gastado):
acierto cruzado +1,6/+1,9 puntos con k = 25 y +8/+13 útiles con presupuestos amplios, pero peor con ≤ 100 citas malas; G-111 no cumplió su
umbral y queda registrado como tal. Aquí decide un banco que nadie ha visto.

## Sistemas (fijados ahora)
- **Control:** modelo de utilidad G-103 sin pares, semilla 0.
- **Tratamiento:** el mismo con pares de todas las familias que aparecen en ≥ 25 negocios distintos (`experiments/g111_educar.py
  --k 25`), semilla 0.
- Contexto: B0 y prefijos solos (mismo motor, interruptores).
Enseñados con el motor congelado `freeze-G111-1` sobre `base_kiosco_nube.json` y los 216 negocios de los 9 bancos gastados.

## Banco nuevo
`results_v3/kiosco/congelado_g111`: 8 redactores independientes (Agent con `isolation: "worktree"`, nunca *fork*; 2 Opus, 2 Sonnet,
2 Haiku, 2 Fable), 4 negocios cada uno, encargo `results_v3/kiosco/encargo_redactor_g111.md` (el neutral de G-103 con la lista de sectores
excluidos ampliada con los 31 de `congelado_g103`); sin mensajes del usuario, sin este preregistro, sin ejemplos. Commit del banco antes de
ejecutar Leobot sobre él.

## Medida (conteo automático por claves, como en `experiments/g106_curva.py`)
Turnos `directa` y `si_no` con claves (N turnos) más los `sin_respuesta`. Para cada sistema, útiles con a lo sumo B citas malas, con
B = 0,26 N, 0,39 N y 0,65 N (equivalen a 100, 150 y 250 de 383).

## Umbrales de éxito (fijados ahora)
1. Con B = 0,39 N y con B = 0,65 N: tratamiento − control ≥ +2,0 puntos de N en ambos.
2. Con B = 0,65 N, intervalo bootstrap por negocio (10 000, semilla 0) de la diferencia que excluye 0.
3. Con B = 0,26 N: tratamiento − control ≥ −2,0 puntos (no empeora de forma clara).
4. `Bot.answer` p95 ≤ 5 ms; reinicio y `PYTHONHASHSEED` 0/1 idénticos respuesta por respuesta.
Si 1 o 2 fallan: negativo, conservado. Si pasan: el tratamiento sustituye al control como modelo del kiosco en la próxima base, y se
pide juez ciego para las citas engañosas antes de cualquier tag estable.
