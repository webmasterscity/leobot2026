# G-112 — umbral de cita que iguala todas las citas malas de B0: negativo en el banco nuevo `congelado_g112`

Motor congelado `342dc4b` (huella `d1c92eb7…`, igual antes y después); banco de 32 negocios (8 redactores independientes, commit `2a13519`
antes de ejecutar). Conteo automático (`experiments/g103_evaluar.py`, `experiments/g112_evaluar.py`).
| sistema | útiles directas + sí/no (de 365) | citas malas | sin respuesta bien |
|---|---|---|---|
| B0 | 117 | 114 | 212/212 |
| G-112 | 119 | 120 | 209/212 |
Diferencia +0,55 puntos, bootstrap por negocio [−2,75, +3,83]: **umbral 1 falla**; umbral 2 pasa (120 ≤ 1,10 × 114). Reinicio idéntico;
`Bot.answer` p50/p95 1,24/2,11 ms. No se promueve.
Serie del mismo sistema frente a B0 (los dos primeros bancos eran desarrollo para G-112): `congelado_g103` +5,2, `congelado_g111` +2,4,
`congelado_g112` +0,55 puntos. La ventaja del modelo denso no se sostiene de forma fiable entre bancos nuevos.
**No repetir**: cambiar solo la regla del umbral de cita del modelo denso.
