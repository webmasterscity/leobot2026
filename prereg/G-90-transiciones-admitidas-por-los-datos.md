# G-90 — transiciones admitidas por los datos

2026-09-27. Previo a código. G-89 conserva su fallo 0,649482 <0,65.

## En palabras fáciles de entender

Al aprender con textos marcados, Leobot también observa qué clases pueden ir
una detrás de otra. Comprobaremos si usar esa información evita algunos cortes
incorrectos de nombres. Las combinaciones permitidas saldrán de los ejemplos,
sin escribir reglas sobre personas, lugares o el significado de las etiquetas.
Si esa limitación impide encontrar una secuencia, se conserva la predicción
anterior y se cuenta el caso. No se modifica ningún dato para mejorar la nota.

## Causa propuesta, fuente y diferencia

G-89 predice 197 continuaciones BIO incompatibles con su formato, pero esto
no prueba que explique toda la pérdida. Su interpolación permite transiciones
no observadas. Hipótesis: limitar a pares de etiquetas vistos mejora al menos
un punto de F1. Alternativa: elimina combinaciones válidas o solo embellece
el formato sin mejorar la identificación semántica.

[Lester y otros, 2020](https://aclanthology.org/2020.findings-emnlp.166.pdf)
estudian restricciones al decodificar. Usan redes y reglas IOBES diseñadas,
excluidas aquí; además reportan menor ganancia con BIO. No trasladar su
rapidez de entrenamiento ni F1 a Leobot. El trabajo de [supervisión débil de 2026](https://www.mdpi.com/2076-3417/16/8/3632)
genera etiquetas mediante LLM y las valida con formato fijado: tampoco es
fuente de enseñanza compatible. La propuesta acotada aquí es un soporte de
transiciones obtenido únicamente de los conteos humanos G-89.

No añadir aprendiz: extraer del modelo G-89 todas las parejas de su tabla
`bigrams` con conteo positivo, incluidos inicio/final de secuencia. Conservar
incluso la transición anómala presente una vez; no usar apoyo mínimo ni
interpretar prefijos BIO dentro del decodificador. Todo lo demás, emisiones,
interpolación, terminaciones y ancho de búsqueda, sigue igual. Durante
decodificación, una transición no observada tiene logprobabilidad −infinito.
Si no se obtiene una secuencia completa admitida, volver al método G-89 y
registrar ese respaldo. La pertenencia es entre símbolos opacos.

## Comparación y puertas

Fuente/partición G-89 intactas. Reutilizar su modelo guardado y verificar SHA
contra el manifiesto local antes de congelar; no reenseñar palabras. `testa`
está gastado y se evalúa una vez. `testb` cerrado. Comparar sin límite, soporte
aprendido y soporte con identidades de etiquetas permutadas (semilla 1;
inicio/final no cambian). Esta confusión conserva la estructura del grafo,
pero cambia qué etiqueta ocupa cada posición. El modelo estadístico permanece
intacto en los tres. Conservar también referencia por palabra G-89.

Puerta: F1 ≥0,65 **y** mejora ≥0,01 sobre G-89 y sobre soporte confundido;
≥0,05 sobre palabra aislada; recuperación ≥0,40 en nombres completos nuevos,
con ≥100 casos. No redondear, bajar corte o elegir otro soporte tras medir.
Eliminar restricciones debe restaurar etiquetas G-89 exactas; reinicio/hashseed 1
exacto. Focales: restricción sale de conteos, nombres de clases intercambiables,
respaldo cuando no existe camino y desactivación exacta.

Solo si pasa: otro preregistro para comprobación humana aparte (`testb`) y
posible educación pregunta/clase. Ni G-89 ni este desarrollo prueban utilidad
en el kiosco. Si falla, no integrar ni enseñar preguntas con esta variante.

## Presupuesto

Reutilización/aprendizaje ≤10 s CPU, evaluación/recarga ≤50 s, total ≤60 s,
pared ≤90 s, RAM conjunta ≤512 MiB. Registrar CPU por etapa, respaldo, tamaños,
latencia por secuencia; no es latencia de `Bot.answer`. Costo previo G-89 y
descarga ya registrados, no gratuito. Motor/base estables sin modificar;
trece rápidas y focales, commit previo y `freeze-G90-prototipo`. Resultados
`results_v3/g90_observed_transitions.json`; sin auditor ni reserva PAR-6.
