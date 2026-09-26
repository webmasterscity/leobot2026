# G-61 — cada línea se lee bajo su encabezado, y se cita tanto como G-58r pero eligiendo mejor

Fecha: 2026-09-26. Preregistro previo al código del motor. Base: `freeze-G-60`. Prioridad del usuario en `MISION.md` («Prioridad actual»). El plan 3 del coordinador guía; esto se aparta de su punto de operación, con la razón abajo.

Es una capacidad general de lectura: entender una línea dentro de su sección, como hace una persona.

## Fallo medido (bancos gastados de G-57, G-58, G-59 y G-60 y desarrollo A–F; conteo por claves)

**1. La unidad buena queda primera en 885 de 2050 preguntas con respuesta (43 %).**
- En preguntas directas, en 857 de 919 la respuesta está en una sola unidad, pero solo en 427 queda primera.
- Cuando pierde, en 262 de 430 casos tiene menos palabras de la pregunta que la ganadora.
- Una muestra de fallos muestra la causa: las palabras que faltan están en el encabezado que gobierna la línea. Por ejemplo, una fila de precios bajo «Extras» o «Tarifas por noche», o una respuesta bajo su pregunta.
- Hoy una unidad no hereda las palabras de su encabezado.

**2. Una pregunta frecuente escrita en la misma línea que su respuesta** («¿Hay parking? El más cercano es…») se parte en dos frases. La pregunta sola gana y no responde.

**3. G-60: citar desde 0,7 deja al kiosco casi mudo.** Muestra algo en 45 de 639 turnos y da 29 útiles, frente a 82 de G-58r. Pero, a igual volumen, sus rasgos citan con más acierto: desde 0,5, el 69 % de sus citas son útiles, frente al 56 % de G-58r.

## Cambio (5.8)

**1. Herencia del encabezado** (interruptor `inherit_heading`).
- Cada unidad responde también a las palabras de su encabezado: la sección que la gobierna o la pregunta de unas preguntas frecuentes.
- Esas palabras se indexan con la unidad.
- Los títulos y las preguntas no heredan nada.

**2. Pregunta en la misma línea** (interruptor `inline_questions`).
- Una frase que termina en «?» y que no es la última de su renglón encabeza las siguientes frases de ese renglón, como una pregunta frecuente.
- Se trata como las preguntas de G-57r: encabeza y nunca es la respuesta.

**3. Confianza de G-60 recontada con el motor nuevo**, en los 5 bancos gastados.
- Punto de operación: cita desde **0,4**.
- Se eligió en desarrollo para citar más o menos tanto como G-58r (392 frente a 369 citas en los bancos de G-59 y G-60), así la comparación es a igual exposición.
- **Por qué no 0,7 (plan 3):** G-60 midió que 0,7 deja el kiosco mudo. A igual volumen, lo que importa es elegir mejor qué citar.

**Qué no se incluye:** el δ recontado en pares de negocio. En desarrollo, a igual número de citas, no añadió nada a la herencia: 205 útiles con 392 citas sin él, 205 con 406 con él. Menos piezas (5.8).

**Por qué los mecanismos actuales no bastan:** la búsqueda solo ve las palabras de la línea.

**Qué experimento distingue:** las ablaciones sin herencia y sin pregunta en línea, en el mismo banco.

**Qué se elimina si funciona:** la tabla de celdas de G-58 como decisora de la cita (queda como respaldo cuando no hay modelo contado).

La herencia y la pregunta en línea se probaron en desarrollo antes de este preregistro, con las cifras de abajo. El código del motor entra en git después de este archivo.

**Cifras de desarrollo** (validación cruzada: se cuenta en todo lo demás y se prueba en la mitad de los negocios de G-59 y G-60 que no se usó; conteo por claves; G-58r nunca vio esos bancos):

| Sistema | Útiles en directa + sí/no (de 538) | Citas | Citas útiles | Citas sin dato |
|---|---|---|---|---|
| G-58r (medido) | 161 | 369 | 199 | 80 |
| Motor de G-60 con pregunta en línea, confianza desde 0,4 | 175 | 362 | 216 | 46 |
| **G-61: además, herencia** | **205** | **392** | **250** | **48** |

## Medida

Congelado `freeze-G-61`; semilla de su huella.

**A. Banco congelado nuevo.**
- 24 negocios de 24 sectores distintos de los 120 anteriores.
- 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), de 4 modelos, con el encargo neutral de siempre.
- En git antes de ejecutar.

**B. Juez ciego** (jueces nuevos, Opus, encargo de G-58). Califica, mezclados y sin decir el sistema, G-61, G-58r y las respuestas que cambian en los controles.

El juez doble del plan 3 queda para cuando se certifiquen respuestas planas: aquí no hay ninguna.

**Umbrales de éxito (banco congelado, juez):**

| Puerta | Umbral |
|---|---|
| 1. Útiles en directa + sí/no | ≥ G-58r + 5 puntos en el mismo banco |
| 2. Citas engañosas | ≤ 15 % de las citas y no más de 2 puntos por encima de G-58r |
| 3. Inventadas · respuestas planas | 0 · error ≤ 2 % si las hay |
| 4. Sin respuesta bien llevadas | ≥ 90 % |
| 5. Eco de datos | 0 |

**6. Controles:**
- sin herencia y sin pregunta en línea (retención);
- rasgos barajados: menos útiles o menos acierto;
- otro negocio: útiles ≤ 5 % y «No lo sé» ≥ 80 %;
- reinicio: 100 %;
- renombrado estricto: ≥ 95 %.

Diagnóstico: contestando siempre, G-61 frente a G-58r.

**7. Pruebas generales sin retroceso:**
- conversación 158;
- regresión completa;
- latencia 5.6: p95 de `answer` ≤ 10 ms;
- tablero y sonda;
- MFAQ `valid` y SQuAD-es (unidad con la respuesta) no menores que G-58r.

**Retención 5.9:**
- la herencia y la pregunta en línea se quedan cada una si su ablación muestra que aporta útiles sin subir las engañosas más de 2 puntos;
- la confianza desde 0,4 se queda si pasan las puertas 1 a 5.

**Tag estable:** si pasa, con auditoría 5.10 antes del tag.

## Presupuesto

Implementación y conteo ≤ 45 min; banco ≤ 40 min; juez ≤ 1 h; medidas generales ≤ 30 min. Hasta 16 procesos, con al menos 2 GB de RAM libres.
