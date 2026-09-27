# G-75 — evidencia relacional aprendida con participantes

2026-09-27. Previo a código. Motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
Prototipo externo. No modifica la base del usuario ni `leobot/`.

## En palabras fáciles de entender

No basta saber que dos palabras pueden hablar de lo mismo: también importa
quién participa y cómo se relaciona con la acción. Enseñaremos al prototipo
con preguntas y respuestas reales de páginas web. Aprenderá qué coincidencias
entre relaciones y participantes caracterizan una respuesta elegida por personas,
comparándola con otras respuestas del mismo sitio. Esas otras respuestas son
contrastes de aprendizaje, no pruebas de que sus hechos sean falsos.

La información de los negocios de prueba no se usará para enseñar significados.
Sus bancos antiguos solo calibran y comprueban cuándo la nueva señal resulta
útil. Las respuestas seguirán siendo citas del texto cargado. G-74 demuestra
que esta vía sola no alcanza el 60 % en el banco actual; se busca un complemento
real que mejore al menos cinco puntos sin aumentar citas cuando falta el dato.

## Hipótesis y diferencia

Predicate Matrix proporciona candidatos de significado, muchos ambiguos. En
G-34 se añadían equivalencias léxicas con peso fijo; G-48 relacionaba caminos
entre palabras ya coincidentes; G-71/G-72 no aprendían de preguntas humanas.
G-75 aprende de MFAQ si una relación compartida y la colocación de sus
participantes respaldan emparejar pregunta y respuesta. Las rutas sintácticas
vienen del analizador aprendido existente; no se escriben correspondencias
entre funciones a mano. Una ablación conserva solo el significado léxico.

Fuentes, antecedentes y límites: investigación G-71 y G-73b. La adaptación
concreta es una hipótesis del proyecto, no un resultado atribuido al artículo.
Si funciona sustituiría el uso indiscriminado de equivalencias, sin añadir
un servicio externo. No transforma los enlaces de la fuente en hechos seguros.

## Educación fijada

Reutilizar muestreo G-65 de MFAQ: semilla 57, ≤100 pares por dominio, excluir
dominios de calibración G-57, mismo SHA y deduplicación normalizada. Extender
el lector opcionalmente para conservar el texto original sin cambiar su salida
normal. Solo para este aprendiz: pregunta ≤24 palabras sintácticas, respuesta
≤48; dominio con al menos dos respuestas distintas. Orden determinista por
SHA de dominio/pregunta/respuesta, seleccionar como máximo 2 000 pares.

Cada pregunta se compara con su respuesta humana y con la respuesta distinta
siguiente de su dominio, en orden circular. La segunda es contraste, no oro
negativo semántico. Guardar solo conteos/coeficientes y la fuente de candidatos;
no conservar preguntas, respuestas ni soluciones de negocios en el modelo.

Representación por pareja:

- relaciones de PropBank compartidas por algún término, a partir de G-74;
- por cada par de términos con relación compartida, palabras iguales que pueden
  ser participantes, identificadas por la lematización existente;
- pares de rutas de hasta tres arcos desde cada término de relación hasta ese
  participante, usando `g23_role_paths.route` sobre el análisis aprendido;
- conjuntos completos de esos pares de rutas, borrando nombres de participantes.

Las rutas son símbolos aprendidos, no listas de papeles o de preposiciones.
Máximo 64 parejas de cabezas y 128 bindings —vínculos entre participantes—
por comparación. Ante exceso, descartar esa señal y registrar el límite.
Máximo 200 000 rasgos; no aumentar límites tras observar resultados.

Por rasgo, contar presencia en respuesta propia y contraste, y apoyo en dominios
distintos. Conservar solo rasgos presentes en ≥5 dominios. Peso = logaritmo de
la razón de frecuencias suavizadas con uno. Puntaje = suma de pesos de los
rasgos presentes dividida por raíz del número de rasgos con peso. No hay
palabras de negocio ni significados definidos por el desarrollador.

