# Preregistro del primer tablero AGI

Fecha: 2026-09-22. Referencia congelada: `estable-A-1`, árbol del motor `644c55528a5fd97a8822f719f70e11cfae242783`. El tablero sirve para detectar el mayor obstáculo; no certifica AGI.

## Baterías y criterios fijos

- Lenguaje español abierto: 20 preguntas de `dev-context-es-question-es.json` de [MLQA](https://github.com/facebookresearch/MLQA), elegidas con `random.Random(int('644c5552', 16))` sobre los identificadores ordenados. Para cada caso, entregar el párrafo por `ingest_document_text`, luego preguntar por `respond`, sin anotación semántica ni reparación manual. Registrar respuesta con evidencia y coincidencia exacta normalizada con alguna respuesta oficial. Esta muestra pública de desarrollo es diagnóstica, no reserva final.
- Razonamiento relacional y abstracción: los tres resultados reservados A-1, con su ablación y contraevidencia, se reportan como evidencia interna limitada. Causalidad se marca **no evaluada** porque esos ensayos no aíslan intervenciones causales generales.
- Transferencia a dominios nuevos: registrar el control histórico no isomorfo (3 ejemplos educado y 3 fresco) como **sin transferencia**. No convertir el renombrado de A-1 en una mejora aquí.
- Planificación y uso de herramientas: marcar **no evaluado en tarea pública nueva** hasta tener una interfaz de tarea externa con información y herramientas igualadas. Las pruebas internas de planificación no son una referencia frontier.
- Conversación útil: registrar el diagnóstico interno de diálogo mixto (8/13) solo como visible, sin puntaje de reserva. Autocorrección e incertidumbre: A-1b confirma retirada en 3 órdenes, limitada a reglas meta.
- Eficiencia: usar la batería inmutable `experiments/fixed_latency.py` con 100 000 hechos, tres valores de `PYTHONHASHSEED`, p50/p95, RAM y puertas de `prereg/performance-1-latencia.md`.
- Última ARC-AGI pública comprobada el 2026-09-22: [ARC-AGI-3](https://arcprize.org/arc-agi/3), interactiva. Sus juegos públicos serán la batería fija de seguimiento; si Leobot no tiene interfaz para leer marcos y elegir acciones, registrar **no evaluado**, nunca cero inventado. [ARC-AGI-2](https://github.com/arcprize/ARC-AGI-2) es una batería estática distinta y no sustituye a ARC-AGI-3.

## Comparación y actualización

Solo se anota una cifra frontier cuando proceda de fuente primaria fechada y **de la misma batería y protocolo**. Si falta un lado, la brecha se marca no comparable. No inferir una brecha numérica desde conjuntos distintos. El obstáculo principal se elige de resultados medidos y capacidades aún inaccesibles; se explica la incertidumbre. En futuros tags se reutilizan los mismos 20 identificadores de MLQA y la misma batería de latencia. El tablero se genera fuera de `leobot/` y el motor no lee respuestas oficiales. No se modificarán selección ni criterios tras ver el primer resultado sin otro preregistro.
