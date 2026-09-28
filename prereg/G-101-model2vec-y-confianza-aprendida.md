# G-101 — Model2Vec como información para elegir y calibrar

2026-09-27. Propuesto por el usuario durante G-100: «y si usamos Model2Vec
para confianza?». Sigue vigente la excepción neuronal externa, sin integración
automática en `leobot/`. G-99/G-100 conservan todos sus resultados negativos.

## En palabras fáciles de entender

Model2Vec transforma un texto en números que permiten comparar significados
rápidamente. Eso puede ayudar a encontrar el fragmento correcto, pero semejanza
no equivale a certeza. Probaremos su búsqueda sola y combinada con nuestro
selector, que aprenderá con ejemplos cuándo una cita contesta y cuándo falta
el dato. Lo mediremos contra el modelo propio y la versión estable.

No descargaremos un modelo grande que escriba respuestas: este modelo prepara
representaciones y la salida seguirá siendo una cita del documento. La confianza
se ajustará con ejercicios separados de enseñanza. No cambiaremos mínimos ni
ejemplos después de ver el examen. Una mejora necesita aciertos, prudencia y rapidez.

## Fuente y mecanismo

[Ficha oficial](https://huggingface.co/minishlab/potion-multilingual-128M),
revisión `73908c3438cf03b6a01bcb9611d62b23d0726f08`: modelo estático multilingüe
de 256 dimensiones, destilado de BGE-M3 y enseñado con C4; licencia MIT. No
inferir que 128 M implica ejecutar un Transformer de ese tamaño por consulta.
[Biblioteca oficial](https://github.com/MinishLab/model2vec), versión PyPI
0.9.0: permite representaciones y clasificación entrenable. Se mide velocidad
local; «hasta 500×» no certifica cinco milisegundos ni utilidad del kiosco.

Entorno virtual local aislado con bibliotecas ya instaladas visibles; instalar
solo Model2Vec base, sin extras de distillation/train ni modelos maestros.
Descargar archivos de la revisión fijada, registrar tamaños y SHA. Sin servicios
de inferencia remotos, GPU ni texto de evaluación enviado a terceros.

Hipótesis H1: representación previa más amplia mejora la elección respecto a
G-98. H2: entrenar decisión/confianza con coincidencias exactas y similitud es
mejor que equiparar similitud con probabilidad. Copiar frases no certifica utilidad.

Variantes: `static`, mejor unidad por coseno Model2Vec y confianza isotónica;
`hybrid`, red G-99 Decision de 48 unidades, variables lexicales G-99 (13) más
coseno de pregunta/unidad Model2Vec, margen respecto a las demás y contraste
con media de unidades; `shuffled`, igual que hybrid con preguntas permutadas
por grupo. No vectores completos como variables: G-99 mostró sobreajuste al
añadirlos. Sin historial nuevo en este ensayo para aislar esta representación.
Model2Vec congelado; solo enseñar la red de decisión, no llamarlo entrenado
desde cero. Estandarizar variables con enseñanza; 24 épocas, AdamW 0,001,
decaimiento 0,001, lote 64, semilla 1, pérdida G-99 con opción vacía y componente
binaria. Para static exigir coseno positivo; para red exigir puntaje >0.

Reusar exactamente la enseñanza/particiones G-98 y sus huellas antes de añadir
variables. 6000 SQAC humanos +1737 ejercicios sintéticos de negocios; 1798 de
comprobación educativa y 455 propuestas de calibración, separados. Ningún caso
G-97/G-98 común ni panadería enseña. La confianza isotónica se ajusta solo con
calibración. Mínimos 0,4 y 0,9 fijados; principal hybrid a 0,9. Reportar ambos,
sin escoger mínimo por resultados. Similaridad sin calibrar no se presenta
como porcentaje de corrección. Medir selección cruda, probabilidad calibrada
y respuestas reales por separado. No aumentar contexto con conocimientos externos.

## Evaluación, controles y presupuesto

Mismo evaluador G-97 y muestra gastada de 157 turnos/102 contestables: estable,
G-98, static/hybrid/shuffled en ambos mínimos. Meta ≥62/102 útiles, cero errores
nuevos y p95/máximo completo y condicional <5 ms. Paso intermedio ≥5 útiles más
que G-98 sin errores nuevos. Panadería aparte; reinicio hashseed 1, desactivación,
cambio/vaciado del documento, huellas y exportación NumPy. Trece rápidas y
focales pertinentes. Calcular también error cuadrático de confianza en DEV,
solo diagnóstico, no usarlo para ajustar. Si pasa, reserva independiente nueva
antes de afirmar generalidad; si falla, documentar sin promoción.

Adquisición/entorno ≤650 MiB de descargas, 600 s CPU/900 s pared. Enseñanza y
confianza ≤900 CPU/1200 pared; evaluación/reinicio ≤240 CPU/400 pared. Una hebra,
un trabajo pesado, RSS ≤3 GiB por proceso. Una instancia compartida de pesos
Model2Vec de solo lectura; no duplicar la tabla por variante. Costos anteriores
reutilizados. Artefactos `.leobot-data/g101/`, resultados `results_v3/g101_*`.
Preregistro/commit; adquirir/verificar; implementar/contrastar; congelar y enseñar;
congelar modelos; medir/repetir; informar utilidad/errores/tiempo y recomendación.
