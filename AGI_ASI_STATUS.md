# Estado respecto a AGI / ASI

## Resultado actual

**AGI demostrada: NO**  
**ASI demostrada: NO**

La V3.9 conserva las capacidades anteriores y añade habilidades iterativas, formación grounded de conceptos y predicados auxiliares inventados/reutilizables, pero las pruebas no justifican llamar al sistema AGI.

## Evidencia positiva

- aprende programas aritméticos a partir de ejemplos;
- aprende relaciones compuestas y clausuras;
- reutiliza habilidades previas como abstracciones;
- una habilidad puede servir para aprender otra bajo menor presupuesto de búsqueda;
- puede mantener 10.000 niveles de dependencia sin expansión exponencial;
- descubre factorial y Fibonacci dentro de un espacio recursivo general;
- puede seleccionar conocimiento relevante frente a grandes cantidades de información irrelevante cuando dispone de índices/contexto;
- puede recombinar algunas equivalencias lingüísticas aprendidas;
- puede inducir ciertas construcciones lingüísticas sin frame manual mediante hechos grounding y evidencia contrastiva;
- puede resolver ambigüedad semántica por intersección de episodios cuando una hipótesis común sobrevive;
- conserva trazabilidad y se abstiene cuando el espacio de hipótesis no permite una conclusión.
- induce macros parametrizadas de planes independientes y las transfiere a entidades/estados nuevos;
- usa esas macros para reducir profundidad y nodos de búsqueda en la batería interna;
- invalida automáticamente una macro cuando cambia un operador del que depende.

## Evidencia que falta

Una afirmación seria de AGI requeriría, como mínimo, demostrar de forma independiente y fuera de distribución que el sistema puede:

1. interpretar lenguaje natural abierto más allá de relaciones que pueden anclarse a hechos ya estructurados;
2. aprender nuevas representaciones y primitivas cuando el DSL actual no basta;
3. transferir estrategias entre dominios cualitativamente diferentes sin intervención específica del desarrollador;
4. planificar y corregirse en tareas largas y abiertas;
5. adquirir conocimiento de grandes documentos sin anotación manual y usarlo con comprensión contextual;
6. seleccionar autónomamente objetivos, subproblemas y fuentes de evidencia;
7. mantener estas propiedades al aumentar órdenes de magnitud de conocimiento y duración de interacción;
8. superar baterías externas amplias evitando contaminación del entrenamiento y hardcodeo de benchmarks.

ASI exigiría además evidencia de capacidad general significativamente superior a la humana en una gama amplia de dominios. Nada de las pruebas actuales establece eso.

## Hipótesis de investigación que sí queda fortalecida

La V3 ofrece evidencia para una hipótesis más acotada:

> un sistema no neuronal puede aumentar su capacidad mediante adquisición de hechos, inducción de procedimientos, descubrimiento de recurrencias, formación de abstracciones reutilizables e indexación selectiva, sin que toda nueva capacidad requiera una respuesta escrita a mano.

El siguiente cuello de botella principal ya no es únicamente velocidad o memoria. Es **representación abierta**: permitir que el sistema proponga y valide nuevas primitivas, conceptos y gramáticas cuando sus DSL actuales resultan insuficientes.


## V3.2 — evidencia adicional, no AGI

Se añadió adquisición de procedimientos sin frame manual a partir de cambios observables. En la evaluación interna congelada:

- parámetro lingüístico no visto: 200/200 frente a 0/200 del control episódico;
- transformación vectorial no vista: 200/200 frente a 0/200 del control episódico;
- adquisición compuesta con experiencia previa: 200/200;
- misma experiencia previa con reutilización desactivada: 0/200;
- sin experiencia previa: 0/200.

La tarea compuesta fue encontrada con una habilidad previa bajo un espacio de búsqueda de tamaño 3; sin reutilización, ese mismo espacio no podía expresar la solución. Esto demuestra transferencia dentro del DSL y presupuesto definidos. No demuestra capacidad general, comprensión abierta ni ASI.