Controles: lexical (solo relaciones, sin rutas) y señal confundida (intercambiar
con semilla fija los rótulos propio/contraste de cada pareja, antes de contar).
El primer control separa el aporte de participantes; el segundo el de la
asociación educativa real. Ambos reciben la misma información y presupuesto.

## Uso y selección

Preparar los árboles de unidades al cargar el contexto. Analizar cada pregunta
en la respuesta, contabilizando ese costo. Solo activar una propuesta nueva
si la unidad tiene enlace no literal G-74; sin él se conserva exacta la base.
Alternativas: unidad de referencia o unidades con esa señal. Puntuar con
score original + peso × puntaje aprendido. Pesos candidatos: 0,25; 0,5; 1; 2,
además de la opción sin mecanismo. No seleccionar en G-62/G-63/G-64.

Reconstruir para la unidad elegida los rasgos originales; añadir puntajes
léxico/estructural y cantidad de interpretaciones. Sus intervalos se aprenden
de cuartiles en los bancos de entrenamiento, nunca del banco comprobado.
Recontar confianza Bayes/isotónica solo para filas donde actúa la señal;
sin señal, devolver la confianza original. Umbral de cita 0,4 intacto.

Usar TRAIN de G-68 (G-57–G-61 y desarrollo), particiones cruzadas por negocio.
Elegir peso por mayor número de respuestas útiles cruzadas, restringiendo citas
sin dato a no superar referencia; desempatar por menos citas sin dato y menor
peso. Incluir siempre referencia sin mecanismo. Después fijar la selección y
evaluar mediante `Bot.answer` real en DEV G-62/G-63/G-64, gastado.

Puerta parcial: ≥5 puntos útiles sobre referencia y sobre señal confundida,
≥2 puntos sobre lexical, sin más citas sin dato; salida literal, reinicio y
control sin señal exactos, p95 <5 ms incluyendo pregunta sin análisis previo.
Reportar p50 y máximo, preparación de documentos, usos/excesos, errores y
costos. No llamar «cero engaños» a contar menos citas sin dato. Si pasa,
integración y reserva nueva con juez independiente antes de promover.

## Presupuesto

Un proceso pesado. Enseñanza/análisis ≤600 s CPU; calibración/evaluación ≤300 s;
RAM ≤1 GiB; ≤1 200 s transcurridos. Registrar etapas, descargas cero, ejemplos
excluidos y huellas. Pruebas focales de vinculación, límites y aislamiento;
regresión completa solo para tag estable. Commit del preregistro antes de
implementar, tag `freeze-G75-prototipo` antes del ensayo. No sustituir objetivo
por éxito en la panadería ni detener el proyecto si este complemento falla.

## Corrección de ejecución antes de medir resultados

La primera corrida se interrumpió tras unos 391 s CPU, 80,376 de enseñanza y
unos 311 de selección: excedió el presupuesto de selección. No llegó a elegir
un modelo ni a evaluar su calidad. Se conserva en `g75_interruption.json`.
Un perfil sobre 83 turnos gastados muestra 181 análisis sintácticos y 3,201 s
en el analizador, de 3,879 s totales. La carga de tres documentos tomó 2,855 s.

Sin cambiar ejemplos, rasgos, coeficientes ni puertas, se recorrerá TRAIN una
sola vez por negocio y se compararán allí las doce combinaciones de variante
y peso. Los árboles y rasgos de una pregunta/documento se pueden reutilizar
durante ese ajuste; los puntajes y respuestas se recalculan para cada modelo.
Una prueba compara las filas obtenidas con el recorrido original independiente.
Los datos reutilizados se descartan al cambiar el documento.

Se guardará la enseñanza al terminarla y se mostrarán tiempos parciales. En la
medición pública se borrarán los análisis de preguntas en cada llamada: p50,
p95 y máximo incluirán análisis nuevo, también si se repite una pregunta. La
preparación de unidades al cargar sigue separada y contabilizada. Se conservan
los límites originales por nueva corrida, registrando además el costo total
de ambos intentos. Congelación nueva: `freeze-G75-prototipo-b`.
