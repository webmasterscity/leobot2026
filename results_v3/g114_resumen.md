# G-114 — modelo denso G-112 frente a B0 con juez ciego doble: **mejora demostrada en utilidad y engañosas; no promovible por el criterio 3**

Motor congelado `339dd02` (huella `d1c92eb7…`, igual antes y después); banco nuevo `congelado_g114` (32 negocios, 816 turnos, 8 redactores
independientes; commit `6bca23e` antes de ejecutar). Juez: encargo de G-103 sin cambios; 369 respuestas distintas mezcladas y anónimas en
13 lotes; jueces A (Opus) y B (Sonnet) por lote, desacuerdo 13/369 (3,5 %) resuelto por un tercero (Opus). Datos: `kiosco/evaluacion_g114/`.
| | B0 | G-112 |
|---|---|---|
| útiles en directas + sí/no (N = 360) | 100 (27,8 %) | **129 (35,8 %)** |
| engañosas (todos los turnos) | 22 | **15** |
| sin respuesta bien manejadas | 155/161 (96,3 %) | 156/161 (96,9 %) |
| `Bot.answer` p50/p95 | 0,19 / 0,33 ms | 1,31 / 2,23 ms |
Umbrales preregistrados:
1. **Pasa:** +8,06 puntos, bootstrap por negocio [+3,44, +12,71].
2. **Pasa:** engañosas 15 ≤ 22 + 3,6.
3. **Falla por un turno:** 156/161 = 96,9 % < 97 %. Cinco turnos del banco (redactor W7) están marcados `sin_respuesta` con acción
   `responder` (contradicción del redactor); en 4 G-112 dice «No lo sé» y la regla C preregistrada lo cuenta como abstención indebida.
   Sin esos cinco turnos, 155/156 (99,4 %); B0 152/156. No se cambia el criterio: queda fallado.
4. **Pasa:** reinicio idéntico en 816/816 respuestas; p95 2,23 ms ≤ 5 ms.
**Veredicto según el preregistro: no se promueve** (exigía 1–4). Aun así es la primera mejora de la sesión confirmada en un banco nuevo con
juez ciego y criterios fijados antes: +8 puntos de utilidad con **menos** respuestas engañosas. Coincide con G-103 (+6,5 [+2,8, +10,4] con
juez) y contradice la lectura pesimista del conteo automático (G-112: +0,55), que no acredita respuestas correctas con otra unidad.
Siguiente paso: repetir con un banco 5 y el criterio 3 contado solo sobre turnos coherentes (tipo y acción concordantes), preregistrado
antes; si pasa, auditoría 5.10 y tag estable.

## Compatibilidad del motor (para un eventual tag)
Con `soft_prefix`, `candidate_model`, `general_knowledge` y `number_compare` apagados, el motor actual (`d1c92eb7…`) da las **585 respuestas
del banco G-64 idénticas** a las del motor de `estable-G-19` (`11a1ef58…`, commit `ccd895f`) sobre la misma base `base_kiosco_nube.json`
(resumen `47c1e2c6cf5e4509`), también con `PYTHONHASHSEED` 1 (`experiments/g114_compat585.py`).
Regresión completa (`experiments.regression_batches`, motor `d1c92eb7…`): **Python 3.12.3: 684 pruebas, 6 fallos esperados, 0 fallos**
(125 s). Con Python 3.11.15 falla `test_meta_v57` (2 casos, `meta_role_set_transfer` en vez de `cross_modal_projection_transfer`); falla igual
con el motor del inicio de la sesión (`fa15c4a`) y pasa con 3.12 y 3.13: **defecto preexistente de dependencia de versión** (probablemente
la suma de flotantes compensada de `sum()` desde 3.12), registrado; no afecta al kiosco.
