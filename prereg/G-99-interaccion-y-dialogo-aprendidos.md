# G-99 — elegir evidencia por palabras y contexto conversacional

2026-09-27. Nueva autorización: «continua mejorando el modelo para ver si
logramos el objetivo». Prototipo neuronal externo; `leobot/` y base intactos.

## En palabras fáciles de entender

El modelo anterior resume demasiado las frases: puede confundir un teléfono
con un precio porque ambos aparecen cerca de la palabra «reservas». La búsqueda
original conserva coincidencias útiles que el modelo pierde. Enseñaremos un
selector a combinar esas coincidencias con semejanzas aprendidas entre palabras.
Otra variante verá la pregunta anterior para interpretar las repreguntas.

Habrá comparaciones sin semejanzas, sin historial y con ejemplos confundidos.
Todo se aprende con material educativo separado. Las pruebas anteriores sirven
para comparar, no para enseñar. Registrar aciertos y errores importa más que
conseguir que responda más. La meta sigue siendo al menos seis respuestas útiles
de cada diez que tienen dato, sin errores nuevos y en menos de cinco milisegundos.

## Diagnóstico y fuentes

Análisis de salidas ya guardadas de G-98: entre 61 abstenciones contestables,
la candidata lexical del estable contiene las claves en 22; la neuronal en 8.
No es un nuevo examen. El selector actual reduce cada texto a un vector, ignora
historial y términos fuera del vocabulario; no debe reemplazar coincidencias
precisas por semejanza promedio sin comprobar el costo en selección.

[ColBERT, 2020](https://arxiv.org/abs/2004.12832) y
[K-NRM, 2017](https://arxiv.org/abs/1706.06613) estudian interacciones entre
palabras, con representaciones y pesos aprendidos. [SmallReason-ColBERT v1,
29-08-2026](https://arxiv.org/html/2609.29652v1) separa representación y pesos
de importancia, con controles; usa un modelo previo de 32 M y entrenamiento
de base en ocho H100 durante unas 24 horas. Sus mejoras no prueban esta
adaptación pequeña ni cinco milisegundos CPU. [LightOn, 16-06-2026](https://huggingface.co/blog/lightonai/lateon-regularization)
documenta pérdida al comprimir interacciones: no se añade un índice aproximado.
Se implementa una adaptación local, no una reproducción de esos trabajos.

## Hipótesis y diseño congelable

H1: combinar coincidencia exacta, correspondencias ya aprendidas y comparación
de palabras supera la selección de G-98. H2: la pregunta anterior aporta en
repreguntas. No hay listas de horarios, tipos de negocio ni preguntas especiales.

Reusar G-98 `prepare`, con las mismas fuentes, 6000 SQAC humanos y 1737 ejercicios
sintéticos TRAIN, y las mismas particiones por documento. Reconstrucción debe
reproducir huellas G-98 antes de añadir variables. Calibración solo en su mitad
reservada; la comprobación educativa no selecciona modelos ni hiperparámetros.
Añadir a cada turno educativo la pregunta previa de su conversación, si existe;
SQAC sin historial. En inferencia, último mensaje de cliente del historial
alternado pregunta/respuesta. No leer futuras preguntas ni las respuestas gold.

Vectores de palabras G-98 `localized` congelados, 64 números, proyecciones q/a.
Por candidata: coincidencia exacta (también palabras fuera del vocabulario),
cobertura ponderada por `Bot._delta`, correspondencias de `Bot._bridge`, sus
ausencias y medias/máximos; largo de pregunta/unidad; coincidencia de pares
contiguos; comparación máxima por palabra con medias, mínimo, desviación y
cuantiles; coseno de representaciones promedio. Sin diccionario nuevo.
Comparación neuronal acotada a primeros 32 términos de pregunta y 64 de unidad;
coincidencia literal sobre todos los términos. No se trunca el texto citado.
Agregar promedio q/a y su producto como variables continuas (64 números cada
uno) para aprender distinciones. Variables del turno anterior separadas, sin
concatenar ciegamente las preguntas. Preparar unidades al cargar contexto.

Aprender una red pequeña: estandarización de variables con enseñanza, capa
oculta 48 tanh, salida escalar. Pérdida por documento de elección entre unidades
positivas y opción vacía de puntaje cero, más 0,25 de entropía binaria por unidad;
positivas múltiples permitidas y relleno enmascarado. AdamW 0,001, decaimiento
0,001, 24 épocas, lotes de 64 preguntas, semilla 1, una hebra CPU. Pesos de
palabras congelados; se enseña únicamente la decisión. Nada se guarda como tabla
de preguntas/respuestas. Cuatro variantes con presupuesto igual:
- `lexical`: solo variables de coincidencia/longitud/correspondencias, sin historial.
- `interaction`: variables anteriores más interacciones neuronales, sin historial.
- `history`: todas las variables, principal.
- `shuffled`: como history, pero permuta preguntas y su historial dentro del
  mismo grupo, manteniendo documentos/etiquetas y contabilizando cambios.

Confianza: calibración isotónica de puntajes fuera de enseñanza, por separado
para cada modelo. Dos puntos de operación registrados antes de medir: mínimo
0,4 (comparación con G-98) y mínimo 0,9 (principal para prudencia), ambos requieren
que la unidad supere la opción vacía. No cambiar ni seleccionar el mínimo por DEV.
No prometer que 0,9 sea una garantía de corrección. No emitir texto generado.

## Medidas y puertas

Reutilizar evaluador G-97 sin cambiar juicio/historial. Comparar estable, G-98,
cuatro variantes (cada mínimo) en los mismos 157 turnos gastados; panadería
solo diagnóstico. Reportar elección cruda y cambios previos preservados. Meta
principal ≥62/102 útiles, cero errores nuevos y p95/máximo <5 ms, incluyendo
activación. Paso intermedio ≥5 útiles más que G-98 sin errores nuevos; historia
y comparación neuronal deben aportar frente a sus ablaciones. No presentar
este material gastado como validación de generalidad ni promover automáticamente.
Si pasa, exigir reserva nueva independiente antes de afirmar éxito general.

Control de reinicio en proceso nuevo/hashseed 1, exportación PyTorch/NumPy,
desactivación, cambio/vaciado de documento, enmascarado del relleno y aprendizaje
real de un contraste. Trece rápidas antes/después. Ninguna red nueva en `leobot/`.

## Plan y presupuesto

Preregistrar/commit; escribir contrastes; implementar preparación/red/ejecución;
congelar enseñanza; entrenar/exportar; congelar modelos; medir, repetir y registrar.
Preparación+enseñanza+confianza ≤1200 s CPU/1800 s pared; evaluación/reinicio
≤240 CPU/400 pared; RSS ≤3 GiB por proceso y un trabajo pesado por vez. Costos
G-97/G-98 reutilizados, descargas nuevas cero. Artefactos `.leobot-data/g99/`,
resultados `results_v3/g99_*`. Preservar todas las variantes y fallos; no ajustar
con los errores del examen. Código y datos anteriores permanecen congelados.
