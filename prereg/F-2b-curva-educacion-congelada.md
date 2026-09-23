# F-2b — Curva de educación de secuencias con motor idéntico

F-2 terminó 7/32 en reserva SCAN con 256 pares, frente a 0/32 fresco y solo memoria: hubo reglas adquiridas, pero falló el umbral previo de 8/32. No se cambia ese resultado ni se modifica el motor para este ensayo. Hipótesis: la representación actual necesita más experiencias estructuralmente variadas para consolidar conectores y modificadores; alternativa: el espacio de programas es insuficiente y duplicar datos solo aumenta costo.

## Currículos y reserva

Motor y configuración `freeze-F-2b:leobot` deben tener **exactamente el mismo árbol** que `freeze-F-2:leobot`; sin cambios de primitivas, learners o límites. Datos SCAN `addprim_jump` con hashes de F-1/F-2. Dos bots: A recibe los mismos 256 pares de F-2; B recibe 512 pares: todos los 68 comandos de ≤3 tokens y 74 seleccionados en cada longitud 4–9 con `Random(1642)` por estrato; orden canónico por longitud/texto. Un bot fresco y otro con los 512 pares pero composición apagada son controles. Ningún bot ve salidas de prueba.

Después de etiquetar el árbol, elegir 32 comandos nuevos de la división oficial de prueba con semilla `sha256((H0 + ':F-2b').encode())`, excluyendo por identificador los 16 usados en F-1 y 32 usados en F-2. Comparar ambos currículos sobre los **mismos** 32 comandos. Repetir B con renombrado biyectivo total de símbolos. Guardar/cargar antes de consultar. Una observación contradictoria sobre una regla usada debe retirarla y retirar las dependencias afectadas. No elegir ejemplos a partir de respuestas reservadas.

## Métricas, decisión y presupuesto

Exactitud de prueba, cantidad de reglas, candidatos, ejemplos, CPU de observación, consolidación, carga y consulta, RAM pico y p50/p95. Separar costo inicial de costo por caso resuelto. La señal de **más educación con motor congelado** requiere B ≥12/32 y ≥4 aciertos adicionales sobre A. Promover como mejora de adquisición eficiente solo si B ≥15/32, el costo CPU por acierto no sube frente a A, controles fresco/memoria 0 o claramente menores, renombrado preserva aciertos, corrección y reinicio pasan y p95 ≤10 ms. Si no, registrar «más ejemplos sin suficiente ganancia» y retirar la ruta candidata; no subir límites ni ajustar umbrales mirando reserva. Presupuesto: 512 ejemplos por bot B/control, 32 pruebas, ≤20 000 candidatos, ≤30 s CPU por brazo y ≤120 s pared. Motor congelado antes/después; si varía por orden, evaluar tres órdenes.

F-2b tampoco sustituye la fase F larga: no hay 50 familias, 10 dominios ni transferencia entre estructuras distintas. Ninguna salida de SCAN se codifica en motor o fixture de respuesta.
