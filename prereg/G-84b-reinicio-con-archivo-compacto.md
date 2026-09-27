# G-84b · Comprobar el mismo modelo con un archivo sin espacios de presentación

27 de septiembre de 2026. Antes de cambiar el archivo o repetir respuestas.

## En palabras fáciles de entender

La prueba G-84 produjo una mejora parcial, pero su archivo de aprendizaje quedó
demasiado grande para volver a abrirlo. Parte del tamaño corresponde a espacios
y saltos de línea puestos para facilitar la lectura del archivo. Guardaremos
exactamente los mismos datos con menos espacios y comprobaremos que se abre y
produce exactamente las mismas respuestas. Esto no enseña nada nuevo, no cambia
las decisiones y no convierte el resultado parcial en una prueba superada.

## Motivo y alcance fijado

G-84: 334/816 útiles, 69/488 citas sin dato, 482 elecciones correctas. No pasó
≥491 ni ventaja ≥17 sobre directo (327/73) y confundido (341/80).
El archivo generado por Bot.save ocupa 110 314 166 bytes, por encima del límite
vigente de 100 MiB; Bot.load lo rechaza. Se conserva intacto ese archivo y el
informe original, incluida la recarga fallida. No subir el límite del cargador.

Leer ese JSON con la biblioteca estándar y escribir otro archivo con los mismos
valores y orden de listas, sin espacios/saltos de presentación. Sin quitar datos,
redondear de nuevo, alterar índices ni filtrar pesos. Prohibido reenseñar o elegir
una variante. Candidato: `.leobot-data/g84_candidate_compact.json`; la base del
usuario sigue intacta. Registrar SHA y tamaños de ambos archivos.

Recargar el compacto en proceso nuevo/hashseed 1 con el **mismo prototipo G-84**
y medir todo DEV con Bot.answer. Exigir SHA de respuestas idéntico al publicado,
estructura de primer nivel conservada, ausencia de citas no literales y tamaño
≤100 MiB. Reportar tiempos/preparación y límites; no mezclar esta comprobación
de transporte con las puertas de calidad G-84, que permanecen fallidas.

Procesos pesados secuenciales, memoria conjunta ≤1 GiB, ≤60 s CPU total,
≤90 s transcurridos. Registrar por separado compactación y recarga/evaluación.
Congelar `freeze-G84b-transporte` antes de ejecutar. No promoción ni reserva nueva.
