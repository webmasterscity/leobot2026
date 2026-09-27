# G-77 — separar lo común del sitio de lo que distingue la pregunta

2026-09-27, previo a código. Prototipo externo, motor estable intacto.

## En palabras fáciles de entender

Reconocer que una pregunta habla de un hotel no basta para distinguir si pide
su precio, su ubicación u otro dato. La prueba anterior podía aprender grupos
amplios, pero elegía pocas respuestas adicionales. Probaremos si aprende a
separar las palabras repetidas en un sitio de las que distinguen cada pregunta.
No indicaremos cuáles son esas palabras ni qué categorías debe descubrir.
Las dos partes se estiman contando ejemplos. La comparación decidirá si esta
separación ayuda o solo añade trabajo.

## Hipótesis y fuentes

G-76 eligió peso cero; su mejor elección sin abstenerse subía de 909 a 921/1 656
en TRAIN. Algunos grupos observados tratan hoteles, cupones o casinos. Esto
sugiere, pero no demuestra, que el tema del sitio consume la representación.
Hipótesis: explicar por separado ese tema permite adquirir distinciones comunes
a varios sitios con la misma cantidad de grupos, ejemplos y rondas.

[Zhai y colaboradores, KDD 2004](https://timan.cs.illinois.edu/czhai/pub/sigkdd04-ctm.pdf)
separan componentes comunes y propios de colecciones. Comparan noticias y
reseñas contra una mezcla simple; no estudian preguntas del kiosco ni aseguran
cero errores. [Hiemstra y colaboradores, SIGIR 2004](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/hiemstra_sigir04.pdf)
separan vocabulario de fondo y relevante; ganancia de recuperación pequeña
(precisión media 0,223→0,230), principalmente compresión. No basta para la meta.
Esta adaptación de G-76 no reproduce ninguno de los dos sistemas.

G-59/G-66 comparaban respuestas rivales para asociaciones entre palabras; aquí
el fondo compite durante la adquisición de grupos de preguntas completas. Si
funciona sustituye la educación G-76, no suma otro índice al motor. Usar el
mismo ejecutor para comparar, medir y guardar modelos.

## Mecanismo y decisiones fijadas

Mismos 4 000 pares, vocabularios, 32 grupos, 12 rondas y tres semillas G-76.
Conservar identificador de sitio solo durante educación. Contar frecuencia
global por término en preguntas y respuestas. Para respuestas de un sitio,
suavizar sus frecuencias con una observación distribuida según el fondo global.

Por palabra y grupo, probabilidad = `r * P(palabra|grupo) + (1-r) * fondo`.
El fondo de preguntas es global; el de respuestas es el de su sitio. Hay dos
valores r, uno por lado, inicializados en 0,5. En cada ronda, calcular la
responsabilidad del grupo y la probabilidad de que cada palabra venga del grupo;
solo esa fracción enseña sus cuentas. Reestimar r con esas fracciones y suavizado
uno en cada alternativa. Resto de actualización, suavizados y priors de G-76.

En respuesta, fondo de pregunta global aprendido; fondo de unidad contado en
todo el documento cargado (términos de unidades), suavizado con una observación
global. Calcularlo al cargar. Aplicar las mismas mezclas al estimar el grupo.
Puntaje de compatibilidad, pesos y confianza exactamente como G-76. No guardar
identificadores de sitio ni preguntas/respuestas en los modelos.

Variantes: completa; ablación con fondo de respuestas global también durante
educación y consulta; control con respuestas permutadas dentro del sitio.
Tres modelos por variante, señal promedio; no elegir semillas. Ablación y control
tienen mismo presupuesto y datos. G-76 sin fondo queda como antecedente negativo,
no se reenseña para este ensayo.

## Medidas, puertas y presupuesto

TRAIN/DEV, evaluación pública, selección, calibración y controles de G-76.
Mismas puertas: ≥5 puntos útiles frente a base, ≥2 frente a control confundido;
además ≥2 frente a la ablación global. Citas sin dato no mayores que base,
salida literal, reinicio/desactivación exactos, p95 y máximo <5 ms. Informar
también selección sin abstenerse, r aprendidos y semillas individuales sin
seleccionarlas. Conteo por claves en desarrollo gastado, no reserva ni juez.

Preparación/educación ≤600 s CPU; selección/evaluación ≤200 s por tres variantes
en vez de dos; memoria ≤1 GiB, tiempo transcurrido ≤1 100 s, un proceso pesado.
Guardar cada modelo antes de seguir y registrar interrupciones. Pruebas focales
con símbolos, actualización del documento y renombrado de sitios. Commit previo
y congelación `freeze-G77-prototipo` antes de medir. Si falla, conservarlo; no
ampliar grupos ni rondas. Si pasa, integración y prueba externa antes de promover.

Durante selección se reutiliza la preparación del documento para sus cuatro
pesos, como en G-75. Se extrae el recorrido común de turnos de G-68 para evitar
duplicar el evaluador. Prueba focal: mismas filas que recorridos separados.
No se reutilizan respuestas ni se adelanta análisis de preguntas al medir latencia.
