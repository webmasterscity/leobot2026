# Instrucciones para trabajar en Leobot

La misión permanente está en `MISION.md`: léela completa al empezar cada sesión y síguela. Si te lanzaron como verificador independiente con un encargo concreto (regla 5.10 de `MISION.md`), haz solo ese encargo.

La continuidad técnica está en `LEOBOT_STATE.md`. Reanuda desde su «Siguiente paso concreto», conserva los resultados negativos y sigue las restricciones del proyecto: el motor operacional de `leobot/` no usa LLM, redes neuronales ni servicios que oculten esas capacidades.

## Investigación científica para problemas difíciles

- Cuando un cuello de botella general resista los mecanismos existentes, busca artículos e investigaciones científicas **recientes y pertinentes**, incluyendo publicaciones de **2026** y de años posteriores conforme avance la fecha. No te limites a trabajos históricos ni supongas que el conocimiento recordado sigue actualizado.
- Prioriza fuentes primarias: artículos originales, actas de conferencias, prepublicaciones de los autores y código o datos oficiales. Comprueba fecha, versión, método, controles, límites y costo. Usa trabajos anteriores cuando expliquen un mecanismo aún relevante.
- Compara la idea encontrada con lo que Leobot ya implementa. Extrae únicamente mecanismos compatibles con sus restricciones; un resultado obtenido con LLM o redes neuronales no demuestra que su parte simbólica funcione por separado.
- Convierte cada idea prometedora en una hipótesis refutable y un experimento pequeño, preregistrado antes de implementar. Mide frente al baseline y las ablaciones, con presupuesto, reserva y costo total. No atribuyas a Leobot una capacidad por el resultado de otro sistema o por haber leído un artículo.
- Registra en `LEOBOT_STATE.md` las fuentes que cambiaron una decisión, el resultado de la prueba y los resultados negativos. Cita enlaces directos. No añadas subsistemas por novedad bibliográfica ni repitas mecanismos que ya existen.
