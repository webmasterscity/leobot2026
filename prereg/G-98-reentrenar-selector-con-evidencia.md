# G-98 — reentrenar el selector con evidencia

2026-09-27. Preregistro anterior a código y resultados. El usuario reabre
solo el entrenamiento: «entrenalo un 100% mejor». Se interpreta como aspirar
a duplicar las 29 respuestas útiles, no como una garantía ni una orden de
modificar el examen. La meta anterior de 60 % exigiría al menos 62/102.

## En palabras fáciles de entender

El modelo anterior no añadió ninguna respuesta. Aprende a relacionar preguntas
y respuestas frecuentes, pero acierta poco cuando debe escoger una frase entre
varias dentro de un documento. Probaremos si más práctica de lo mismo basta y
si enseñar directamente esa elección funciona mejor. También practicará cuándo
no hay respuesta. Nunca se le enseñan las preguntas usadas para medir el resultado.

Separaremos negocios completos para enseñar, comprobar y ajustar la confianza.
No bajaremos el mínimo de confianza después de ver los resultados. Compararemos
con el modelo anterior y con otro que recibe preguntas confundidas. Registraremos
aciertos, errores y tiempo; mejorar en ejercicios no basta para anunciar el doble
de utilidad. Esta tanda termina con resultados y propuesta, sin nuevas búsquedas
de modelos ni cambios en el Leobot estable.

## Hipótesis, alcance y controles

H1: la enseñanza localizada mejora la elección y la utilidad frente a G-97
y a continuar su enseñanza original. Se conserva la red de G-97: vocabulario
fijo, promedio de vectores de 64 números, proyecciones distintas de pregunta
y respuesta. Inicio con pesos G-97 entrenados, SHA registrado. Modelo externo,
no LLM generativo. Excepción neuronal del usuario vigente para esta prueba.
No reglas semánticas manuales, no modelo público nuevo ni cambios en `leobot/`.

Variantes fijadas:
- `original`: G-97 congelado, incluido su filtro de confianza.
- `more`: otras seis pasadas por los mismos 6000 pares MFAQ, con su muestreo,
  vocabulario y pérdida contrastiva; AdamW nuevo, 0,003, semilla 1. Es doce
  pasadas totales, no afirmación de duplicar calidad. Recalibrar en el conjunto
  separado de G-98; conservar comparación original sin recalibrar.
- `localized`: doce pasadas de enseñanza localizada descrita abajo, AdamW
  0,001, decaimiento 0,0001, lote 32, temperatura 0,1, semilla 1. Elegir una
  unidad o una opción vacía, cuyo puntaje lineal desde la pregunta se aprende.
- `shuffled`: igual que localized, pero preguntas permutadas dentro de cada
  grupo educativo, conservando documentos y etiquetas; reportar cuántas cambian.

Sin escoger épocas ni variantes por los resultados de desarrollo. Mantener
todas las variantes, sin nuevas búsquedas de hiperparámetros en esta tanda.

## Enseñanza y separación

Reusar SQAC humano local, SHA de G-78, y bancos TRAIN declarados de G-68.
Estos últimos contienen material sintético previo: se declara aparte; no
son preguntas humanas ni una nueva reserva. El banco común G-97, su panadería,
PAR-6, duxiV2 y entregas G-97R2 no entran a entrenamiento ni confianza.

SQAC: reutilizar segmentación/validación de posición de G-78. Grupo por fuente
y artículo; SHA(grupo) módulo 5: 2/3/4 enseñanza, 1 comprobación, 0 excluido.
Primeros 6000 ejemplos educativos y 1000 de comprobación por SHA(id). Solo
fragmentos que contienen la respuesta anotada y al menos una alternativa.
Todas las unidades que contienen literalmente esa respuesta son positivas.
Máximo 16 unidades por ejercicio: todas las positivas que quepan y rivales
con mayor similitud según G-97 congelado; excluir si positivas >16. No crear
ausencias borrando frases: podría quedar otra respuesta válida.

TRAIN de negocios: grupo banco/negocio, SHA módulo 5: 2/3/4 enseñanza, 1
comprobación, 0 ajuste de confianza. Unidades del segmentador operacional;
positivas si contienen todas las claves del autor. Excluir ejemplos contestables
sin unidad positiva, y charla. Ausencia solo cuando el autor indica abstenerse
o derivar. Historial no se añade al selector en este ensayo; las referencias
dependientes del diálogo son un límite declarado. Máximo 16 unidades por
ejercicio para enseñar; en inferencia se consideran todas. Ninguna pregunta,
respuesta o clave se guarda en pesos como tabla de consulta.

Enseñanza localizada: pérdida logaritmo de suma de probabilidades de todas
las unidades positivas; en ausencia, la opción vacía. Puntajes de unidades
por coseno/0,1, puntaje vacío aprendido linealmente. Máscaras excluyen relleno.

Confianza: mismas cuentas e isotónica existentes, solo grupos de ajuste, dos
mitades por SHA de grupo; rasgos G-97 más margen frente a opción vacía donde
existe. Mínimo 0,4. Mantener una opción vacía elegida como abstención.
No ajustar con los grupos usados para entrenar los pesos. Reportar aparte
precisión cruda, elección vacía y confianza máxima: ni confianza ni exactitud
educativa se convierten en utilidad real.

## Medidas, puertas y costo

Comparación común G-97: estable, original, more, localized y shuffled; 157
turnos gastados, no reserva independiente. Mismo evaluador automático, estados
y citas que G-97. Meta solicitada ≥58/102 útiles, meta previa ≥62/102; cero
errores nuevos frente al estable, literalidad, p95 y máximo de respuesta
completa y condicional <5 ms. Localized debe superar more y shuffled por al
menos tres útiles y mejorar las seis elecciones crudas correctas de G-97.
No modificar las respuestas ya entregadas por el estable en este ensayo.

Comprobación educativa aparte con grupos excluidos de pesos/confianza.
Panadería exacta después de congelar; reinicio en proceso nuevo y otro hashseed;
desactivación exacta, reemplazo de documento, equivalencia PyTorch/NumPy y
pérdida que realmente enseña selección/ausencia. Trece rápidas antes/después.
Si desarrollo no pasa las puertas, cerrar negativo sin nuevos autores/jueces.
Si pasa, hace falta examen independiente nuevo antes de afirmar generalización
o promover; no reutilizar como reserva los bancos vistos.

Presupuesto nuevo: preparación/enseñanza/confianza ≤900 s CPU y 1200 s pared;
evaluación/reinicio ≤180 s CPU y 300 s pared; RSS por proceso ≤3 GiB; una
hebra de cómputo y un proceso pesado. Artefactos G-97 de solo lectura, costos
previos identificados como reutilizados. Datos/modelos en `.leobot-data/g98/`,
resultados `results_v3/g98_*`. Código y modelos congelados antes de medir.

Plan: comprobar base y controles; preparar/enseñar/exportar; congelar; medir
común y panadería, repetir proceso; registrar resultados y terminar esta tanda.
Se aplica la propuesta ya documentada en G-97; no hace falta otra búsqueda
bibliográfica para volver a comprobar esta hipótesis específica.
