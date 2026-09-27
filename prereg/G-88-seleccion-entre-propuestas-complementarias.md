# G-88 — selección entre propuestas complementarias aprendidas

2026-09-27. Antes de código. Motor estable `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## En palabras fáciles de entender

Ya comprobamos que las asociaciones aprendidas pueden encontrar algunas
respuestas que quedan fuera de la primera lista. Ahora comprobaremos si Leobot
aprende a elegirlas y cuándo debe callar. Ampliar la lista también puede aumentar
los errores: por eso compararemos las respuestas reales, no solo la presencia
de una solución. No habrá reglas sobre negocios ni respuestas preparadas.

## Hipótesis y alcance

G-87 pasó su puerta descriptiva: 627/816 soluciones en seis propuestas actuales,
673 al sumar seis propuestas por alineación. Doce propuestas actuales cubren
también 673, con veinte casos exclusivos de cada lista. La hipótesis es que la
complementariedad aprendida ayuda al selector, manteniendo la prudencia; la
alternativa es que basta ampliar la lista actual o que las nuevas candidatas
solo añaden ruido. No usar las veinte claves para elegir o enseñar nada.

Reutiliza G-65/G-84 como proponente y PAR-2 como selector; no es un subsistema
nuevo. G-65 mezclaba puntajes y G-84 solo seleccionaba dentro de seis unidades
anteriores. Aquí cambia el conjunto que recibe el mismo aprendiz. Si funciona
reemplazaría esa limitación de seis, sin mantener rutas competidoras redundantes.
Antecedentes científicos y sus límites en G-84/G-86/G-87; no se atribuye a los
artículos el resultado de esta combinación. Los estudios de alineación de
[ACL 2023](https://aclanthology.org/2023.acl-long.219.pdf) usan BERT y advierten
sobre enlaces nulos/múltiples. El trabajo de [agosto de 2026](https://arxiv.org/html/2608.15804v1)
obtiene F1 14,9 de detección de invenciones en QA con OTAlign, con representaciones
neuronales. No se adoptan ni se trata correspondencia léxica como prueba de verdad.

## Diseño fijo

Base y tablas G-84 directo, mismos SHA de G-87. No reenseñar asociaciones.
Cuatro variantes, sin selección de hiperparámetros:

1. **Seis:** referencia G-84 directo sin cambio, K=6.
2. **Doce:** primeras doce unidades de `_scored` actual, K=12.
3. **Unión (principal):** seis iniciales más seis por alineación G-65 directa,
   exactamente `g87.proposed`; deduplicar, sin completar huecos, K máximo 12.
4. **Confundida:** mismo algoritmo de unión, pero permutar con semilla 1 las
   columnas de respuesta al calcular el puntaje que propone nuevas unidades.

Las propuestas adicionales excluyen pregunta/encabezado. Las primeras seis
permanecen en el mismo orden; nuevas unidades siguen el orden de alineación.
Conservar para cada candidata el puntaje `_scored` original, o su base si no
recibió ganancia. No inventar coincidencias para incorporarla. Las variables
siguen siendo las 33 de G-84 directo; `rango` ahora puede ser 7–12, valor que
recibe su peso de los ejemplos. El resto de la selección no cambia.

En la variante confundida solo cambia quién propone; las 33 variables que
evalúan cada candidata conservan su significado real. Preparar permutación
por contexto. En todas: cargar contexto prepara las tablas, la pregunta se
procesa en cada respuesta y no se guardan preguntas. La nueva propuesta se
calcula también en inferencia y su costo cuenta, incluso si repite operaciones.

Enseñanza: TRAIN G-68, mismos negocios, etiquetas y división cruzada en mitades.
Modificar solo el K que consume `training_turns`, no su criterio de etiquetado.
Reajustar regresión y calibración con empates G-68, umbral 0,4, para cada
variante. G-84/MFAQ siguen siendo conocimiento previo, no adquisición gratuita:
su costo histórico permanece registrado; aquí se mide reutilización y ajuste.

## Puertas y controles

Evaluar una vez mediante `Bot.answer` en DEV G-62/G-63/G-64 gastado. Principal:
≥344/816 útiles, ≤73/488 citas sin dato, ≥499/816 elecciones correctas antes
de abstención, y ≥17 útiles sobre **cada** control. Literalidad de evidencia,
restauración exacta de la base y de G-84 directo, recarga/hashseed 1 idéntica;
base compacta ≤100 MiB. p95 y máximo <5 ms. No elegir el mejor control como
principal después de leer DEV; todos los resultados se conservan.

Focales: no perder las seis iniciales, no duplicar, conservar puntajes originales,
recambio de documento y desactivación. Bot sin nuevo aprendizaje cubierto por
seis; misma información/presupuesto por doce; señal confundida explícita; no hay
memoria de respuestas. Renombrado, documentos incompatibles, reserva/juez y
auditor 5.10 requieren integración congelada tras pasar desarrollo. No se
promueve por el caso del usuario ni por la disponibilidad que midió G-87.

## Costo y ejecución

Enseñanza ≤600 s CPU, evaluación/controles ≤240 s, total ≤840 s, pared ≤1 100 s,
RAM conjunta ≤1 GiB. Un proceso pesado. Registrar preparación, ajuste, evaluación,
guardado, compactación y recarga; puntos de recuperación y fallos. Fuente de
propuestas y huellas verificadas; no descargas. Trece rápidas y focales antes
de `freeze-G88-prototipo`, preregistro con commit antes de código. Resultados
en `results_v3/g88_complementary_proposals.json`. Motor/base intactos mientras
sea prototipo; PAR-6 ajeno cerrado. No ampliar K ni mover puertas tras medir.