Límites nuevos visibles: la frase procedural sigue agrupándose principalmente por su construcción superficial normalizada; paráfrasis no groundedas no se entienden automáticamente. Los estados son enteros pequeños y el DSL de ejecución sigue acotado.

## V3.3 — planificación adquirida, todavía no general

La evidencia nueva muestra una cadena más larga de adquisición:

```text
transiciones observadas
→ procedimientos ejecutables
→ equivalencias de superficie por significado operativo
→ paráfrasis procedurales nuevas
→ composición de secuencias
→ objetivo natural grounded
→ selección/simulación de acciones
→ plan hacia un estado nuevo
```

En la batería interna V3.3: paráfrasis 200/200 frente a 0/200 del control exacto; secuencias de 2 y 3 pasos 200/200 frente a 0/200 de las ablaciones relevantes; planificación 200/200 en objetivos generados por acciones aprendidas; y ruta natural de objetivo calculado 200/200 frente a 0/200 sin grounding del objetivo.

Esto fortalece la hipótesis de aprendizaje acumulativo, pero no satisface AGI. El planner opera sobre tuples enteros, usa BFS acotado, solo enumera automáticamente acciones sin parámetros, y no induce todavía operadores sobre estados simbólicos heterogéneos ni planes abiertos largos. Las cinco peticiones generales abiertas del benchmark base siguen sin interpretarse.

## V3.4–V3.5 — avance y límite

La evidencia nueva supera la etapa puramente numérica: Leobot induce operadores parametrizados sobre relaciones heterogéneas, compone dos operadores para alcanzar un objetivo textual nuevo y puede reutilizar un operador adquirido para reducir la cantidad de experiencias necesaria al aprender otra formulación con roles reordenados.

Esto satisface una propiedad de aprendizaje acumulativo local, pero no basta para AGI. El vocabulario de predicados del mundo sigue explícito, el planner es búsqueda acotada, las evaluaciones son internas y las tareas abiertas de lenguaje/creación siguen muy por debajo de un LLM de frontera. ASI exigiría superioridad amplia y reproducible en dominios variados y nuevos; no existe esa evidencia.


## V3.6 — evidencia jerárquica, todavía no inteligencia general

La evidencia nueva muestra una propiedad local de abstracción de experiencia: planes correctos repetidos pueden convertirse en habilidades parametrizadas que después reducen el coste de resolver problemas estructuralmente equivalentes con entidades nuevas. En 200 mundos held-out la versión jerárquica resolvió 200/200 bajo un presupuesto de profundidad donde el control primitivo resolvió 0/200; con profundidad suficiente para ambos, la mediana de nodos fue 2 frente a 23.

Además, una cadena de 256 instancias de la habilidad (1.024 primitivas equivalentes) se ejecutó con 256 expansiones jerárquicas. Este resultado prueba compresión de búsqueda en esa familia, no crecimiento cognitivo ilimitado.

Persisten obstáculos incompatibles con una afirmación de AGI: lenguaje abierto general, creación/explicación de contenido comparable a un LLM, aprendizaje de representaciones completamente nuevas, transferencia entre dominios no preparados, macros de longitud variable/recursivas, aprendizaje desde documentos brutos y evaluación externa independiente. ASI permanece todavía mucho más lejos.

## Actualización V3.8–V3.9

Hay evidencia interna adicional de **formación de representación acumulativa**: una superficie natural puede originar un predicado opaco, ese predicado puede convertirse en primitiva y V3.9 puede incluso inventar un auxiliar intermedio cuando el objetivo no cabe en el presupuesto directo. El auxiliar puede transferir a una tarea distinta después de reiniciar.

Esto no cambia el veredicto: **AGI no demostrada; ASI no demostrada**. La representación sigue siendo binaria, depende de conocimiento estructurado previo y opera en DSLs explícitos. El lenguaje natural abierto y las tareas de dominio verdaderamente abierto continúan pendientes.
