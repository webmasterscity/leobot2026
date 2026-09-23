# Preregistro B-1 — invención de un operador agregado

Fecha: 2026-09-22. Estado: diseñado. Motor de referencia: `estable-A-1`, árbol `644c55528a5fd97a8822f719f70e11cfae242783`.

## Fallo y explicaciones rivales

El meta-DSL ofrece comparaciones de valores o pares concretos y programas de hasta tres pruebas. Una decisión que requiere resumir muchas posiciones variables pierde la cantidad y la relación entre posiciones. La alternativa sencilla es que las piezas de A o las proyecciones actuales ya basten. Se medirá esa alternativa con la misma información y el mismo presupuesto. Si bastan, no se promueve otro operador.

## Sustrato seguro y mecanismo candidato

Se permite un árbol tipado y acotado con números, booleanos y secuencias; acceso por índice, resta, comparación, conversión de booleano a número, iteración de longitud finita, suma, mínimo y máximo, y comparación final con un umbral aprendido. Son operaciones matemáticas generales, sin nombres de tareas ni respuestas. Un generador declarativo producirá hasta 32 programas candidatos y un intérprete propio los ejecutará sin `eval`, Python generado, shell ni cambios de código durante el ensayo. El operador nuevo será el programa mínimo que sobreviva a validación independiente; su nombre interno será un identificador derivado de su estructura. La búsqueda actual seguirá como respaldo. Si funciona y pasa regresiones, sustituirá la necesidad de agregar reglas manuales de conteo por dominio; no se retirará otro módulo sin equivalencia demostrada.

## Familias y partición

- Desarrollo F1: 64 experiencias con 12 valores agrupables en seis pares, con todas las 64 configuraciones de orden entre cada par. La estrategia útil depende de cuántas comparaciones cumplen una condición, con umbral enseñado por los ejemplos. Los centros y magnitudes cambian por experiencia. El meta-DSL anterior no recibe ese conteo como rasgo.
- Desarrollo F2: 128 experiencias de ocho valores individuales con signos y magnitudes variables. La estrategia útil depende de cuántos valores cumplen una comparación contra un umbral; el operador de reducción debe reutilizarse con otra forma de entrada y otro umbral final. Se enseña F2 después de F1 con el motor congelado.
- Reserva: 128 tareas nuevas por familia y orden de adquisición, con valores, escalas y configuraciones nuevas. Las semillas se derivan de los primeros ocho dígitos de `git rev-parse freeze-B-1:leobot`, más 0, 1 y 2; no se generan antes del tag. Órdenes de desarrollo: semillas 17, 53 y 97. Se renombrarán familias y estrategias en una repetición.

## Controles

Tratamiento con invención, ablación con los operadores actuales y la misma información, fresco, solo memoria, tarea incompatible que depende del máximo de magnitudes y no de la cantidad, contraevidencia que invalida el operador y dependientes, guardado/cierre/carga, reserva estructural, renombrado total y pista auxiliar correlacionada solo durante adquisición. Ante hipótesis indistinguibles, el motor debe conservar la duda y pedir un caso separador sin inventar su resultado.

## Métricas, umbrales y presupuesto

Se cuentan aciertos, abstenciones, errores seguros, candidatos del árbol, ejemplos, intervención humana, CPU y RAM de adquisición, búsqueda, validación, consolidación y respuesta. Se mide arranque frío, primera adquisición y reutilización. Para superar B-1: F1 y F2 ≥90 % de aciertos en las tres reservas; la ablación F1 ≤75 % o al menos cinco veces más candidatos; F2 educado necesita menos candidatos o menos ejemplos que F2 fresco con idéntico presupuesto; contraevidencia retira operador y dependientes; reinicio, renombrado y pista invertida no generan errores seguros. La latencia fija debe cumplir los presupuestos de `prereg/performance-1-latencia.md` antes del tag estable.

Presupuesto: máximo 32 programas candidatos y profundidad fija del motor anterior; 30 s de CPU por variante y orden, 256 MiB RAM, `timeout 180s` por experimento. El evaluador vive fuera de `leobot/`. Si falla o excede presupuesto, se conserva el resultado; modificar el criterio exige un preregistro nuevo.
