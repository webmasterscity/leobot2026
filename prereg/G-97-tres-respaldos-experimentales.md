# G-97 — tres respaldos experimentales

2026-09-27. Preregistro anterior a código y medición.

## En palabras fáciles de entender

El usuario autoriza probar tres alternativas donde Leobot se queda sin
respuesta: instrucciones escritas por nosotros, un modelo de lenguaje público
y un modelo pequeño que entrenaremos desde cero. Compararemos los tres con
el Leobot estable sobre las mismas preguntas. Las alternativas podrán elegir
un fragmento del documento o callar; sus datos saldrán del texto cargado.

Una cita puede ser literal y, aun así, no contestar. Contaremos esos fallos,
las preguntas atendidas, las abstenciones y el tiempo completo de respuesta.
También habrá preguntas nuevas redactadas por otra sesión, después de congelar
los programas. Si una alternativa falla, se conservará el resultado.

El respaldo se activa solo cuando el sistema estable se abstiene. Por tanto,
los errores que ya contesta el estable no se arreglan con este diseño: se
medirá ese límite. Llegar al 100 % en una prueba no garantizaría perfección
para cualquier negocio. El motor que usa el usuario no cambia en este ensayo.

## Autorización y alcance

Excepción explícita del usuario: «solo para probar» reglas como respaldo;
después pidió considerar modelos de lenguaje/entrenamiento y finalmente
«las 3 pruebas, reglas, conseguir un llm ideal, entrenarlo nosotros».
Se permite en este experimento usar reglas semánticas manuales y redes
neuronales externas a `leobot/`. No representa autoaprendizaje puro ni revoca
globalmente MISION.md. No se requiere otra confirmación para esta prueba.
No hay servicios de inferencia remotos, GPU, entrenamiento pagado, cambios en
la base estable ni acceso a PAR-6/duxiV2. Los textos de evaluación no educan.

Base estable G-64 con SHA registrado; mismo segmentador y respuestas previas.
Respaldo solo para estados `unknown`, `ambiguous`, `literal_unknown` y
`unrecognized`. Si hay una candidata, devolver `closest` con cita literal y
procedencia; no dar afirmaciones numéricas calculadas ni reescribir el dato.
Conservar condición, negación y horarios completos de la unidad elegida.
Si no puede elegir, devolver exactamente la abstención anterior. Sin caché
de preguntas/respuestas; preparación de unidades permitida al cargar contexto.

## Las tres alternativas y sus controles

**A, reglas declaradas.** Tabla manual de expresiones para horarios,
ubicación, contacto, pagos, precios, entregas, reservas, cancelaciones,
cambios/devoluciones, garantía, estacionamiento, accesibilidad, mascotas y
edad. Añadir coincidencia léxica de sustantivos para productos/servicios.
La candidata debe compartir la categoría preguntada y cubrir los términos
específicos de la pregunta que no sean palabras funcionales o las señales
de categoría. Ante empate sin evidencia adicional, abstenerse. No guardar
datos del negocio ni preguntas completas; tabla y condiciones se congelan
antes de medir. Contrastes locales verifican horarios de entrega distintos
de apertura, servicios ausentes y cambio de documento. No es aprendizaje.

