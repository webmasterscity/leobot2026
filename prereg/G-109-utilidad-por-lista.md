# G-109 — Modelo de utilidad del kiosco enseñado por lista (ListNet)

Fecha: 2026-09-29. Estado: diseñado (precede a la ejecución). Motor: `db80a09` (sin cambios en `leobot/` para este ciclo: solo cambia la
enseñanza, `experiments/g109_listwise.py`).

## Qué fallo concreto resuelve
Desarrollo (`congelado_g103`, gastado): la unidad correcta está entre las 8 candidatas en 292/383 turnos pero el modelo la elige primera
en 188 (64 %); «elige otra» es el mayor hueco (104). El modelo G-103 se enseña candidata por candidata (logística puntual), que optimiza
la probabilidad de cada candidata y no el orden entre las candidatas de un mismo turno.

## Por qué los mecanismos actuales no bastan / qué distingue las hipótesis
Hipótesis: con los mismos rasgos, un objetivo por lista (softmax sobre las candidatas de cada turno; Cao et al., ICML 2007) ordena mejor.
Alternativa: el límite está en los rasgos, y el objetivo no cambia nada.
Medida de desarrollo (sin reserva): acierto cruzado entre respondibles (5 grupos por negocio, 216 negocios de enseñanza) y, en
`congelado_g103`, útiles con a lo sumo 100 y 150 citas malas (`experiments/g106_curva.py`), frente al modelo puntual sin pares
(149 y 162).

## Umbral para seguir (fijado ahora)
Solo si en `congelado_g103` supera al modelo puntual en ≥ 8 útiles con ≤ 100 y con ≤ 150 citas malas **y** el acierto cruzado sube
≥ 2 puntos, se prepara congelado y reserva (banco nuevo, juez ciego) con los umbrales 1, 3, 4 y 5 de G-103. Si no, negativo registrado.

## Controles
Mismo presupuesto de épocas y regularización; con y sin pares; semilla 0 y 1.
