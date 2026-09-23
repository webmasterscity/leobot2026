# G-13 — aprender vínculos entre fragmentos y papeles en ámbitos nuevos

Fecha: 2026-09-23. Preregistro anterior al código. H0 = `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. [G-12](G-12-fuente-independiente-roles.md) pasó la puerta de fuente, no una puerta de aprendizaje. MASSIVE español es una localización de inglés y contiene anotaciones explícitas; esto prueba aprendizaje **desde instrucción**, no desde lectura libre.

## Fallo, hipótesis y alternativa

G-10 aprendió pistas de acciones SQL pero no reconstruyó la estructura completa; G-11 añadió poco. `Language.teach` alinea valores conocidos dentro de una construcción completa, y su parser agotó 10 ms por consulta en G-9c al recibir miles de ejemplos. Falta un mecanismo de búsqueda local que asigne **fragmento y papel juntos** en frases con entidades no vistas. Hipótesis: el mismo principio de pistas explícitas y auditables sirve para candidatos de fragmento, combinando superficie, forma y palabras vecinas, sin depender del ámbito. Alternativa sencilla: solo recordará nombres o contextos de la fuente; el control de memoria o las etiquetas barajadas igualarán su calidad en ámbitos nuevos.

Si funciona, se podría reemplazar parte de las construcciones exactas en `Language` por una propuesta local de argumentos **solo después de demostrar** que mejora las pruebas de Leobot y no degrada latencia. Por ahora el aprendiz vive fuera del motor y no cuenta como habilidad adquirida por Leobot.

## Datos y particiones

- Usar únicamente `es-ES.jsonl`, SHA-256 `310462a79fa181ff83c643a8d356c7b8155fd37a25e80a77ba3ca9b29305c4a5`, filas `partition=train`. Partir 18 ámbitos completos con semillas 719/787/853, H0 y `0x69B`, exactamente como G-12. No seleccionar frases por dificultad. Los ámbitos excluidos solo aportan `utt` al aprendiz; `annot_utt` llega al evaluador después de la predicción.
- Extraer fragmentos por la sintaxis general `[papel : texto]` y alinearlos literalmente con `utt`; tokenizar palabras Unicode con desplazamientos. Generar candidatos de 1–6 palabras consecutivas. Longitudes mayores siguen en el denominador y cuentan como fallos. Una etiqueta enseñada es elegible si aparece en ≥3 ámbitos de educación y ≥20 anotaciones. Todas las demás permanecen en la evaluación general, pero no se exige que el aprendiz invente sus nombres.

## Tratamiento, controles y reglas de búsqueda

- Tratamiento: para cada fragmento positivo de educación, contar rasgos reutilizables de superficie, forma, longitud y contexto izquierdo/derecho con su papel y procedencia de ámbito. Contar su presencia entre todos los fragmentos candidatos de educación. Promover solo rasgos observados en ≥5 positivos de ≥2 ámbitos y ≥20 candidatos; estimar ventaja explícita sobre la frecuencia base con suavizado unitario. En una frase nueva, puntuar cada par candidato/papel y seleccionar un conjunto sin solapamientos por programación dinámica; un puntaje insuficiente implica abstenerse. Ninguna palabra ni etiqueta de MASSIVE se programa como regla. Límite de 1 000 pares evaluados por frase y p95 ≤10 ms.
- Ablación sin contexto: misma educación y búsqueda, solo rasgos internos del fragmento. Solo memoria: guardar cadena del fragmento→papel y recuperar solo coincidencias exactas unívocas. Misma información simple: papel más común entre las anotaciones y las cadenas vistas. Control confundido: permutar papeles de fragmentos **dentro de cada ámbito**, conservando texto, fronteras y frecuencias. Bot fresco: no proponer fragmentos. `Language` no es control justo en este piloto: G-9c mostró que enseñar miles de construcciones lo hace agotar 10 ms por consulta; su ruta se comparará antes de una posible integración.
- Guardar/cargar modelo declarativo; contraevidencia sintética local que invierta una pista después de ejemplos en ámbitos distintos; renombrar a un símbolo nuevo los valores de fragmentos de una sola palabra de una muestra determinista y reportar estabilidad y abstención por separado. No exigir estabilidad si la forma del valor contiene información legítima (por ejemplo, un número). No usar `eval`, shell generado, LLM, red neuronal ni datos del evaluador durante el aprendizaje.

## Métricas, puerta y presupuesto

Medir F1 micro de **frontera exacta + papel** sobre papeles elegibles en ámbitos excluidos, F1 sobre cadenas de fragmento no vistas en educación, F1 sobre todos los papeles, exactitud por frase, precisión/cobertura, tasas por papel, coste de educación, enumeración, validación, respuesta, RAM y candidatos. Reportar cuántas anotaciones exceden seis palabras. El control de mezcla recibe idéntica información y presupuesto. Repetir semilla 719 con `PYTHONHASHSEED=0/1`; los conteos y predicciones deben coincidir.

La puerta pasa **en cada semilla** solo si F1 exacta+papel sobre papeles elegibles ≥0,55 y ≥0,15 por encima del mejor control; F1 sobre cadenas nuevas ≥0,35 y ≥0,10 por encima de memoria; al menos tres papeles con ≥20 anotaciones excluidas logran F1 ≥0,30; reinicio, contraevidencia y H0 pasan. CPU total ≤120 s, pared ≤180 s, RSS ≤256 MiB, p95 ≤10 ms y ≤1 000 pares por frase. Si falla, registrar causa y no integrar. Si pasa, aún se necesita una fuente distinta y una prueba de lectura abierta antes de promover el mecanismo al motor; un corpus de órdenes con anotaciones no demuestra AGI.

## En palabras fáciles de entender

Le mostraremos ejemplos de frases donde se marca qué parte es un nombre, un momento u otro dato. Después tendrá que encontrar esas partes en preguntas de ámbitos que no vio al aprender. Si solo reconoce las mismas palabras de siempre, la prueba con nombres nuevos y los controles lo dejarán claro.
