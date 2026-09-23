# Preregistro C-1 — dos learners de vistas como datos

Fecha: 2026-09-22. Referencia: `estable-B-2`, árbol del motor `7564d4fe2d89bdf1504211fcb242619fdbe39698`. C-1 es el paso de equivalencia de la fase C, no su experimento decisivo.

## Fallo, alternativa y cambio propuesto

`MetaController._best_projection_view` y `_invent_aggregate_view_from_tasks` son dos learners escritos como recorridos distintos. Ambos generan particiones de experiencias, evalúan cada partición dejando una experiencia fuera, comparan con la clase mayoritaria, comprueban apoyo y promueven una vista. Agregar un tercero exige volver a programar buena parte del ciclo. Alternativa sencilla: dejar los dos recorridos y agregar otro `if`; eso no reduce la intervención del desarrollador.

Un único intérprete tipado leerá datos declarativos con: representación de entrada, generador de hipótesis, operadores admitidos, restricciones, estrategia de búsqueda, verificador, costo, promoción, rollback y presupuesto. Los dos programas de datos iniciales reproducirán los learners de proyección y plegado agregado actuales. Solo habrá operaciones en una lista cerrada; sin `eval`, Python generado, shell ni acceso a evaluadores o repositorio. Se eliminarán los recorridos duplicados de validación y construcción de cubos. Si la equivalencia falla, no se retirará el código antiguo ni se promoverá el intérprete.

## Familias, partición y controles

- Desarrollo: experiencia de proyección con grupos repetidos, F1 de seis pares y F2 de ocho valores de B-2, en órdenes 17, 53 y 97. Antes de implementar se guardarán resultados de referencia: vista, parámetros, predicciones y candidatos, usando únicamente el motor `estable-B-2`. Esa referencia visible comprueba equivalencia, no cuenta como reserva.
- Reserva nueva: después de `freeze-C-1`, 128 tareas por familia, con nombres, magnitudes y orden nuevos, generadas con la huella `freeze-C-1:leobot` más 0, 1 y 2. La reserva solo puede puntuar generalización y costo; no ajusta la especificación después de verse.
- Controles: mismo motor con el intérprete frente a los resultados B-2 y la referencia previa; ablación de cada learner; bot fresco; solo memoria; misma información; estructura incompatible; contraevidencia; guardar/cerrar/cargar; renombrado; pista espuria invertida; motor congelado. Donde la capacidad dependa de ambos learners, registrar también su combinación, sin atribuirla a C-1.

## Umbrales y presupuesto

En desarrollo, deben coincidir exactamente los tipos de vista, programas elegidos, umbrales, cubos, predicciones y conteos de candidatos en las tres órdenes, salvo métricas de tiempo. Las pruebas propias existentes de ambos learners y las pruebas rápidas deben pasar. En reserva, cada tratamiento debe conservar ≥90 % de aciertos de sus familias conocidas; contraevidencia y reinicio no pierden rollback. El costo de adquisición no puede superar 1,5 veces la referencia B-2 en el mismo protocolo, ni la latencia fija empeorar >20 % en p95 antes de un tag estable. El programa de datos tiene límites explícitos de tareas, candidatos y CPU; cada ensayo lleva `timeout 180s` y RAM ≤256 MiB. Registrar adquisición, búsqueda, validación, consolidación, inferencia, arranque frío, ejemplos, candidatos y RAM sin sumar costos anidados.

Este paso **no supera la fase C**. Después habrá un preregistro C-2: el MetaController deberá construir y seleccionar un learner nuevo a partir de los componentes, resolver una familia que los learners existentes no resuelvan dentro del presupuesto y transferir sin editar el motor. Si C-1 solo cambia el formato de configuración o añade superficie sin retirar duplicación, se descarta.
