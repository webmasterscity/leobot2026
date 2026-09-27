# G-73b — comprobar correspondencias nominales de Predicate Matrix

2026-09-27, antes de descargar/contar. Motor intacto
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## En palabras fáciles de entender

La descarga de los textos originales de AnCora está rechazada por su servidor.
Otro equipo publicó una colección que conecta parte de esas anotaciones con
las de otros diccionarios de significado. Comprobaremos qué contiene y cuántas
relaciones del español conserva. Son correspondencias entre significados;
no equivalen a frases con preguntas y respuestas. Si sirven, aún habrá que
demostrar que Leobot aprende de ellas sin convertirlas en reglas especiales.

## Fuente, diferencia y pregunta

[A Multilingual Predicate Matrix, LREC 2016](https://aclanthology.org/L16-1423/)
describe la integración de AnCora-Verb y AnCora-Nom en una colección multilingüe.
Combina correspondencias previas con ampliaciones automáticas; no se tratará
como verdad humana infalible. Las cifras de sus evaluaciones no son de Leobot.

Dirección enlazada desde la [página de sus autores](https://adimen.ehu.eus/web/PredicateMatrix):
`https://adimen.ehu.eus/web/files/PredicateMatrix/PredicateMatrix.v1.3.tar.gz`.
La página declara CC BY 3.0; registrar también la licencia incluida y la huella
del paquete. Usar TLS normal, sin excepciones ni contenido ejecutable.

Pregunta de esta inspección: ¿contiene correspondencias nominal-verbo con
papeles alineados suficientes para investigar una representación común de
relaciones, conservando qué participante corresponde a cuál? G-34 era un
diccionario de correspondencias léxicas; aquí interesa la relación completa
con sus casillas y ambigüedades. No hay aprendiz ni mejora operacional aún.

## Procedimiento y criterios fijados

1. Descargar ≤64 MiB, ≤120 s, dos intentos máximo; registrar URL final, SHA256,
   bytes y CPU/tiempo. Leer el archivo comprimido sin extraer rutas al sistema.
2. Leer la documentación y el encabezado/formato, sin hacer conteos completos.
   Fijar la correspondencia de columnas antes de escribir el contador completo.
3. Puerta de contenido parcial: ≥200 predicados nominales españoles con enlace
   a predicados verbales; ≥3 códigos de papel alineados en ≥50 predicados
   nominales cada uno. Contar todos los enlaces, los ambiguos y los incompletos;
   no seleccionar a mano vocabulario ni quitar conflictos para pasar.
4. Contar filas válidas, lenguas, verbos/nombres, sentidos, conjuntos de papeles
   y duplicados. No inferir que un campo desconocido es una relación completa.
5. Esta puerta sustituye **solo** la disponibilidad de correspondencias. La
   puerta del corpus G-73 queda sin evaluar. No hay frases/preguntas alineadas
   salvo que estén realmente presentes, y no se presume calidad de respuestas.

Este material público es educación/desarrollo, nunca reserva nueva. Ningún
archivo se carga en el motor. Una futura hipótesis de aprendizaje requerirá
separar familias de relaciones y documentos, comparar contra diccionario léxico
simple, señal barajada y lector actual, y medir `Bot.answer` en negocios nuevos.

## Presupuesto y congelación

≤512 MiB expandidos en total, ≤20 000 miembros, ≤512 MiB RAM, ≤120 s CPU,
≤5 minutos transcurridos para leer/contar. Si excede, detener y declarar la
inspección incompleta. Contar en flujo; no ejecutar scripts del paquete.
Guardar adquisición y huellas antes/después. Commit de este registro antes de
implementar; congelar lector y mapeo del esquema antes del conteo completo.

Resultados posibles: contenido suficiente/insuficiente, formato no verificado
o acceso pendiente. No implica mejora del 60 %, prueba de comprensión ni
solución de la panadería. Regresión completa y auditoría no corresponden a una
inspección de datos sin cambio de motor.
