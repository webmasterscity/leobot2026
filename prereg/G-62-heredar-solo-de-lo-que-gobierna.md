# G-62 — cada línea hereda solo de lo que de verdad la gobierna

Fecha: 2026-09-26. Preregistro previo al commit del motor. Base: `freeze-G-61`. Prioridad del usuario en `MISION.md` («Prioridad actual»).

Es una capacidad general de lectura: saber qué parte de un documento encabeza a cuál.

## Fallo medido

G-61 pasó todas las puertas del kiosco con el juez: 118/301 útiles frente a 96/301 de G-58r. Pero no se promovió, porque MFAQ `valid` bajó: 56,90 % frente a 57,24 %.

El diagnóstico posterior, en desarrollo, midió MFAQ según de dónde se hereda:

| Heredar de | MFAQ |
|---|---|
| todo encabezado (G-61) | 56,90 % |
| encabezados con marca (markdown, mayúsculas, dos puntos) y preguntas | 57,05 % |
| solo markdown y mayúsculas, y preguntas | 57,31 % |
| solo preguntas | 57,31 % |

Lo que falla son las líneas cortas sin marca y las que terminan en dos puntos cuando se toman como título de toda la sección.
- En una página de preguntas frecuentes, «Los requisitos son:» dentro de una respuesta gobernaba también todas las respuestas siguientes.
- En un negocio, «Extras:» sí gobierna la lista que presenta, pero esa lista termina en la línea en blanco.

## Cambio (5.8)

**1. Alcance de la herencia**, en `_layout_units`. Es una regla de maquetación, no de palabras:
- una pregunta (de preguntas frecuentes o la que abre su renglón) gobierna su respuesta, como en G-61;
- un título marcado por la tipografía (markdown o todo en mayúsculas, sin dos puntos al final) gobierna toda su sección;
- una línea que termina en dos puntos presenta solo su bloque, hasta la siguiente línea en blanco;
- una línea corta sin marca puede ser contenido y no gobierna nada. Sigue siendo el `heading` de la unidad, pero no se hereda.

El control `inherit_all_headings` devuelve el alcance de G-61.

**2. Sin cambio:** la pregunta en línea de G-61 y la confianza contada citando desde 0,4. La confianza se recuenta con el motor nuevo en los 6 bancos gastados: G-57, G-58, G-59, G-60, G-61 y A–F.

**Por qué los mecanismos actuales no bastan:** G-61 hereda sin distinguir un título de una línea cualquiera.

**Qué experimento distingue:** los controles «herencia de todo encabezado» (G-61) y «sin herencia», en el mismo banco, más MFAQ.

**Qué se elimina si funciona:** nada. Se estrecha una pieza de G-61.

**Cifras de desarrollo.** Validación cruzada: se prueba en la mitad de los negocios de G-59 y G-60 que no se usó; conteo por claves; con los conteos de la confianza de G-61.

| Sistema | Útiles en directa + sí/no (de 538) | Citas | Citas útiles | Citas sin dato | MFAQ |
|---|---|---|---|---|---|
| G-58r (medido) | 161 | 369 | 199 | 80 | 57,24 % |
| G-61 | 205 | 392 | 250 | 48 | 56,90 % |
| **G-62** | **201** | **395** | **244** | **52** | **57,24 %** |

**Declarado antes de medir:** MFAQ queda justo igual que G-58r (57,24 %). La puerta «no menor» pasa por igualdad, sin margen. Si en la medida final sale menor, G-62 no se promueve.

## Medida

Congelado `freeze-G-62`; semilla de su huella.

**A. Banco congelado nuevo.**
- 24 negocios de 24 sectores distintos de los 144 anteriores.
- 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), de 4 modelos, con el encargo neutral de siempre.
- En git antes de ejecutar.

**B. Juez ciego** (8 jueces nuevos, Opus, encargo de G-58). Califica, mezclados, G-62, G-58r y las respuestas que cambian en los controles.

**Umbrales de éxito (banco congelado, juez), los mismos de G-61:**

| Puerta | Umbral |
|---|---|
| 1. Útiles en directa + sí/no | ≥ G-58r + 5 puntos en el mismo banco |
| 2. Citas engañosas | ≤ 15 % y no más de 2 puntos por encima de G-58r |
| 3. Inventadas · respuestas planas | 0 · error ≤ 2 % si las hay |
| 4. Sin respuesta bien llevadas | ≥ 90 % |
| 5. Eco de datos | 0 |

**6. Controles:**
- herencia de todo encabezado (G-61);
- sin herencia;
- sin pregunta en línea;
- rasgos barajados;
- otro negocio: útiles ≤ 5 % y «No lo sé» ≥ 80 %;
- reinicio: 100 %;
- renombrado estricto: ≥ 95 %.

