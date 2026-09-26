Superior a las anteriores: **sí**, por poco. Frente a `estable-G-18` iguala con texto limpio y gana con texto partido. Frente a G-63 casi empata.

# Auditoría 5.10 de G-64 (unir renglones partidos usando el ancho del documento)

Auditor independiente (Claude Opus 5.5, copia aislada en `G-64` = `b8343ff`), 2026-09-26. Motor `freeze-G-64` = `11a1ef58`, igual al de la rama `G-64`.

## Qué comprobé y qué salió

1. **Orden en git: correcto.**
   - Preregistro `c4030f7` (08:55:17), luego el motor V2 `848baea` = `freeze-G-64` (08:57:54).
   - El commit del preregistro también trae el motor de G-63, idéntico a `freeze-G-63`. La tabla de desarrollo se corrió después (`g64_dev.log`, 08:56:48) y cuadra con el preregistro.
   - El banco `congelado_g64` entró en `2ad30e5` (09:23:48), después de congelar y antes de cualquier resultado. La evaluación corrió a las 09:24; los resultados entraron en `00f6de1`.
2. **Reproducción: exacta.**
   - 12 de las 13 variantes del evaluador (todas las de G-64 y las 4 de `estable-G-18`) dan 585/585 respuestas idénticas a las guardadas.
   - `partido` con `PYTHONHASHSEED=1`: 585/585.
   - La regresión completa da 669/6/0.
   - El control de renombrado recalculado da lo mismo: 97,8 % tal cual, 97,1 % partido y 95,4 % en `estable-G-18` partido.
   - REINICIO_PENDIENTE
3. **Puertas del juez: idénticas** a `juez_puertas.json`, con 0 turnos sin juicio.
   - Revisé a mano 26 veredictos contra los textos: los 23 turnos donde G-64 y `estable-G-18` difieren, la pregunta sin respuesta perdida y una muestra al azar. Todos son razonables.
   - El juez es indulgente con las citas cortadas («duran 50», «a las 10:00 a»). Eso favorece a `estable-G-18`.
4. **Trampas (5.7): ninguna.**
   - El cambio toca solo `leobot/context.py` (`_unwrapped`). Son reglas de forma: largo del renglón, primera palabra del siguiente y el umbral de «4 cortes y 20 %», declarado antes de medir.
   - No hay listas de palabras, ni ramas por negocio o por pregunta, ni lectura de bancos o resultados.
   - Con texto limpio, la prueba del ancho no se activa en ninguno de los 216 negocios de los bancos. En MFAQ se activa en 1 de 390 páginas, que de verdad viene partida.

## ¿Es superior? Con números

**a) Frente a `estable-G-18`:**
- **Texto tal cual:** 585/585 respuestas idénticas. Útiles 102 = 102 y engañosas 4,4 % = 4,4 %.
- **Texto partido a 70, puerta 1 (juez, directa + sí/no):** 102 frente a 95 (+2,6 puntos). No pasa la vara de +5 puntos.
- **Engañosas con texto partido:** 4,3 % frente a 7,1 %. Evita 8 y crea 3; el preregistro dice «evita 5, crea 1» porque cuenta solo directa + sí/no.
- **Inventadas:** 0 en los dos.
- **Preguntas sin respuesta:** 157/158 frente a 158/158. Es el turno W2/n6 3,2, que el texto limpio también falla.
- **Controles:** pasan.
  - Sin unir = `estable-G-18` partido.
  - Otro negocio: 0 útiles.
  - Renombrado: arriba.
- **MFAQ normalizado:** 57,31 %. Lo medí también para `estable-G-18`, que no estaba medido: 57,24 %.
- **MFAQ original:** 56,01 % frente a 57,24 % (−1,2 puntos). Es el artefacto declarado: una unidad unida lleva un espacio donde había un salto de línea. G-64 no lo informó.
- **SQuAD-es y conversación:** 0,8013 y 158, iguales. Son cifras guardadas; no las volví a correr.
- **Latencia (p95):** entre −2,5 % y +2,9 %, con 220 MB en los dos.
- **¿Peor en algo medido?** Solo en detalles menores: MFAQ original, una pregunta sin respuesta y tres engañosas nuevas. Nada rompe una puerta.

