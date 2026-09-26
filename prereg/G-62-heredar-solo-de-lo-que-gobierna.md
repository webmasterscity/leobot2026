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
