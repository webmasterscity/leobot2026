# Preregistro B-2 — conservar hipótesis rivales y pedir una prueba

Fecha: 2026-09-22. B-1 quedó registrado como fallo en `a228abb`; no se revisan sus límites ni sus reservas. Referencia: `freeze-B-1`, árbol `912790def147f8986b01ecee3574e6c59a67ee4a`.

## Fallo observado y alternativas

En las tres órdenes B-1, F1 y F2 dieron 128/128, pero una pista de magnitud invertida produjo 3–4 recomendaciones seguras falsas y 34,68–34,78 s de CPU. Un diagnóstico posterior con datos de desarrollo muestra una proyección de la posición 7 con exactitud 1,00 y cobertura 0,977; el plegado de signos también ajusta todos los 128 ejemplos, pero la búsqueda se detiene al hallar la proyección. La causa candidata es selección prematura de una única representación entre explicaciones indistinguibles. Alternativa sencilla: preferir siempre el plegado aprendido. Se rechaza como principio general porque una operación previa también puede ser espuria. La comparación decidirá si conservar ambas y pedir evidencia funciona mejor.

## Cambio mínimo y decisión de admisión

El controlador conservará como máximo dos vistas verificadas y estructuralmente distintas cuando ambas expliquen la misma experiencia: la vista existente y un operador compuesto que ya tenga una fuente independiente. La búsqueda adicional estará limitada a 32 candidatos y se ejecutará una sola vez por lote de evidencia; después habrá revalidación barata. Ante predicciones opuestas, no dará una recomendación segura. Con un conjunto de acciones sin etiquetas provisto por el entorno, propondrá la acción que más separe ambas hipótesis por unidad de costo. El entorno ejecutará la acción y entregará el resultado real por la interfaz ordinaria de observación. Una hipótesis contradicha por esa intervención se retirará; una intervención que contradiga el agregado retirará este y sus dependientes. Persistirán la ambigüedad, la decisión y la evidencia. No se aceptará por defecto la vista más antigua ni la de mayor complejidad.

Este cambio unifica la detección de duda y la elección de pruebas que ya existen en el MetaController con los operadores agregados B-1. Si funciona, elimina la preferencia implícita por la primera vista encontrada; no se retira otro learner.

## Familias, reserva y controles

Se repiten las familias F1/F2 y los órdenes 17, 53 y 97 de B-1 con una **nueva reserva**, generada solo después de `freeze-B-2` a partir de los primeros ocho dígitos de su árbol, más 0, 1 y 2. F1: 64 configuraciones de seis pares en adquisición, 128 casos reservados con centros y escalas nuevas. F2: 128 configuraciones de ocho valores con signos, 128 configuraciones reservadas; se transfiere el reductor de F1. Una pista de magnitud codificará la etiqueta en adquisición y se invertirá en la reserva. Además, habrá 16 acciones factibles sin etiqueta, con configuraciones de signos y magnitudes diversas; el motor elige una, el entorno devuelve su resultado por conteo real de signos. No se generan etiquetas dentro del motor.

Controles: B-1 congelado con la misma información y acciones; tratamiento sin intervención; tratamiento tras intervención; fresco; solo memoria; ablación del operador; estructura incompatible dependiente de magnitud máxima; inversión del confusor; renombrado total; contraevidencia que invalida agregado y dependientes; guardar/cerrar/cargar antes y después de la intervención. Se distinguirá ahorro de candidatos de ahorro de CPU total. Se medirá también si el controlador pide una prueba cuando los rivales coinciden en todos los ejemplos observados.

## Métricas y umbral fijo

Para promover: F1/F2 ≥90 % (≥116/128) en cada orden; ablación F1 ≤75 % (≤96/128) o cinco veces más candidatos; F2 educado menos candidatos o menos ejemplos que fresco; cero errores seguros antes de la intervención confundida; propuesta con ganancia de información positiva y observación real; después de **una** intervención, ≥90 % en la reserva confundida y cero errores seguros; contraevidencia y reinicio retiran dependientes; renombrado y estructura incompatible pasan. Cada variante **del tratamiento** y orden ≤30 s de CPU y ≤256 MiB; los controles heredados se miden con igual tiempo máximo, pero un control que agote el presupuesto no invalida una mejora del tratamiento. `timeout 180s` por orden; máximo 32 programas por búsqueda. No se cambia el límite de profundidad. Se registran ejemplos, candidatos, CPU de adquisición, búsqueda, verificación, consolidación e inferencia, RAM, inicio en frío, guardado y carga. La puerta fija de latencia debe pasar antes de un tag estable.

Refutación: si dos hipótesis sobreviven pero el sistema elige una en silencio; si la pregunta no discrimina; si el entorno debe traducir o reparar la respuesta; si hay errores seguros tras invertir la pista; o si el costo excede el presupuesto, B-2 no se promueve aunque F1/F2 acierten.
