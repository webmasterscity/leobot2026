# G-65 — aprender correspondencias que compiten por explicar la pregunta

Fecha: 2026-09-27. Base: `estable-G-19`, motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
Registro anterior al prototipo. Objetivo solicitado: ≥60 % de respuestas útiles,
cero invenciones observadas, respuesta p95 <5 ms, negocios nuevos sin reglas léxicas manuales.

## Causa e hipótesis

G-59/G-60 no superaron sus pruebas y multiplicar por 3,3 los ejemplos de MFAQ
apenas cambió el resultado. El puente actual cuenta coincidencias independientes:
una palabra de la pregunta se asocia con muchas palabras incidentales de la respuesta.
G-28b ya ensayó IBM-1 con 2000 ejemplos de lectura y retiró correspondencias vacías.
No se presenta repetir ese algoritmo como invención: esta prueba contrasta explícitamente
el papel de frases y de datos de preguntas frecuentes frente a palabras aisladas.

Hipótesis: la competencia entre correspondencias, incluidas secuencias de dos palabras,
aprende asociaciones más específicas que contar toda coincidencia. El resultado debe
mejorar la selección de texto en negocios ajenos a la enseñanza.

Sustrato programado: secuencias contiguas de longitud uno o dos, conteos, normalización
de probabilidades y cinco rondas de estimación de correspondencias (IBM-1).
Ninguna palabra, sentido, respuesta, sector ni pregunta se define en código.
La salida sigue siendo una unidad del documento cargado. La tabla aprendida contiene
probabilidades, nunca respuestas de entrenamiento ni soluciones de los exámenes.

## Fuentes que orientan la decisión

- [Zhou y otros, ACL 2011](https://aclanthology.org/P11-1066.pdf): traducción de frases
  para recuperar preguntas; distingue asociaciones aisladas de contexto local.
  Es un antecedente, no prueba de que funcione aquí. Usa archivos de preguntas y
  respuestas, alineación estadística y combinación de puntuaciones; no demuestra
  comprensión abierta ni ausencia de errores. No copiamos sus cifras como objetivo.
- [Hernandez Cano y otros, 2026, v1, 11 de mayo](https://arxiv.org/abs/2605.09985):
  dos experimentos humanos sobre abstracciones reutilizables en tareas cambiantes;
  seis modelos comparativos. Motiva separar transferencia de ajuste al pasado;
  su tarea geométrica no valida lectura ni proporciona un mecanismo lingüístico listo.
- [ADVENT, 2026, v1](https://arxiv.org/abs/2607.01585): inventa predicados guiado
  por un modelo de lenguaje; incompatible con la ruta operacional y no se adopta.

## Enseñanza y desarrollo

Se reconstruye primero la base histórica desde AnCora, COSER, MLQA y SQuAD-es con
los scripts existentes. MFAQ `es/train`, SHA `c985eb099bcdadf87baa778786148e4de6c9a84057e68b4268ea2f832b884c66`:
misma muestra G-57 (semilla 57, máximo 100 pares por dominio); se excluyen los
dominios de calibración G-57. Se deduplican pares normalizados en el candidato
y sus ablaciones. Los términos candidatos requieren apoyo en cinco dominios;
se limita la tabla por soporte, no por inspección de palabras.

Desarrollo: bancos gastados `desarrollo` A–F y G-59/G-60, nunca duxiV2.
Es diagnóstico, no reserva. Se informa el techo de unidades que contienen todas
las claves antes de comparar; se conservan las limitaciones del juez automático.
Tres modelos previamente fijados: puente actual; alineación de palabras;
alineación de palabras y pares contiguos. Cinco iteraciones para los dos últimos.
Mezcla del puntaje nuevo y el anterior elegida únicamente en A–D entre 0, 0,25,
0,5, 1 y 2. Comprobación de desarrollo separada en E–F y G-59/G-60.
No se cambia esa rejilla después de medir.

Puerta para integrar: al menos +5 puntos de selección útil y ≥60 % de selección
útil en las preguntas directas y sí/no del desarrollo separado. Una puntuación
inferior impide alcanzar 60 % mediante abstención, así que se descarta sin abrir
una reserva. La mejora debe superar a palabras aisladas en ≥2 puntos para
conservar la parte de frases. Recalibrar el silencio no sustituye esta puerta.

## Reserva y controles, solo si pasa desarrollo

Integrar el candidato útil en `ContextMixin`, con enseñanza pública mediante datos
y persistencia en `context_model`; retirar el prototipo duplicado. Congelar motor
antes de solicitar 24 negocios nuevos a redactores independientes (5.10), que
solo reciben la interfaz y un encargo neutral. Guardar material en git antes de
ejecutar. Juez independiente ciego, misma información para ambos sistemas.

Puertas finales: útiles ≥60 % de directas y sí/no; cero inventadas; citas engañosas
no superiores a la base; ≥95 % de abstención correcta cuando falta el dato;
p95 <5 ms; no retroceso en conversación, lectura fija y regresión.
No basta con citar algo que existe si no responde a la pregunta.

Controles: mismo texto y datos sin candidato, palabras sin frases, asociaciones
barajadas, bot fresco, memoria de ejemplos sin transferencia (solo coincidencia
exacta, fuera del motor), documento incompatible, cambio de valores/retirada de
documento, reinicio y renombrado. El renombrado total de símbolos se mide además
en un mundo sintético separado, sin atribuirle comprensión humana.
Tres semillas para orden de enseñanza; semilla de reserva derivada del motor.
Si no pasa desarrollo, auditor independiente verifica ese resultado y no se crea
tag estable ni se declara refutada toda la fase G.

## Presupuesto y ejecución

Reconstrucción ≤15 min, prototipo ≤20 min CPU, ≤1,5 GB RAM adicional, máximo
2 procesos pesados, al menos 2 GB disponibles. Enseñanza 5 rondas, máximo 2 millones
de asociaciones; si excede se informa truncamiento y no se oculta el costo.
Desarrollo ≤10 min; eventual evaluación nueva ≤45 min y auditoría ≤20 min.
Todo comando largo lleva `timeout`. Registrar CPU de adquisición, entrenamiento,
validación, consolidación y respuesta; ejemplos, candidatos, RAM y tamaño de tabla.
Comprobar huella del motor antes y después. No cambiar criterios con resultados.

## En palabras fáciles de entender

Queremos que Leobot aprenda qué formas distintas de decir algo están relacionadas.
Le mostraremos preguntas reales y sus textos correspondientes, sin escribirle
listas de equivalencias. Después deberá encontrar el texto adecuado en negocios
que no enseñaron esas relaciones. Si confunde temas, no llega a la mejora acordada
o se vuelve lento, conservaremos el resultado y descartaremos el cambio.