**7. Pruebas generales sin retroceso, frente a G-58r:**
- MFAQ `valid` contestando siempre: ≥ 57,24 %;
- SQuAD-es, unidad con la respuesta: ≥ 0,7987;
- conversación 158;
- regresión completa sin fallos;
- latencia 5.6: p95 de `answer` ≤ 10 ms;
- tablero y sonda sin cambio.

**Retención 5.9:**
- el alcance nuevo se queda si da al menos los útiles de «sin herencia» + 3, sin subir las engañosas más de 2 puntos, y si MFAQ no baja;
- la pregunta en línea, como en G-61.

**Tag estable:** si pasan las puertas y las pruebas generales, con auditoría 5.10 antes del tag.

## Presupuesto

Implementación y conteo ≤ 30 min; banco ≤ 40 min; juez ≤ 1 h; medidas generales ≤ 40 min; auditoría ≤ 1 h. Hasta 16 procesos, con al menos 2 GB de RAM libres.

## Resultado (2026-09-26, banco congelado de 24 negocios nuevos y 647 turnos; juez ciego de 8 jueces nuevos, Opus)

| Puerta | Umbral | G-62 | G-58r, mismo banco | ¿Pasa? |
|---|---|---|---|---|
| 1. Útiles en directa + sí/no | ≥ G-58r + 5 puntos | **99/276 (35,9 %)** | 69/276 (25,0 %) | **sí (+10,9)** |
| 2. Citas engañosas | ≤ 15 % y ≤ G-58r + 2 puntos | **5/199 (2,5 %)** | 2/149 (1,3 %) | sí (+1,2) |
| 3. Inventadas · planas | 0 · — | **0** · ninguna | 0 | sí |
| 4. Sin respuesta bien llevadas | ≥ 90 % | **99,4 %** | 100 % | sí |
| 5. Eco de datos | 0 | **0** | 0 | sí |

El 68,3 % de las citas de G-62 son útiles, frente al 67,1 % de G-58r. Contestando siempre (conteo automático): 134/276 frente a 126/276.

**Controles:**
- alcance de G-61 (todo encabezado): 103/276, con 2,0 % de engañosas. Da 4 útiles más en el kiosco, pero es el alcance que bajaba MFAQ.
- sin herencia: 86/276 (2,8 %);
- sin pregunta en línea: 93/276 (2,5 %);
- rasgos barajados: 13/276 y 26,4 % de citas útiles. La confianza contada importa.
- otro negocio: 1/276 útil (0,4 %) y 580/647 «No lo sé» (89,6 %).
  - Los jueces marcaron 9 de sus citas como «inventadas»: son texto literal del documento cargado, que es de otro negocio, igual que en G-59 y G-61.
  - De sus 36 citas, 20 engañan: la objeción 2 de G-58r sigue abierta.
- reinicio: 647/647;
- renombrado estricto: 640/647 (98,9 %).

**Retención 5.9:**
- el alcance nuevo da 99 útiles frente a 86 sin herencia (+13, pedía ≥ +3), con engañosas 2,5 % frente a 2,8 %, y MFAQ no baja. **Se queda.**
- la pregunta en línea da 99 frente a 93 (+6), con engañosas 2,5 % frente a 2,5 %. **Se queda.**

**Pruebas generales (`freeze-G-62`):**
- MFAQ `valid` contestando siempre: **57,24 %**, igual que G-58r. Pasa «no menor» por igualdad, como se declaró antes de medir.
- SQuAD-es: unidad con la respuesta 0,8013 (G-58r 0,7987), F1 0,2485;
- conversación 101/21/36 = 158;
- regresión 667/6/0;
- latencia intercalada con `estable-G-17`, 3 rondas × 3 semillas ([resumen](../results_v3/latency_rounds_g18/resumen.json)): p95 entre −7,6 % y +1,2 %, límites pasan, RAM 220 MB. p95 de `answer` en el banco: 0,26 ms.
- tablero: MLQA con bot fresco 0/20, sin cambio;
- sonda de lectura: 0/4, sin cambio.

**Defectos vistos por los jueces, declarados:**
- Una frase corta con la que el cliente abre su pregunta («Mi mamá camina poco.») se repite como saludo antes de la cita. Es el eco breve de la objeción 3 de G-58r; la puerta 5 no lo mide.
- Con el documento de otro negocio, las citas engañan más de la mitad de las veces.

**G-62 supera sus puertas.** Queda pendiente la auditoría 5.10 antes del tag.
