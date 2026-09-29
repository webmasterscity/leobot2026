# G-104 — Continuidad del tema entre turnos como rasgos del mismo modelo de utilidad

Fecha: 2026-09-28. Estado: diseñado (precede al código). Depende de G-103 (modelo de utilidad por candidata, `cb41148`).

## Qué fallo concreto resuelve
`Bot.answer(pregunta, historial)` ignora el historial. Los seguimientos («¿y los domingos?», «¿y para niños?», «¿cuánto cuesta esa?»)
son ≈ 12 % de los turnos de los bancos y hoy solo se acierta la unidad en 45 % (desarrollo, bancos G-62 a G-64, conteo por claves).
G-58r retiró un uso anterior del historial porque producía citas engañosas.

## Por qué los mecanismos actuales no bastan
El diagnóstico previo (`results_v3/nube_diagnostico_1.md`) mostró que arrastrar siempre los términos del turno anterior sube los
seguimientos (top1 0,455 → 0,520) pero **daña las preguntas independientes** (0,580 → 0,521): sin una compuerta el historial pierde.
Una compuerta escrita a mano (palabras como «y») queda prohibida; hace falta que el modelo aprenda cuándo importa.

## Mecanismo
El historial entra como **rasgos del mismo modelo** de G-103, sin compuerta aparte:
1. Del historial se toma el último turno del cliente que pregunta algo. Sus palabras que no están en la pregunta actual y la unidad
   que esa pregunta obtiene por sí sola (sin historial) son «el tema anterior».
2. Nuevos rasgos por candidata: hay historial; parte de la masa δ de las palabras del tema anterior que la candidata explica; comparte
   encabezado con la unidad anterior; es la unidad anterior; ganancia de la mezcla para el tema anterior; y dos productos
   (esas dos señales por «lo poco que la pregunta actual explica por sí sola»).
3. El grupo de candidatas se forma con la mezcla de la pregunta actual más medio peso de la del tema anterior; los demás rasgos siguen
   usando solo la pregunta actual. Sin historial nada cambia.
4. El modelo se enseña con los mismos turnos, ahora con el turno anterior de su conversación. Sin listas de palabras, sin ramas por
   tipo de pregunta: si el historial no ayuda a una pregunta independiente, el modelo aprende a ignorarlo.
`answer` sigue sin guardar nada de la persona: usa solo el historial que recibe.

## Qué eliminaría si funciona
La nota «G-58r no usa el historial» y el argumento de que hay que retirar el seguimiento.

## Experimento que distingue las hipótesis
El mismo banco nuevo de G-103, con sistemas: tratamiento con historial; sin historial (interruptor `history_features` apagado, mismo
modelo); historial barajado (el turno anterior de otra conversación del mismo banco: señal confundida); B0.
Juez ciego doble como en G-103.

## Umbrales de éxito (fijados ahora)
Con el juez, entre los turnos de tipo seguimiento con respuesta:
1. Útiles con historial ≥ útiles sin historial + 5 puntos porcentuales, y también > historial barajado + 5 puntos.
2. Directas + sí/no: útiles con historial ≥ útiles sin historial − 1 punto.
3. Citas engañosas con historial no más de 1 punto peores que sin historial; inventadas: 0.
4. Latencia de `answer` con historial: p95 ≤ 10 ms.
Si 1 falla, el historial no se promueve (queda el interruptor apagado en la base congelada) y se conserva el resultado.

## Cifras de desarrollo ya vistas (no cuentan como evidencia de éxito)
Diagnóstico con la mezcla de B0: seguimientos top1 0,455 → 0,520 con términos + sección siempre activos; independientes 0,580 → 0,521.

## Riesgos declarados
El texto de los turnos previos viene de conversaciones escritas por modelos de lenguaje, en las que cada seguimiento se sigue de un turno
bien formado. Las cadenas de varios seguimientos solo se ven a un turno de profundidad.
