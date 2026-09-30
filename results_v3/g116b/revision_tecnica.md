# Revisión técnica complementaria G-116b

Fecha: 2026-09-29. Encargo concreto de revisión de código; no auditoría científica ni promoción de fase. Se revisaron biblioteca, conocimiento general, recuperación y herramientas de comparación.

La primera revisión pasó 27 pruebas focales y encontró un fallo: la primera pregunta tras enseñar una nueva negación podía consultar una lista sin actualizar y recibir una afirmación positiva. Las bibliotecas y la compatibilidad de contexto no presentaron defectos importantes.

La reproducción original y la nueva prueba de aprendizaje incremental fallaron antes de la corrección. En `fa9d49d` / `freeze-G116b-2`, ambas rutas separan las palabras y actualizan la sintaxis antes de consultar los negadores. El revisor confirmó que la primera respuesta deja de ser `general_yes`; la intersección negativa devuelve `None`, la positiva sigue encontrando la relación y la nueva prueba pasa. Comandos acotados a 40 s; el revisor no modificó archivos ni repitió la regresión completa.

Dictamen técnico favorable para integrar las correcciones. Ninguna candidata aprendida se activa ni se promueve.

## En palabras fáciles de entender

El programa había aprendido una nueva palabra que niega, pero la primera vez aún consultaba su lista anterior. Ahora actualiza lo aprendido antes de responder. Otro revisor repitió el caso y confirmó que ya no dice que sí por ese error. Esta comprobación permite conservar el arreglo; no demuestra que el programa conteste mejor cualquier pregunta.
