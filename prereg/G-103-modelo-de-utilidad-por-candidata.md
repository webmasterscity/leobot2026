# G-103 — Modelo de utilidad por candidata con asociaciones pregunta→unidad aprendidas

Fecha: 2026-09-28. Estado: diseñado (precede al código). Motor de partida: `11a1ef58` (`estable-G-19`). Entorno: sesión de nube,
línea base B0 (`experiments/nube_educar.py`, SHA de la base en `.leobot-data/nube_manifest.json`), no la base histórica con MFAQ.

## Qué fallo concreto resuelve
El kiosco distingue mal «la respuesta está en el texto» de «no está» y elige la unidad con una mezcla de pesos por palabra:
confianza actual AUC 0,78 (validación cruzada por negocio, 4 653 turnos de 9 bancos gastados); acierto de la unidad elegida
0,554 entre los turnos respondibles. Con B0 contesta útilmente 27,9 % de directas + sí/no y se abstiene 797 veces (43 % de los turnos).
El diagnóstico está en `results_v3/nube_diagnostico_1.md`.

## Por qué los mecanismos actuales no bastan
- `_usefulness` es Bayes ingenuo sobre 7 rasgos agrupados; no ve palabras concretas, así que no puede aprender que «cuánto» pide algo con «$»,
  ni que «plata» se contesta con «dinero», ni que «pagar» se parece a «efectivo».
- El puente de δ guarda como mucho 12 palabras por pregunta con apoyo en ≥ 20 dominios de FAQ (B0: 56 palabras).
- Los intentos previos con asociaciones (G-69, G-70) contaban correspondencias competitivas y no las combinaban con los demás rasgos.

## Mecanismo
1. **Candidatas.** Puntuación actual (mezcla δ + puente + clase de respuesta) más *coincidencia por prefijo*: una palabra de la pregunta que
   no aparece en el texto puede coincidir con palabras del texto que comparten al menos 3 letras iniciales y al menos la mitad de la
   longitud de la mayor (ganancia con δ×razón de prefijo). Las 8 primeras unidades (sin encabezados de pregunta) son las candidatas.
2. **Modelo.** Una regresión logística (no red neuronal, biblioteca estándar) sobre cada candidata:
   ~20 rasgos generales (puntuación y distancias entre candidatas, cobertura de la pregunta por palabras propias y heredadas del encabezado,
   δ de lo que no explica, BM25, tipo y largo de unidad, posición, dígitos) más rasgos dispersos «palabra de la pregunta que la unidad no
   tiene | palabra de la unidad» (pares con apoyo ≥ 3 candidatas de entrenamiento), «palabra de la pregunta | forma de una palabra con
   dígitos o símbolos de la unidad» (forma = clases de caracteres, sin lista de palabras ni expresiones por construcción) y tipo de unidad.
3. **Elección y confianza.** La candidata de mayor probabilidad se elige; su probabilidad, calibrada con isotónica sobre puntuaciones
   validadas por negocios cruzados, sustituye a la confianza de siete rasgos. Los umbrales de cita y silencio se conservan (0,4; sin
   respuestas planas nuevas).
4. **Enseñanza.** Solo cuentas y pesos guardados en `context_model`: ningún texto de pregunta ni de respuesta. Datos de enseñanza:
   los 9 bancos gastados (216 negocios, texto de modelos de lenguaje, declarado), etiqueta = la unidad contiene todas las claves del turno
   (o ninguna unidad para preguntas sin respuesta). Los turnos sin ninguna unidad que contenga las claves (cuentas, datos repartidos) no enseñan.

## Qué eliminaría si funciona
El Bayes ingenuo por rasgos agrupados, las celdas `cells`/`admitted` y el puente contado de MFAQ como única fuente de asociaciones.

## Experimento que distingue las hipótesis
Banco **nuevo**, escrito después de congelar el motor por redactores independientes (Agent con `isolation: "worktree"`, encargo neutral
`results_v3/kiosco/encargo_redactor.md`, sectores distintos de los 216 negocios previos; solo se les lee la lista de nombres de sector).
Juez ciego doble (dos familias de modelo) con desempate, sobre todas las respuestas no triviales de todos los sistemas, mezcladas.

