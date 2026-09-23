# G-20 — ¿faltaban ejemplos o falta representación?

Fecha: 2026-09-23. Preregistro anterior al evaluador. Motor H0 `1f3187f2ced4c97364503187d074815f33612326`. G-19, con 411 ejemplos de un solo triple, obtuvo 28/79 frente a 31/79 por tipo de entidad; se rechazó. El código de clasificación G-19 se conserva fijo para aislar el efecto de más experiencia.

## Hipótesis discriminante

Hipótesis: aprovechar triples de párrafos con varias relaciones, cuando las dos menciones están cerca y el mismo par no recibe dos etiquetas diferentes en ese párrafo, da suficiente variedad de lenguaje para superar el control por tipo. Alternativa: el contexto léxico de G-19 no representa la relación con generalidad; más ejemplos débiles mantienen o empeoran el resultado. [Mintz y otros](https://aclanthology.org/P09-1113/) muestran la posibilidad y el ruido de supervisión distante; [relajación convexa de 2014](https://aclanthology.org/D14-1166/) trata etiquetas latentes. Este ensayo no implementa su método: mide primero si la cantidad extra puede cambiar la decisión. BabyDS 2026 enseña significados por pares oración/estructura en un mundo acotado; no justifica atribuir lectura libre a este clasificador.

## Datos, partición y aprendizaje

Mismo `train.es.jsonl` REDFM fijado y hash G-19. Elegir artículos excluidos nuevos con particiones G-15 semillas **977 primero y 1039 después**; no reutilizar 911 como reserva decisiva. Algunos artículos pueden coincidir entre particiones aleatorias; G-19 solo publicó agregados, nunca sus textos. Mantener el evaluador anterior de G-19 como ablación de educación: determina relaciones elegibles con ≥5 ejemplos de ≥3 artículos **de un solo triple**, aprende solo de esos ejemplos. Tratamiento: los mismos más ejemplos de párrafos con varios triples, usando cada triple como episodio candidato si sus menciones cumplen separación ≤160 caracteres, sin `.?!` ni salto entre ellas, y si el mismo par de entidades tiene una sola relación en ese párrafo. Aplicar exactamente la extracción de rasgos, ponderación inversa y centroides coseno de G-19; cada ejemplo pesa uno. La única diferencia del tratamiento es experiencia adicional, sin ajuste de parámetros.

Prueba: párrafos excluidos con un triple, límites de ambas menciones entregados por el evaluador, relaciones elegibles por el control de un solo triple y pares de entidades ausentes de **toda** la educación. Así la comparación es pareada. Este sigue siendo un techo condicional, no lectura autónoma ni nuevo mecanismo integrado en Leobot. No abrir `dev/test` oficiales ni textos excluidos antes de congelar el evaluador. Conservar solo resultados agregados.

## Controles, métrica y puerta

Además del tratamiento y ablación G-19, incluir con toda la educación: tipo de entidades solamente, etiquetas barajadas dentro del par de tipos, memoria exacta y fresco. Medir estrato confundido donde un par de tipos admite ≥2 relaciones educativas. Renombrar todas las superficies de entidad del ensayo debe conservar cada predicción. Párrafos de prueba con varios triples se registran como estructura incompatible y no puntúan. Persistencia, corrección y texto crudo no aplican a este techo; se exigirán en la integración si pasa. Código y motor congelados antes/después de cada semilla.

Puerta **en cada semilla**: ≥60 pares nuevos elegibles, ≥5 relaciones, exactitud tratamiento ≥45 %, ventaja ≥10 puntos absolutos sobre el mejor de ablación G-19, tipo y etiquetas mezcladas; al menos 5 relaciones con acierto; ≥20 casos de tipo confundido y ventaja ≥10 puntos frente al mejor control en ese estrato; renombrado idéntico. Repetir la primera semilla con `PYTHONHASHSEED=0/1`: predicciones y conteos discretos iguales. CPU total ≤30 s, pared ≤60 s, RSS ≤128 MiB por semilla. Reportar carga, adquisición, predicción, ejemplos, candidatos, RAM y número de rasgos. Si 977 falla, detener 1039 y no integrar la variante. Si pasa ambas, preregistrar integración posterior con extracción de entidades sin límites externos, persistencia, corrección y fuentes adicionales; no crear tag aquí.

## En palabras fáciles de entender

La prueba anterior tuvo pocos ejemplos claros. Ahora probaremos si las frases con varias relaciones aportan ejemplos adicionales que enseñen algo útil. Usaremos otros artículos y compararemos contra aprender solo de frases claras y contra fijarse solo en los tipos de nombres. Si no mejora, necesitaremos una forma distinta de entender la estructura de las frases.