**B, LLM público.** Selección bibliográfica previa: [LFM2.5-350M](https://huggingface.co/LiquidAI/LFM2.5-350M),
350 millones de parámetros, arquitectura híbrida con convoluciones y atención,
español entre los idiomas declarados; [publicación de sus autores de 2026](https://www.liquid.ai/blog/lfm2-5-350m-no-size-left-behind).
No se le atribuye ser «ideal» antes de probarlo. Cuantización oficial
`LFM2.5-350M-Q4_K_M.gguf`, revisión
`657e078c94084481950a2d555a941481f715536b`, licencia LFM Open License 1.0
conservada junto al archivo; solo investigación local, sin redistribución.
Ejecutor llama.cpp revisión `4da6337767f973e2b4d0797e5b323d77d8565e4a`.
Proceso persistente local, una hebra CPU, sin GPU, contexto 4096 tokens,
máximo ocho tokens de salida, elección codiciosa, estado borrado entre consultas.
Entrada: instrucciones, historial y lista numerada de unidades. Una petición
fija solicita el número de la unidad que responde o 0 si falta el dato. Una
salida inválida, un número fuera de rango o un contexto excesivo causa abstención.
El programa copia la unidad elegida; ninguna respuesta del LLM educa C.

[xLLM](https://docs.xllm-ai.com/en/hardware/overview/) es un ejecutor centrado
en aceleradores, no una arquitectura nueva que garantice cinco milisegundos
en esta CPU; la biblioteca [X—LLM](https://github.com/KompleteAI/xllm) facilita
ajuste de modelos existentes. [BitNet](https://arxiv.org/abs/2504.12285)
reduce costo, pero velocidad por token no certifica tiempo total. No instalar
estas alternativas en este ciclo. [Model2Vec](https://huggingface.co/minishlab/potion-multilingual-128M)
es una alternativa rápida de representación, no un LLM generativo; queda fuera
de B para no cambiar silenciosamente la comparación pedida.

**C, modelo propio.** Red pequeña de recuperación, no LLM generativo.
Reusar MFAQ español humano y muestreo G-65 con su SHA. Solo pares con
1–40 términos de pregunta y 1–160 de respuesta. Ordenar por SHA del par;
dominios con SHA módulo 5 = 0 reservados para comprobación educativa. Tomar
los primeros 6000 pares del resto y 1000 de la comprobación, sin cambiar topes.
Vocabulario compartido de términos y pares consecutivos, frecuencia ≥2 en
enseñanza, máximo 20000 ordenados por frecuencia y desempate léxico.
Tabla de 64 números por elemento, promedio, transformación 64×64 y tangente
hiperbólica distinta para pregunta/respuesta, normalización de longitud.
Inicialización aleatoria semilla 1. Seis épocas, lotes 64, AdamW 0,003 y
decaimiento 0,0001; pérdida contrastiva simétrica con temperatura 0,1.
Preguntas o respuestas idénticas en el lote cuentan como positivos múltiples;
otros falsos negativos posibles se declaran. Una hebra PyTorch CPU durante
enseñanza; exportación numérica sin pickle y ejecución NumPy con una hebra.

Tres variantes C: inicial sin entrenar, entrenada, entrenada con parejas de
respuesta permutadas dentro del dominio (semilla 1). Mismos ejemplos, épocas
y tamaño. Ajustar para cada una el respaldo con los seis bancos TRAIN
existentes: candidatas por coseno entre pregunta y unidades; confianza Bayes
ingenuo existente, calibración isotónica fuera de la mitad de negocios usada
para contar; usar umbral 0,4 existente. Variables categóricas: coseno en
pasos de 0,1, margen [0,0.01,0.025,0.05,0.1,0.2,0.4], cobertura conocida
y solapamiento léxico en COVER_BINS. No ajustar con DEV o preguntas nuevas.
Medir además elección sin abstención para distinguir selector y confianza.

## Evaluación común, controles y criterio

DEV público gastado: dos negocios por banco G-62/G-63/G-64, elegidos por SHA
del identificador, conservando todas sus conversaciones. Comparación idéntica
de estable, A, B y las tres C; sin seleccionar casos por resultado. Las tres
rutas principales pasan también el caso completo de panadería, como diagnóstico
conocido excluido de enseñanza y de la medida nueva.

Después de congelar código y modelos, redactor independiente Claude (5.10)
sin herramientas ni lectura del repositorio: ocho negocios diversos nuevos,
doce turnos cada uno, ocho contestables y cuatro sin dato por negocio;
paráfrasis, condiciones y confusiones plausibles. Semilla derivada de huella
del motor y `:G97`. No indicarle categorías ni mecanismos. Guardar y hacer
commit antes de ejecutar. Juez independiente ciego sobre salidas únicas por
pregunta, sin conocer variantes: útil y respaldada, abstención correcta,
abstención indebida, cita irrelevante/incorrecta o afirmación no respaldada.
No afirmar independencia humana: son pruebas redactadas por un LLM externo.

Registrar por alternativa cobertura, acierto con/sin dato, errores previos
conservados y nuevos, citas literales, p50/p95/máximo de `answer` completo,
latencia condicional cuando actúa el respaldo, arranque y preparación aparte.
Retirada reproduce estable; reinicio de tablas/modelos en proceso nuevo.
Control de documento sustituido y ausencia de datos; no almacenar soluciones
de evaluación. La memoria sola no es una ruta de estos modelos.

Meta inicial: ≥60 % útiles entre preguntas contestables, sin nuevos errores
frente al estable, cero afirmaciones no respaldadas y p95/máximo <5 ms,
también en las llamadas donde actúa el respaldo. Meta completa del usuario:
100 % contestables útiles y todas las ausencias bien resueltas en el banco;
reportar distancia sin garantizar generalidad. C debe superar a ambos
controles por ≥3 puntos porcentuales útiles, sin más errores. No promoción
automática ni cambio de límites después del resultado.

## Presupuesto y ejecución

Equipo i7-13620H, RAM 16 GiB; una hebra de inferencia, un trabajo pesado.
Adquisición/compilación ≤1200 s CPU y 1200 pared, descargas ≤600 MiB;
entrenamiento y confianza ≤1200 s CPU; evaluación ≤1800 s CPU/2400 pared;
total local ≤4200 CPU, memoria por proceso ≤3 GiB. Redactor y juez externos
≤600 s pared cada uno, registrar tiempo/costo informado. La excepción de
memoria frente a G-96 se debe al ejecutor/modelo público, no a rescatar métricas.
Medición neuronal incluye importaciones, preparación y ajuste; costo previo de
la base educativa se identifica como reutilizado. Si el modelo B tarda más,
se informa y falla; no ocultarlo en percentiles de consultas que no lo usan.

Archivos: `experiments/g97_backups.py` (A e interfaz),
`g97_neural.py` (C y ajuste), `g97_llm.cpp` y `g97_llm.py` (B),
`g97_evaluate.py` (evaluador común), `test_g97_backups.py` (contrastes).
Fuentes/artefactos bajo `.leobot-data/g97/`, informes `results_v3/g97_*`.
Orden: preregistro y commit; adquisición con revisión/huellas; focales y
trece rápidas; entrenar solo con fuentes educativas congeladas; congelar
modelos antes de DEV; congelar todo antes de reserva; medir y juzgar;
registrar resultados y límites. A no puede esconderse como autoaprendizaje;
C no puede presentarse como LLM general ni B como entrenamiento propio.
