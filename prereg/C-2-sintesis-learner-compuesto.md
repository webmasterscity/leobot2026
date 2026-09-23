# Preregistro C-2 — síntesis de un learner compuesto

Fecha: 2026-09-22. C-1 dejó un intérprete seguro para dos learners declarativos. Motor de referencia `freeze-C-1`, árbol `3f47e6a514c60c5f29665d2468f95785b97c8371`. C-2 es el ensayo decisivo de la fase C.

## Fallo observado e hipótesis rivales

Con ocho valores de signo y un contexto numérico que cambia el umbral del conteo, una sonda de desarrollo dio 50/128 en casos nuevos y costó 28,2 s de CPU. Proyección, plegado agregado y programas meta actuales no encontraron la regla completa. La explicación candidata es que falta un learner que combine extractores y valide su composición. Alternativa: bastaría aumentar presupuesto o añadir una rama manual para la tarea; no se hará. Si el control existente con igual presupuesto y datos alcanza el umbral, la síntesis no añade capacidad y no se promueve.

## Sustrato y learner que puede emerger

El MetaController podrá construir **programas de learner como datos** combinando dos extractores tipados de un conjunto genérico: índice numérico, comparación con cero, comparación entre posiciones y plegado booleano sobre un segmento contiguo acotado. El producto de sus salidas forma una partición que un verificador común evalúa dejando experiencias fuera y separando bloques temporales. El generador examina distintas posiciones, segmentos, reductores y órdenes bajo el mismo límite; ningún campo nombra tarea, familia, entidad ni respuesta. La combinación útil, sus operandos, su búsqueda y umbrales deben seleccionarse desde experiencias. No se permite `eval`, shell, Python generado, cambios al repositorio ni lectura de evaluadores. El intérprete finito es el sandbox.

El controlador detectará un hueco tras agotar los learners actuales, propondrá hasta cuatro descripciones candidatas variando composición y verificador dentro del DSL, comparará sus resultados con los learners base bajo idéntica información y presupuesto, promoverá solo una descripción que generalice y registrará sus fuentes, costo y rollback. En una segunda familia intentará reutilizar la descripción aprendida antes de repetir la búsqueda. Si funciona, se elimina la rama actual de rechazo definitivo cuando ninguno de los learners individuales sirve; no se agregan reglas por dominio.

## Familias y partición

- Desarrollo F1: 128 experiencias de nueve rasgos, un contexto numérico de signo y ocho valores con signos y magnitudes variables. La etiqueta depende de cuántos valores cumplen la comparación y de cuál condición de contexto se observa. El contexto varía de magnitud para que recordar valores exactos no sirva. La sonda visible descrita arriba es desarrollo, no reserva.
- Desarrollo F2: 128 experiencias de otra disposición: un contexto expresado por la relación entre dos valores de centro variable y ocho valores individuales. La composición abstracta «contexto binario más resumen de una secuencia» puede transferir, pero las posiciones y el extractor de contexto cambian. Se enseñará F2 después de F1 con el mismo motor.
- Reserva: 128 configuraciones nuevas por familia y orden, con centros, magnitudes, símbolos y distribución distintos, generadas **solo después de `freeze-C-2`** con los primeros ocho dígitos del árbol del motor más 0, 1 y 2. Órdenes de enseñanza 17, 53 y 97. Los resultados no se usan para ajustar el DSL.

## Controles y umbrales

Tratamiento con síntesis, ablación sin síntesis, fresco, solo memoria, misma información, estructura incompatible, contraevidencia, reinicio, reserva estructural, renombrado total y pista auxiliar invertida. Si dos learners explican igual la enseñanza, conservar incertidumbre y pedir una intervención que los separe; el entorno produce la respuesta real. F1 y F2 ≥90 % de respuestas apoyadas en cada orden; controles actuales con la misma información <90 % en F1; F2 educado debe usar menos candidatos o menos CPU que F2 fresco; contraevidencia retira la vista y toda dependencia no sustentada; guardado/carga conserva el learner; no hay errores seguros al invertir la pista. El learner sintetizado debe ser un programa de datos persistido y reutilizado, con código congelado durante todas las experiencias. Regresiones de las capacidades anteriores y puerta fija de latencia antes de tag estable.

Presupuesto: hasta cuatro descripciones de learner, 96 hipótesis estructurales por descripción y orden, profundidad de dos extractores, 30 s de CPU por variante/orden, 256 MiB RAM, `timeout 180s` por orden. Se registran ejemplos, descripciones e hipótesis exploradas, CPU de adquisición, búsqueda, experimento, verificación, promoción/rollback, inferencia, arranque frío y RAM pico. Los costos anidados se identifican como tales. Si el aprendizaje requiere más presupuesto o una solución introducida por el desarrollador, C-2 falla y se conserva como resultado negativo.
