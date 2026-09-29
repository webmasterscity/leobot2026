# G-111 — Solo asociaciones aprendidas que se repiten en muchos negocios distintos

Fecha: 2026-09-29. Estado: diseñado (precede a la ejecución). Motor: `31136c9` (sin cambios en `leobot/`: solo la enseñanza,
`experiments/g111_educar.py`).

## Qué fallo concreto resuelve
Los pares palabra|palabra aprendidos de los 216 negocios de enseñanza no transfieren a sectores nuevos (G-103: −0,3 puntos con juez;
esta sesión, desarrollo `congelado_g103`: con todas las familias 126 útiles frente a 129 sin pares; forma sola 126 frente a 149 con ≤ 100
citas malas). El filtro de apoyo actual (≥ 3 candidatas) deja entrar pares de un solo negocio o sector.

## Hipótesis y alternativa
Hipótesis: las asociaciones que valen en un sector nuevo son las que se repiten en muchos negocios distintos (principio de invariancia
entre grupos: lo que se sostiene en muchos entornos se sostiene en uno nuevo). Alternativa: ningún par léxico transfiere.

## Mecanismo
Igual que G-103 (todas las familias de pares, mismas épocas y regularización), con un solo cambio: un par entra al vocabulario solo si
aparece en candidatas de al menos k negocios distintos. k ∈ {10, 25} (fijados ahora).

## Medida (desarrollo, sin reserva) y umbral para seguir
`congelado_g103`, útiles con a lo sumo 100 y 150 citas malas (`experiments/g106_curva.py`); referencia sin pares 149 / 162 (semilla 0) y
146 / 157 (semilla 1). Se sigue a congelado y reserva (banco nuevo de redactores independientes y juez ciego, umbrales 1, 3, 4 y 5 de
G-103) solo si alguna k supera a sin pares en ≥ 8 útiles en ambos puntos con las semillas 0 y 1.
