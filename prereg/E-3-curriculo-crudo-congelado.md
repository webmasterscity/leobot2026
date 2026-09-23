# E-3 — ¿Basta educar el motor actual con prosa real?

Preregistrado antes de escribir el evaluador. E-1b probó 20 bots frescos, uno por pasaje, y halló cero hechos. E-2 descartó un buscador léxico como mecanismo suficiente. La explicación rival es que el motor actual necesita ver varias fuentes independientes para inducir construcciones transferibles. Este ensayo decide si educación sin código ya mejora la lectura.

## Familia y partición

Usar MLQA español de desarrollo, archivo y SHA-256 fijados en E-1. Excluir los identificadores usados en tablero, E-1b y E-2. Derivar la semilla de `sha256((<huella de freeze-E-3> + ':E-3').encode())`. Escoger 30 pasajes de artículos distintos para enseñanza y 20 preguntas de **otros artículos** para prueba. Selección ordenada y aleatoria con esa semilla, después de congelar el motor; ningún texto se edita ni se traduce manualmente. El bot recibe solo los 30 pasajes crudos por `ingest_document_text`, sin preguntas ni respuestas. En prueba, primero se pregunta antes de leer el pasaje nuevo, luego se le entrega solo ese pasaje y se repite la pregunta. Se evalúan las 20 preguntas una a una sobre copias del bot educado, de modo que no filtren respuestas entre sí.

## Controles y métricas

Comparar bot educado, bot fresco y bot con los mismos 30 pasajes pero `raw_relation_min_support=1000` para impedir promociones de relaciones crudas; los tres reciben el pasaje de prueba. Contar hechos adquiridos, relaciones promovidas, respuestas exactas y respuestas con evidencia comprobable. Guardar/cargar el bot educado antes de prueba y verificar que sus respuestas no cambian. Texto presente sin aprendizaje es control de memoria. Artículos disjuntos hacen más difícil memorizar una entidad concreta; el resultado aún será interno al desarrollo de MLQA y no demuestra transferencia entre dominios. No se inyecta contraevidencia porque no se ensaya ningún mecanismo nuevo de revisión; será obligatoria en un ensayo de promoción. Medir CPU de educación, lectura y respuesta, RAM pico y tiempo de pared. No llamar «comprensión» a texto retenido sin respuesta verificada.

## Umbral, presupuesto y refutación

Si el bot educado obtiene al menos 3/20 respuestas exactas **y** supera tanto al fresco como al control sin promociones en al menos 3 casos, priorizar más educación y analizar las trazas antes de programar un parser. Si no, registrar «educación cruda insuficiente» y diseñar mecanismo nuevo de extracción de significado. Un aumento solo de hechos opacos sin respuesta comprobable no supera el umbral. Presupuesto: 30 pasajes + 20 pruebas por condición, 150 s de pared, 90 s CPU, 80 MiB de descarga. Motor idéntico al tag `freeze-E-3` antes y después; tres semillas de hash solo si aparece una variación.
