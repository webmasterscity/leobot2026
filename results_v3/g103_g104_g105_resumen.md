# G-103 / G-104 / G-105 — resumen de la sesión de nube (2026-09-28 y 29)

Motor congelado: commit `fa15c4a`, huella `2d651fbd9a6f4e7a957dee77548ecb57e47abe30` ([registro](freeze_G103_1.json)). Igual antes y después de cada ensayo.
Entorno: contenedor sin MFAQ, MLQA ni COSER (403/404); línea base **B0** reconstruida con AnCora y SQuAD-es
(`experiments/nube_base.py`, `nube_educar.py`). Sus cifras **no son comparables** con el 35,9 % histórico.

## Banco nuevo y juez
- [`congelado_g103`](kiosco/congelado_g103/LEEME.md): 31 negocios, 838 turnos, 8 redactores independientes de 4 familias de modelo, escrito después de congelar y registrado en git (`292e27f`) antes de ejecutar Leobot.
  Seis negocios repiten un sector de la enseñanza (declarado antes de medir).
- Juez ciego doble sobre 485 respuestas no triviales de cinco sistemas mezclados: 16 jueces Opus y 16 Sonnet, desacuerdo 21/485 (4,3 %), desempate con Opus nuevo.
  Rúbrica declarada antes ([encargo](kiosco/encargo_juez_g103.md)). Incidente: jueces en paralelo compartieron un directorio temporal; se comprobó que cada `veredictos.json`
  trae exactamente los ids de su `items.json` y se repitieron cinco jueces cuyo archivo se perdió. Datos en [evaluacion_g103](kiosco/evaluacion_g103/).

## Resultado con el juez (directas + sí/no con respuesta, n = 383, 31 negocios)
| sistema | útiles | citas | engañosas | sin respuesta bien | inventadas |
|---|---|---|---|---|---|
| B0 (motor con confianza de siete rasgos) | 99 (25,8 %) | 222 | 19 (8,6 %) | 212/214 | 0 |
| + coincidencia por prefijo | 118 (30,8 %) | 264 | 23 (8,7 %) | 211/214 | 0 |
| tratamiento (modelo con pares, G-103) | 124 (32,4 %) | 289 | 34 (11,8 %) | 209/214 | 0 |
| modelo sin pares (solo rasgos densos) | 125 (32,6 %) | 257 | 26 (10,1 %) | 211/214 | 0 |
Bootstrap por negocio (10 000): tratamiento − B0 **+6,5 puntos [+2,8, +10,4]**; tratamiento − sin pares **−0,3 [−5,2, +4,7]**; sin pares − B0 +6,8 [+3,6, +10,1].
Conteo automático (claves) coincide: 92 / 112 / 115 / 116 de 383. Pares barajados: 74. Otro negocio: 0 útiles.

## Puertas preregistradas
**G-103** ([prereg](../prereg/G-103-modelo-de-utilidad-por-candidata.md), enmienda 1): 1) ≥ B0 + 8 puntos: **+6,5, falla**; 2) mejor que sin pares (+3) y que barajados (+5): **falla frente a sin pares (−0,3)**;
3) engañosas ≤ 6 % y ≤ 1 punto peor que B0: **11,8 % (+3,2), falla**; inventadas 0 (pasa); 4) sin respuesta 97,7 % (pasa), otro negocio 0 % (pasa);
5) latencia de `answer` p95 2,25 ms (≤ 10 ms pasa) pero 7,7 veces la de B0 (0,29 ms): **falla** el «no más de 20 % peor»; reinicio y `PYTHONHASHSEED` 0/1/2 idénticos (pasa).
**No se promueve.**
**G-104** ([prereg](../prereg/G-104-continuidad-del-tema.md)), seguimientos, conteo automático (n = 106): B0 15, prefijo 19, tratamiento 33, sin historial 30, historial barajado 28, sin pares 24.
Con historial frente a sin historial +3 (2,8 puntos) y frente a barajado +5: **falla el +5 puntos**. Directas + sí/no 115 frente a 110 (pasa). No se promueve el historial como mecanismo aparte.
**G-105** ([prereg](../prereg/G-105-seguir-instrucciones-del-negocio.md)), turnos de tipo instrucción o acción derivar (n = 116), rúbrica nueva (un «No lo sé» sin salida es `honesta`):
sin instrucciones 2 útiles y 5 engañosas; con instrucciones **22 útiles (19,0 %) y 6 engañosas (5,2 %)**; sin pares 7 útiles. **+17,2 puntos frente al umbral de +25: falla; engañosas 5,2 % frente a ≤ 5 %: falla.**
Directas + sí/no y sin respuesta sin cambio (124/383; 209 frente a 210 de 214). La salida al faltar el dato no se aprendió (19 negocios de 216 la traen; precisión cruzada 0), queda apagada y su criterio 4 no se cumple.

## Qué se aprendió (sin maquillar)
1. **La validación cruzada en desarrollo sobrestimó las asociaciones aprendidas.** Con bancos gastados, por negocio, por banco, por grupo de sector y con corte temporal, los pares sumaban 5 a 9 puntos (AUC 0,82 → 0,87);
   en un banco nuevo de sectores más raros suman 0 en preguntas del texto. Sí ayudan a citar instrucciones (22 frente a 7 útiles) y a los seguimientos (33 frente a 24, automático). Causa sin identificar:
   sector, estilo de redactor y familia de modelo son candidatos; no está probado.
2. **Lo que sí transfirió:** emparejar palabras por prefijo (+19 útiles con el juez, engañosas sin cambio) y un modelo de rasgos generales (+7 puntos en total con el bootstrap frente a B0).
3. **El costo es de citas engañosas:** 19 → 34 en términos absolutos con el modelo de pares (26 sin pares), porque cita más. El umbral se igualó en citas sobre lo no respondible, no en engañosas.
4. **Descartados en desarrollo, con cifras:** historial siempre activo (daña las independientes), sinónimos de WordNet, secciones jerárquicas, proximidad y bigramas, mostrar dos unidades cuando dudo
   (11 aciertos de la segunda frente a 64 de la primera), segunda unidad por complemento de cobertura (29 claves recuperadas contra 148 turnos ya cubiertos que recibirían una unidad extra).
5. **Pendiente sin tocar:** cuentas y datos repartidos (combinada 8 % de los turnos, 2/70 con el tratamiento): 55 % de esos turnos tienen las claves literales en el texto (dos unidades cubren 53 % frente a 35 % de una),
   45 % piden un total calculado.

## Costos y latencia
Enseñanza final: 457,6 s de CPU (extracción 20,7 s; validación cruzada de cinco grupos y ajuste final), base 94,9 MB (pares guardados agrupados; límite de carga 100 MiB). `answer`: p50/p95 1,36/2,25 ms con los dos espacios, 0,17/0,29 ms la línea base.
Redactores y jueces: 8 + 32 + 5 repetidos + 6 de desempate subagentes; texto de modelos de lenguaje declarado, nunca entra al motor.

## Sin verificación independiente del código
Los redactores y los jueces son independientes; no se pidió auditor de código (5.10) porque ninguna fase se cerró ni se creó un tag estable.