Sistemas comparados sobre el banco nuevo: B0 (motor con confianza de siete rasgos); tratamiento; ablación «solo rasgos densos» (mismo
código, sin pares); pares barajados entre candidatas de otros negocios (señal confundida: los pares aprendidos con etiquetas permutadas
entre negocios); otro negocio (preguntas de un negocio contra el texto del siguiente); renombrado estricto de nombres propios;
reinicio (guardar, cargar); `PYTHONHASHSEED` 0 y 1.

## Umbrales de éxito (fijados ahora, no se cambian después de ver el banco nuevo)
Medidos con el juez ciego, entre las preguntas directas + sí/no con respuesta:
1. Útiles del tratamiento ≥ útiles de B0 + 8 puntos porcentuales, y el intervalo bootstrap (por negocio, 10 000 remuestreos) de la
   diferencia excluye 0.
2. Útiles del tratamiento > ablación sin pares + 3 puntos y > pares barajados + 5 puntos.
3. Citas engañosas ≤ 6 % de las citas y no más de 1 punto peor que B0; respuestas inventadas: 0.
4. Preguntas sin respuesta bien manejadas (abstención correcta, o cita honesta): ≥ 97 %; «otro negocio»: ≤ 2 % de útiles.
5. Latencia de `Bot.answer`: p95 ≤ 10 ms y no más de 20 % peor que B0; RAM del proceso ≤ 1,5× la de B0; reinicio y hashseed idénticos
   respuesta por respuesta.
Si 1 falla, el mecanismo no se promueve, con el resultado conservado.

## Presupuesto
Enseñanza ≤ 15 min de CPU en un núcleo; base ≤ 150 MB; sin GPU, sin servicios externos, sin red durante la respuesta.

## Cifras de desarrollo ya vistas (no cuentan como evidencia de éxito)
Validación cruzada por negocio (9 bancos gastados): AUC 0,815 (solo densos) → 0,865 (+ pares); acierto entre respondibles 0,585 → 0,647;
útiles entre respondibles al 10 % de citas sobre lo no respondible 0,291 → 0,401 (actual 0,235). Dejando un banco fuera: 0,816 → 0,868.
Entrenando con seis bancos y probando con los tres últimos: 0,810 → 0,867. Curva: con ~17 negocios de entrenamiento AUC 0,829; con ~172, 0,865.

## Riesgos declarados
- Las asociaciones se aprenden de texto de modelos de lenguaje y se miden con texto de modelos de lenguaje: no equivale a clientes reales.
- Un sector muy distinto puede no compartir asociaciones; el banco nuevo exige sectores nuevos.
- Los bancos gastados ya sirvieron a sesiones anteriores; aquí solo enseñan y validan por negocio, nunca cuentan como reserva.

## Enmienda 1 (2026-09-28, antes de congelar y de escribir el banco nuevo): umbral de cita
Con el umbral 0,4 de la línea base, el modelo cita mucho más y también cita más preguntas sin respuesta (desarrollo, bancos G-62 a G-64:
110 frente a 71 de 488). Comparar a igual umbral mide otra política, no el mecanismo. Regla fijada ahora, con datos de enseñanza y sin
mirar el banco nuevo: el umbral de cita es el menor cuya tasa de citas sobre los turnos sin respuesta de enseñanza, medida con
puntajes cruzados (modelos que no vieron ese negocio), no supera la tasa de la confianza anterior a 0,4 en los mismos turnos
(`experiments/g103_educar.py`, campo `cite_from`; también se guarda `cite_budget`). Se informa además el resultado con 0,4.
Los umbrales de éxito 1 a 5 no cambian.

Cifras de desarrollo con esta regla (enseñado con seis bancos, bancos G-62 a G-64 sin ver; conteo automático, no el juez):
directas + sí/no útiles 228 → 265 (solo prefijos) → 292/816 (tratamiento); citas sin dato 71 → 61 de 488; p95 0,30 → 1,2 ms.
