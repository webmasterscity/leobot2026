# E-5 — Fragmentos de cláusula como candidatos de relación

Preregistrado antes de cambiar el motor. E-4 halló 0/20 respuestas en argumentos de hasta ocho palabras, aunque el bot educado creó 47 hechos. La causa candidata es que la antiunificación recibe oraciones completas y absorbe varias cláusulas en un solo argumento. La alternativa sencilla es seguir con el aprendiz actual y aportar fragmentos separados por puntuación como experiencia adicional. Si eso no mejora cobertura breve sin aumentar falsos hechos, se descarta.

## Mecanismo mínimo y admisión

Dentro de `ingest_document_text`, solo para una oración no interpretada de más de 16 tokens y que ya quedó como observación cruda, dividir por coma, punto y coma o dos puntos; conservar únicamente trozos de 4 a 16 tokens y como máximo tres trozos por oración. Cada trozo es una observación provisional con procedencia propia y entra en el aprendiz de relaciones crudas **existente**. No se añade parser, léxico, regla por dominio ni respuesta fija. La ruta puede desactivarse en la misma llamada para la ablación. Si sirve, elimina la necesidad de añadir manualmente gramáticas para cada cláusula, pero no sustituye la inducción de relaciones ni resuelve preguntas por sí sola.

## Datos y controles

Usar el archivo MLQA español fijado en E-1, excluyendo los casos de tablero/E-1b/E-2/E-3. Tras congelar el nuevo árbol, seleccionar 30 artículos de educación y 20 artículos de prueba disjuntos con semilla `sha256((<huella> + ':E-5').encode())`. Comparar tratamiento con fragmentos y ablación con el mismo texto sin fragmentos; añadir bot fresco y control de fragmentos con tokens barajados de forma determinista, que preserva longitudes y vocabulario pero destruye orden. Se mide cobertura de la respuesta en argumentos de hasta ocho tokens y en cualquier argumento, respuestas exactas, promociones y hechos del artículo de prueba. El evaluador nunca enseña respuestas al bot. Un fragmento coincidente no prueba comprensión.

Guardar/cargar antes de probar y comparar cobertura. Un documento posterior que niegue una relación promovida debe impedir afirmar su versión positiva con seguridad; si no, se registra fallo de revisión y no se promueve como lector confiable. La tarea incompatible son cláusulas barajadas. El bot fresco y la ablación comparten información del artículo de prueba. Huella del motor idéntica antes/después del ensayo. La reserva se genera tras congelar, no se ajusta código mirándola.

## Umbral y presupuesto

Para conservar el mecanismo como mejora de representación: tratamiento ≥5/20 respuestas en argumentos breves y al menos cinco casos por encima de la ablación; cobertura en cualquier argumento no menor que la ablación; cero respuestas nuevas falsas afirmadas con seguridad; en la tarea barajada, no más de dos promociones extra que en la ablación barajada. Si falla, revertir el cambio de motor, conservar el resultado y registrar el siguiente diseño. El cumplimiento no superaría la fase E: faltaría respuesta literal, inferencia, procedimiento, referencia y contradicción. Presupuesto: 30+20 artículos por brazo, 80 MiB descarga, 120 s CPU, 180 s pared; pruebas rápidas ≤40 s por corrida. Semillas de hash 0/1/2 si varía un conteo.
