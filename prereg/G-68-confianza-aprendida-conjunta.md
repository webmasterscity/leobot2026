# G-68 — aprender conjuntamente cuándo sirve una cita

Fecha: 2026-09-27. Preregistro antes del código. Base estable G-19, motor
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## Diagnóstico reproducido y causa que se prueba

El usuario entregó el documento completo de una panadería y la orden exacta.
Con esa entrada, tanto el horario como la dirección quedan primeros en la
selección, pero se descartan con confianza 0,2784 y 0,2302 (cita desde 0,4).
La prueba anterior con una sola línea no reproducía este caso. Se corrige el
registro y se conserva el ejemplo como diagnóstico visible, nunca enseñanza
ni reserva. Estacionamiento ausente debe seguir sin respuesta.

G-65–G-67 evaluaron selección de evidencia, pero aquí la evidencia correcta ya
está seleccionada. La confianza de G-60 combina por separado siete pistas;
su independencia puede ser una aproximación mala. Hipótesis: aprender sus
interacciones permite reconocer más citas útiles con igual umbral y sin
aumentar citas sin dato. No se añaden palabras ni pistas para horarios o lugares.

## Fuentes y comparación con lo existente

[Smits 2026, v2, 2 de junio](https://arxiv.org/abs/2605.22740v2) estudia confianza
local en árboles y compara métodos en 71 conjuntos tabulares; no prueba lectura
ni comprensión. Motiva medir incertidumbre condicionada por varias pistas, no
copiar sus cifras. [Torabian y Urner 2024](https://arxiv.org/abs/2412.00943)
compara calibración mediante árboles y advierte que calibrar no implica acertar.
Aquí se reutilizan los siete rasgos de G-60, la ganancia de información ya usada
en los aprendices y la calibración isotónica; la novedad experimental es su
combinación para la abstención del kiosco. G-39 probó árboles para escoger tramos
de lectura y falló: no se atribuye a árboles una capacidad general por sí mismos.

## Sustrato y datos

Árbol binario de igualdad de rasgos, divisiones elegidas por reducción de impureza,
hojas con frecuencia suavizada; máximo seis niveles, mínimo 20 ejemplos por hoja.
Dos candidatos fijados: un árbol, y promedio de 15 árboles con remuestreo.
Ningún nodo ni decisión léxica se escribe a mano. Semillas 0, 1, 2 para el promedio.
El motor sigue citando texto cargado; no genera contenido nuevo.

Enseñanza: mismos bancos gastados de la confianza G-62 (G-57–G-61 y desarrollo),
con etiqueta automática por claves, limitación declarada. Partición por negocio,
cinco grupos por SHA-256, para obtener puntuaciones fuera de enseñanza y ajustar
la frecuencia. Se informa además Brier —error de las probabilidades—. Cuando
varias observaciones tienen igual puntaje se agregan antes del ajuste isotónico;
se revisa si el ajuste anterior separaba empates y, si ocurre, se mide como control
aparte (no se atribuye su efecto al árbol).

Desarrollo separado: G-62, G-63 y G-64, ya usados en la historia; no se llamarán
reserva. Se mide antes el techo de la selección actual. Base histórica sin cambio,
misma base con calibración de empates correcta, árbol y promedio. Umbral 0,4 fijo.
Se elige entre árbol y promedio por Brier fuera de enseñanza, nunca por los casos
del usuario ni por el banco de comprobación. En el promedio se informa variación
de las tres semillas; no se elige la mejor.

## Puertas

Este paso busca una mejora parcial del aprendizaje de abstención: ≥5 puntos más
de citas útiles en directas y sí/no que la base, sin aumentar la proporción de
citas sin dato sobre preguntas sin respuesta. Los tres órdenes deben cumplir;
la corrección de empates se atribuye por separado. La meta global del usuario
sigue siendo ≥60 % útil, cero invenciones observadas, p95 <5 ms; una mejora
parcial no se declara cumplimiento de esa meta ni inteligencia general.

Si desarrollo pasa: integrar la inferencia y enseñanza genéricas en el mecanismo
de confianza existente, congelar motor, solicitar material nuevo independiente,
guardar antes de ejecutar y usar juez ciego. Exigir las mismas puertas de mejora,
cero inventadas y no más engañosas que la base, más regresión y latencia. Reportar
explícitamente si falta llegar a 60 %. Sin nueva reserva no hay promoción.

Controles: los mismos datos con Bayes actual, empates corregidos, sin aprendizaje,
etiquetas barajadas por negocio, igual información, documentos incompatibles,
cambio/retirada del dato, reinicio y renombrado. Los últimos cuatro son obligatorios
antes de integrar; se declaran no corridos si desarrollo falla. El ejemplo del
usuario se repite después de elegir el modelo y no decide su selección.

## Presupuesto

Preparación y aprendizaje ≤10 min CPU, ≤1 GB adicional, respuesta <5 ms; máximo
dos procesos pesados. Validación ≤10 min; reserva y juez ≤45 min; auditoría ≤15 min.
Registrar ejemplos, candidatos, CPU por fase, memoria y huella antes/después.
Si falla, se conserva el resultado sin modificar el motor ni bajar el umbral.

## En palabras fáciles de entender

En el documento completo, Leobot encuentra las líneas correctas pero no se anima
a mostrarlas. Probaremos si puede aprender mejor cuándo su elección sirve, mirando
varias pistas juntas. No le diremos qué contestar a esa panadería ni bajaremos la
exigencia para responder. Tendrá que mejorar con otros negocios y seguir callando
cuando el dato no exista.

## Resultado de desarrollo (2026-09-27)

No pasó: promedio seleccionado por error fuera de enseñanza, 242–245/816 útiles frente a 269/816 de la base. Caso completo del usuario sigue absteniéndose en horario/dirección. CPU 14,6 s; RAM 522 MiB. No integrado. Auditoría independiente: métricas reproducidas con hashseed 1; ver `results_v3/auditoria_g68_g70.md`. Verificación posterior mediante `Bot.answer` real confirma los mismos conteos (`results_v3/g68_g70_respuestas_reales.json`). No hubo reserva ni juez nuevos.