**b) Frente a G-63 (lo corrí en el banco de G-64, texto partido a 70):**
- **Conteo automático:** 86/266 frente a 90 de G-64 y 73 de `estable-G-18`. G-64 gana 5 turnos y pierde 1.
- **Juez:** 553/585 respuestas coinciden con G-64, y ahí vale el mismo juicio. Con eso, G-63 suma 97 útiles.
  - De sus 7 turnos de directa + sí/no sin juicio, a mi juicio 3 o 4 son útiles, así que G-63 queda en unos 100–101 frente a 102.
- **Texto limpio:** las dos versiones unen igual los 216 negocios, así que la diferencia es nula.
- **MFAQ:** normalizado 57,31 en las dos; original 56,01 frente a 55,97.
- **Resumen:** G-64 nunca es peor que G-63, pero la ventaja es pequeña y no significativa.

**c) ¿La ganancia con texto partido es real?** Remuestreé por negocio (20 000 veces):

| Medida | Diferencia | Turnos ganados / perdidos | IC 95 % | P(≤ 0) |
|---|---|---|---|---|
| Puerta 1 (juez, directa + sí/no) | +7 | 15 / 8 | [−3, +17] | 0,10 |
| Juez, todas las preguntas con respuesta (no preregistrado) | +15 | 27 / 12 | [+1, +29] | 0,02 |
| Conteo automático, directa + sí/no | +17 | 23 / 6 | [+8, +25] | 0,0002 |

Los 8 turnos perdidos no son daño de G-64. En ellos el corte ayudó por azar a `estable-G-18`: con el texto limpio, ninguno de los dos sistemas los acierta. G-64 con texto partido contesta igual que con texto limpio (102 = 102, sin diferencias pregunta por pregunta).

## Objeciones

1. **La ganancia de la puerta 1 no es significativa por sí sola** (P ≈ 0,10). Solo lo es con el conteo automático o contando todos los tipos de pregunta, y ese análisis no estaba preregistrado.
2. **G-64 no pasa su propia puerta 1.** Entra por excepción del usuario, no porque la cumpla. El argumento del «techo» (+2,6 era el máximo posible) se calculó después de medir, aunque el techo es real.
3. **Frente a G-63 casi no hay diferencia** en datos nuevos: +4 automático y unos +1 o +2 con juez. La ventaja de +27 era de desarrollo.
4. **La vara de MFAQ:** con el evaluador original, G-64 queda 1,2 puntos por debajo de `estable-G-18`. Pasa gracias a una medida nueva, normalizada, declarada en G-63 antes de medir. Con esa medida, `estable-G-18` también da 57,24 %, así que la comparación es justa.
5. **Pequeños retrocesos por turno:** 3 engañosas nuevas, una de ellas ante una pregunta sin respuesta, y 1 pregunta sin respuesta mal llevada con texto partido.
6. **El texto partido de la prueba es mecánico:** se corta con `textwrap` a un ancho fijo. En textos reales el corte puede ser distinto (guiones al partir palabras, anchos variables, columnas), y la regla toma como ancho el renglón más largo. No se midió con textos partidos reales, salvo la única página de MFAQ.
7. **Detalles de proceso:**
   - El desempate entre V2 y V3 se escribió después de ver los números (se dice).
   - En desarrollo, «idénticas a `estable-G-18`» comparaba en realidad con «sin unir».
   - La medida del renombrado se precisó después de congelar el motor, antes de que existiera el banco.
   - El banco lo escribieron modelos de lenguaje (declarado), y W3 escribió menos turnos de los pedidos.
8. **Memoria:**
   - Por la RAM compartida, corrí cada variante en su propio proceso, con el mismo código (`g64_evaluar.one`). El trabajador único del evaluador crecía hasta dejar menos de 2 GB libres.
   - SQuAD-es, conversación y latencia no se volvieron a correr: son cifras guardadas.

Archivos del auditor: `aud64/` en el cuaderno de la sesión.

## En palabras fáciles de entender

Cuando alguien pega en el kiosco un texto con los renglones cortados, la versión nueva vuelve a unir las frases mirando el ancho del propio texto. Revisé que se probó con negocios nuevos escritos después de congelar el programa, que no hay trampas y que al repetir la prueba sale exactamente lo mismo. Con texto normal contesta igual que la versión anterior. Con texto cortado contesta un poco mejor (102 frente a 95 de 266 preguntas) y confunde menos. La mejora es pequeña y, con la medida acordada, podría ser en parte suerte. Frente al intento anterior (G-63) es casi un empate. No encontré nada en que sea claramente peor.
