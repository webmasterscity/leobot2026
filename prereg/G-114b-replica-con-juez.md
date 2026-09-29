# G-114b — Réplica de G-114 en un banco 5 (modelo denso G-112 frente a B0, juez ciego doble)

Fecha: 2026-09-29. Estado: diseñado (precede al banco 5). Motor sin cambios (`freeze-G112-1`, huella `d1c92eb7…`); mismo sistema
(`.leobot-data/g112.json`). Motivo: G-114 pasó los umbrales 1, 2 y 4 (+8,06 [+3,44, +12,71]; engañosas 15 frente a 22) y falló el 3 por un
turno, por cinco turnos del banco marcados `sin_respuesta` con acción `responder`. El resultado de G-114 se conserva tal cual.
## Igual que G-114 salvo
- Banco nuevo `congelado_g114b` (8 redactores independientes, 4 negocios cada uno; encargo `results_v3/kiosco/encargo_redactor_g114b.md`
  con los 32 sectores de `congelado_g114` añadidos a la lista de excluidos).
- **Criterio 3** sobre turnos coherentes: tipo `sin_respuesta` con acción `abstenerse` o `derivar`; los turnos `sin_respuesta` con otra
  acción se informan aparte y no cuentan en ningún criterio.
## Umbrales (fijados ahora; iguales a G-114)
1. Útiles G-112 − B0 ≥ +3,0 puntos de N (directas + sí/no con acción responder), bootstrap por negocio que excluye 0.
2. Engañosas G-112 ≤ engañosas B0 + 0,01 N.
3. Turnos coherentes sin respuesta bien manejados ≥ 97 % en G-112.
4. `Bot.answer` p95 ≤ 5 ms; reinicio idéntico.
Si pasan 1–4: G-112 se propone como modelo del kiosco; regresión completa, latencia, tablero y auditoría 5.10 antes de un tag estable.
