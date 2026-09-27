# G-71 — aprender asignaciones completas de participantes

2026-09-27. Registro antes de implementar. Motor estable:
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`. Solo desarrollo externo;
no modifica `leobot/` ni la base educada del kiosco.

## En palabras fáciles de entender

Leobot puede encontrar palabras relacionadas y aun así confundir qué papel
cumple cada persona o cosa en una frase. Vamos a enseñarle con textos anotados
por personas y comprobar si aprende mejor cuando reconoce todos los
participantes de una acción juntos. La prueba cambiará tanto los documentos
como los verbos entre aprendizaje y evaluación.

No escribiremos qué palabra significa abrir, horario o dirección. Las relaciones
se aprenderán de los ejemplos. Primero se le entrega la estructura correcta de
las frases para aislar esta dificultad. Si no mejora ni con esa ayuda, no se
incorpora. Si mejora, todavía habrá que comprobarlo leyendo texto por sí mismo.
Acertar los participantes de una frase no equivale a responder una pregunta:
la meta del 60 %, las respuestas respaldadas y los cinco milisegundos siguen
pendientes de medirse en negocios nuevos.

## Fuente y diferencia comprobable

La [revisión de fuentes](../results_v3/investigacion_2026_g71.md) contrasta tres
publicaciones de 2026 y explica sus dependencias. La idea elegida procede de
[Van Eecke y Beuls, CoNLL 2026](https://aclanthology.org/2026.conll-main.13/):
aprender correspondencias conjuntas entre estructura y participantes.
Es una adaptación reducida, no una reproducción de su sistema.

G-23–G-25 deciden el papel de cada palabra por separado; G-33 aplica coincidencias
de árboles sin aprender distribuciones de asignaciones completas. F-10/F-12
aprenden expresiones lineales con casillas; F-19 aprende rasgos de grafos para
clasificar pares. Aquí la unidad aprendida es una **asignación conjunta**:
una combinación de rutas y papeles debe existir como conjunto en la educación.
Se conservan el extractor y las probabilidades de G-24; el cambio es el conjunto
de respuestas estructurales admisibles, no añadir palabras ni otra confianza.

Hipótesis refutable: exigir combinaciones aprendidas evita asignaciones locales
incompatibles y mejora la lectura de participantes en verbos y documentos
excluidos de la enseñanza. Si funciona, puede sustituir la decisión independiente
de papeles; no justifica añadir otro lector permanente antes de comprobarlo.

## Diseño fijado

1. Reutilizar `g22_ancora_source_gate`, `g23_role_paths` y
   `g24_calibrated_roles`: fuentes UP/UD AnCora fijadas por revisión y SHA,
   rutas de hasta tres arcos y las mismas etiquetas A0/A1/A2/NONE. Son códigos
   del conjunto educativo, no reglas semánticas escritas para el negocio.
2. Fuente: **train** público, ya usado en G-23–G-25. Toda esta prueba cuenta como
   desarrollo gastado, aunque sus particiones cambien; no es una reserva nueva.
   Dos semillas: primeros ocho dígitos del hash del motor XOR `0x7100`,
   y ese resultado XOR `1`. Separar por hash SHA256 de motor, semilla, clase
   y documento/verbo, residuo módulo cuatro. Evaluación: ambos residuos cero;
   enseñanza: ambos distintos de cero; cruces excluidos. Dentro de enseñanza,
   repetir con las clases `caldoc`/`callemma` para ajuste y calibración disjuntos.
3. Ajustar los conteos de G-24 solo en ajuste. Elegir sus tres umbrales en
   calibración con la rejilla original de 125 combinaciones. Usar exactamente
   estos mismos valores en la referencia y en el candidato.
4. Aprender una construcción de cada asignación completa no vacía cuyos papeles
   están todos representados por el extractor. Agrupar por ruta y clase de
   palabra; conservar el orden relativo cuando varias comparten esa clave.
   Borrar identidades de palabras, documentos y verbos. Compartir construcciones
   idénticas entre ejemplos y contar su frecuencia. No añadir construcciones
   parciales ni combinaciones de papeles que no aparecieron juntas.
5. Aplicar una construcción solo si todas sus casillas encuentran palabras
   distintas con las claves requeridas. Las demás palabras quedan sin papel.
   Entre las aplicaciones completas escoger la de mayor suma de las mismas
   puntuaciones locales calibradas de G-24. La asignación vacía vale cero.
   Empates: frecuencia aprendida y orden de adquisición/aplicación. No escribir
   restricciones como «un solo agente». Pueden aprenderse papeles repetidos.
6. Índice por una clave requerida de cada construcción, elegida por su rareza
   en ajuste. Máximo 25 000 construcciones, ocho casillas por construcción,
   2 048 aplicaciones por frase y dos millones de candidatos extraídos por
   semilla. Si un caso supera el límite de aplicaciones, abstenerse en ese caso
   y contarlo, sin escoger un resultado de una búsqueda incompleta. Un exceso
   global invalida el experimento. Contar exclusiones por tamaño e incompletitud.

Esto representa rutas alrededor de un verbo, no todo el árbol de constituyentes
del artículo. No aprende todavía el sentido del verbo ni condiciones temporales:
se prueba un requisito previo concreto, con estructura y verbo objetivo dados.

## Comparaciones y puerta

- Referencia/ablación: G-24 independiente, mismas experiencias y probabilidades.
- Tratamiento: asignaciones conjuntas aprendidas sobre esa referencia.
- Señal barajada: mismos ejemplos, permutar papeles entre participantes de cada
  construcción, mantener intacto el modelo local. Mide el aporte de sus enlaces.
- Fresco y solo memoria: asignación vacía; no hay documentos ni verbos repetidos
  entre enseñanza y evaluación y no se conserva texto en las construcciones.
- Reinicio: guardar/cargar el inventario y reproducir todas las predicciones.
- Renombrado: cambiar biunívocamente claves estructurales y etiquetas en modelos
  ya aprendidos y entradas; deshacer el cambio debe dar la misma predicción.
- Incompatibilidad: registrar asignaciones que cambian y conjuntos completos
  que empeoran; no usar solo el total de palabras acertadas.

Medir precisión, recuperación y F1 —medida que combina ambos— global y por papel,
asignaciones completas correctas, cobertura, construcciones, aplicaciones y
límites. Dar F1 tanto entre candidatos representados como contando como omisión
todo papel fuera del extractor. Las decisiones se juzgan con esta última.

Puerta **en las dos semillas**: F1 al menos +0,03 sobre referencia, precisión no
inferior, A2 no inferior, asignaciones completas al menos +5 puntos porcentuales,
ventaja F1 de +0,03 sobre barajado, reinicio/renombrado exactos, presupuesto válido,
y p95 de extracción más decisión <5 ms. Si falla, registrar el negativo sin
retocar el diseño ni atribuirlo a toda la familia de gramáticas.

Si pasa, el siguiente preregistro tendrá que medir todos los participantes y
condiciones, usar el analizador aprendido de Leobot, validar sin verbo marcado,
y finalmente evaluar `Bot.answer` con negocios y juez independientes. Antes de
promover siguen pendientes contraevidencia, retirada, señal auxiliar confundida,
preguntas sin dato, aislamiento entre clientes, regresión y tablero. No se dan
por superados aquí ni se inventan controles artificiales para declararlos hechos.

## Presupuesto y reproducción

Por semilla: adquisición/extracción ≤120 s CPU, ajuste/calibración ≤300 s,
evaluación/controles ≤180 s, ≤1 GiB RAM, ≤15 minutos transcurridos. Descargas
UP ≤20 MiB, UD ≤48 MiB, caché persistente con SHA obligatorio. Medir cada fase,
primera carga, extracción, decisión p50/p95/máximo y compilación del inventario.
Sin red ni archivos educativos durante las decisiones.

Antes del ensayo: commit del presente registro; luego commit y tag
`freeze-G71-prototipo` del script. Comprobar hash del motor y fuentes del
experimento antes/después. Ejecución prevista:

```bash
timeout 900s env PYTHONHASHSEED=0 python3 -m experiments.g71_joint_constructions 0
timeout 900s env PYTHONHASHSEED=0 python3 -m experiments.g71_joint_constructions 1
```

No requiere auditor independiente para esta prueba ordinaria de desarrollo
(MISION 5.10); sí antes de promover, ante un resultado sospechoso o al cerrar
una fase. No crea versión estable ni altera las respuestas del usuario.

## Incidencia de preparación, antes de obtener resultados

El primer lanzamiento se interrumpió durante la adquisición: el prototipo
detenía el proceso cuando UP y UD no alineaban palabras. Son las mismas **222
frases** excluidas por los lectores G-22b/G-24, comprobadas en los registros
anteriores y recontadas con las fuentes de SHA fijo. Se corrige para contarlas
y excluirlas como G-24, antes de ajustar modelos o medir la evaluación. No se
cambia muestra por acierto ni puerta. Congelación corregida:
`freeze-G71-prototipo-b`; se conserva el tag anterior. Esta interrupción no
produjo métricas y su tiempo completo no quedó instrumentado; la descarga
inicial quedó en caché, por lo que las corridas siguientes son con fuentes
locales. No atribuir sus tiempos a una primera descarga completa.
