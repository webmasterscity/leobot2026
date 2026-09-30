# G-112 — Modelo denso del kiosco con umbral de cita que iguala todas las citas malas de la línea base

Fecha: 2026-09-29. Estado: diseñado (precede al congelado y al banco 3). Motor: sin cambios desde `freeze-G111-1`
(huella `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`); solo cambia la enseñanza (`experiments/g112_educar.py`).

## Qué fallo concreto resuelve
G-103 rechazado: su regla de umbral igualaba solo las citas sin dato de la línea base y, en sectores nuevos, citaba de más (engañosas
8,6 % → 11,8 %). En G-111b (observación no preregistrada) el modelo denso, a igual número de citas malas, supera a prefijos y a B0.
## Mecanismo
Modelo de utilidad G-103 sin pares; el umbral de cita es el menor cuyas citas malas (respondibles con unidad equivocada + sin respuesta),
con puntajes cruzados por negocio en los 216 negocios de enseñanza, no superan las de B0 (confianza de siete rasgos a 0,4) en los mismos
turnos. Enseñado: `cite_from` 0,5167 (1 074 útiles cruzadas con 483 malas frente a 993 / 537 de B0).
## Cifras de desarrollo ya vistas (no cuentan)
`congelado_g103`: 124 útiles con ≈ 129 citas malas frente a B0 104 / 131. `congelado_g111`: 120 / ≈ 113 frente a 111 / 110.
## Experimento decisivo
Banco nuevo `congelado_g112` (8 redactores independientes, 4 negocios cada uno; encargo `results_v3/kiosco/encargo_redactor_g112.md` =
el de G-111b con los 32 sectores de `congelado_g111` añadidos a la lista de excluidos), escrito después de este commit.
Sistemas: **B0** (motor con `soft_prefix` y `candidate_model` apagados) y **tratamiento** (G-112), con `experiments/g103_evaluar.py`.
Útiles = veredicto automático `cita_util` + `correcta` en directa/si_no; malas = `cita_no_util` + `cita_sin_dato` + `contesto_sin_dato` +
`equivocada` en todos los turnos.
## Umbrales (fijados ahora)
1. Útiles del tratamiento − B0 ≥ +2,0 puntos de las directas + sí/no, con intervalo bootstrap por negocio (10 000, semilla 0) que
   excluye 0 (`experiments/g112_evaluar.py`).
2. Malas del tratamiento ≤ 1,10 × malas de B0.
3. Sin respuesta bien manejadas ≥ 97 %; `Bot.answer` p95 ≤ 5 ms; reinicio y `PYTHONHASHSEED` 0/1 idénticos respuesta por respuesta.
Si pasan: el modelo G-112 pasa a ser el del kiosco en la base de la nube y se pide juez ciego y auditoría antes de un tag estable.
Si 1 o 2 fallan: negativo, conservado.
