# Preregistro A-1: reutilización de una subregla meta

Fecha: 2026-09-22. Estado: diseñado. El motor aún no contiene la variante A-1.

## Fallo, alternativa y mecanismo

El controlador aprende programas de hasta tres predicados. Una decisión que depende de cuatro comparaciones binarias no cabe en ese límite. En desarrollo, la búsqueda plana devolvió `meta_program_rejected` sobre 48 tareas equilibradas de cuatro comparaciones. La causa candidata es la ausencia de una subregla reutilizable. La alternativa sencilla es que el enrutador o una proyección ya resuelvan la tarea; por eso se miden como controles.

Se intentará reconocer una misma partición de salidas aprendida en dos familias independientes de dos comparaciones, compilarla como función opaca parametrizada por posiciones relativas, y admitir sus aplicaciones como predicados de una búsqueda externa de tamaño dos. El motor no recibirá XOR, paridad, nombres de familias ni respuestas como primitivas. No se aumentarán los límites de profundidad ni de predicados de la búsqueda plana. Si funciona, se evita programar un nivel de profundidad nuevo para esta clase; se conserva la búsqueda actual como respaldo.

## Familias y partición

- Desarrollo: dos familias de 32 tareas cada una, con cuatro rasgos numéricos y dos comparaciones cuyo resultado conjunto determina la estrategia útil. Sus escalas numéricas y nombres de estrategias difieren. La familia de aplicación contiene 64 tareas con ocho rasgos, cuatro comparaciones y las 16 combinaciones repetidas cuatro veces; los centros numéricos varían entre tareas. La regla útil combina dos aplicaciones de la subregla, cada una sobre cuatro rasgos.
- Reserva estructural: 160 tareas nuevas por orden de datos, con centros, magnitudes y nombres distintos. Se generan solo tras congelar el commit del motor, usando como semilla la primera parte hexadecimal de `git rev-parse freeze-A-1:leobot`, más los desplazamientos 0, 1 y 2. El código que genera y puntúa la reserva vive fuera de `leobot/`. No se inspeccionan ni ajustan los resultados para modificar este preregistro.
- Los órdenes de adquisición de desarrollo se fijan con semillas 17, 53 y 97. La reserva usa esas tres órdenes y sus semillas derivadas de la huella. Las estrategias también se renombran en una repetición.

## Controles

1. Tratamiento: experiencias de ambas familias fuente y de la tarea profunda, con compilación y reutilización activas.
2. Ablación y misma información: idénticas experiencias, sin admitir piezas compiladas en la búsqueda; se conservan el enrutador, la memoria y la búsqueda plana de tres predicados.
3. Fresco: solo experiencia de la tarea profunda. Solo memoria: todas las experiencias, sin inducción de programas ni piezas.
4. Incompatible: tarea de ocho rasgos con la misma superficie numérica pero distinta partición de salidas; una pieza útil no debe certificarse como respuesta sin aprendizaje específico.
5. Contraevidencia: invertir de forma consistente la evidencia de una fuente; debe invalidar la pieza dependiente y dejar de usar las decisiones que dependen de ella. Se comprobará también tras guardar y recargar.
6. Señal confundida: añadir una comparación auxiliar que coincida con la salida durante adquisición y se invierta en reserva. Se ofrece al motor una intervención realizable que separa las explicaciones. Antes de recibir el resultado, no debe presentar una elección falsa con confianza; después solo puede cambiar por la observación real.
7. Renombrado total: cambiar nombres de familias y estrategias sin cambiar la estructura; la mejora debe mantenerse.

## Métricas, umbrales y presupuesto

Se cuentan aciertos y abstenciones en reserva, errores con confianza, ejemplos, programas y aplicaciones candidatos, tiempo y CPU de adquisición, búsqueda, prueba, validación, consolidación e inferencia, y memoria máxima. Se separan arranque frío, primera adquisición y reutilización. Se calcula el costo total por tarea, no solo la latencia de la respuesta.

Para superar A-1: al menos 90 % de aciertos en la reserva en las tres órdenes; ablación claramente peor o al menos cinco veces más candidatos; contraevidencia y reinicio correctos; cero elecciones falsas presentadas como seguras en la señal confundida; renombrado sin pérdida. La ventaja debe venir de una pieza adquirida de las fuentes, no de una función escrita con la respuesta.

Presupuesto por orden: 32 tareas por fuente, 64 de aplicación, 160 reservadas; máximo 32 aplicaciones candidatas de la pieza por tarea de aplicación, límite plano actual de tres predicados, 30 segundos de CPU para adquisición y validación por variante, 256 MiB de RAM pico. La ejecución completa usa `timeout 180s`. Si se excede, el resultado es fallo de presupuesto y se conserva; no se suben límites ni se cambian umbrales después de ver la reserva.

El criterio que refuta la causa candidata es que la ablación resuelva igual con costo comparable, o que la pieza no sobreviva a cambio de escala, renombrado, contraevidencia o reinicio. Si aparece una nueva explicación, se preregistra otro diseño antes de tocar el motor.
