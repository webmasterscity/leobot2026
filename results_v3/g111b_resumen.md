# G-111b — pares comunes a ≥ 25 negocios en el banco nuevo `congelado_g111`: negativo

Motor congelado `62a688a` (huella `d1c92eb7…`, idéntica antes y después); banco de 32 negocios (8 redactores independientes, commit
`ec66f23` antes de ejecutar). Conteo automático por claves; N = 372 turnos directa/si_no con claves; útiles con a lo sumo B citas malas.
| sistema | B = 0,26 N | 0,39 N | 0,65 N |
|---|---|---|---|
| B0 | 128 | 150 | 165 |
| prefijos solos | 127 | 156 | 185 |
| control (modelo denso sin pares) | 149 | 175 | 194 |
| tratamiento (pares en ≥ 25 negocios) | 145 | 173 | 199 |
Tratamiento − control: −1,08 / −0,54 / +1,34 puntos; bootstrap por negocio en 0,65 N: [−4,12, +5,56]. **Umbrales 1 y 2 fallan**
(3 pasa). Sin los 6 negocios de sector repetido (26 negocios, N = 286): +1,75 / +1,40 / +2,45, IC [−4,18, +7,39]: también falla.
`Bot.answer` p50/p95 1,54/2,98 ms. Datos: `results_v3/kiosco/evaluacion_g111/`. **No repetir** pares léxicos filtrados por número de negocios.

## Observación no preregistrada (no cuenta como resultado; motiva G-112)
A igual número de citas malas, el modelo denso sin pares supera a prefijos solos en el banco nuevo en +22 / +19 / +9 útiles
(+5,9 / +5,1 / +2,4 puntos; sin repetidos +21 / +14 / +8), más que en desarrollo (+8 / +2 / +1 en `congelado_g103`). G-103 se rechazó en
su punto de operación porque su regla de umbral igualaba solo las citas sin dato y en sectores nuevos citaba de más. Hipótesis para G-112:
el modelo denso con un umbral que iguale **todas** las citas malas de la línea base en la enseñanza.
