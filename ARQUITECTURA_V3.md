# Arquitectura V3.9

## Flujo cognitivo

```text
entrada
  │
  ├─ lenguaje aprendido: construcciones + grounding contrastivo + paráfrasis
  │
  ├─ frame semántico
  │    │
  │    ├─ consulta factual → índices / SQLite → motor lógico
  │    ├─ relación nueva → router entidad→predicado → inducción relacional
  │    └─ cálculo → router concepto→habilidad → síntesis / recurrencia
  │
  ├─ habilidades aprendidas como DAG
  │    └─ llamadas @habilidad + memoización
  │
  └─ respuesta + prueba / procedencia
```

## Complejidad buscada

| Componente | V2 | V3 |
|---|---|---|
| Composición profunda de habilidades | expansión de árboles | referencias compartidas / DAG |
| Evaluación de miles de capas | recursión potencial | recorrido iterativo + memo |
| Predicados irrelevantes | podía enumerar todos | índice entidad→predicado |
| Habilidades irrelevantes | escaneo completo | índice concepto→habilidad cuando existe contexto |
| Hechos masivos | objetos Python + JSON | SQLite indexado |
| Cierre transitivo largo | fixed-point recursivo | BFS compilado para patrón reconocido |
| Secuencias recursivas | fuera del DSL | síntesis de recurrencias acotadas |
| Paráfrasis | construcción exacta | recombinación de sustituciones aprendidas |
| Semántica de frases nuevas | frame manual | version-space grounding con hechos y apoyos independientes |
| Equivalencias léxicas | por esquema exacto | reutilización por predicado entre actos comunicativos |
| Planes largos repetidos | BFS primitivo | macros parametrizadas + rollout jerárquico con fallback |
| Join de precondiciones | orden global | selección adaptativa según bindings actuales |

## Invariantes de diseño

1. Ninguna respuesta temática está escrita a mano.
2. Toda hipótesis aprendida puede rastrearse a ejemplos y una representación ejecutable.
3. La ausencia de evidencia no se convierte automáticamente en falsedad.
4. Las contradicciones se conservan y se reportan.
5. Cambiar una habilidad invalida sus dependientes.
6. Un límite de presupuesto produce `incomplete/no_solution`, no una respuesta inventada.
7. Los índices reducen búsqueda, pero no cambian la semántica de la conclusión.

## Escalabilidad factual

SQLite usa:

- índice por predicado;
- índice `(predicado, argumento_i)`;
- tabla invertida `(entidad, predicado)`;
- clave BLAKE2 para deduplicación rápida.

La consulta `pred(entidad, ?x)` puede usar índices sin recorrer todos los hechos. Una consulta `pred(?x, ?y)` que pide toda una relación sigue siendo proporcional a la cantidad de resultados: esa carga no puede eliminarse mediante indexación.

## Escalabilidad de habilidades

Una habilidad compuesta almacena referencias:

```text
base = (x0 * x1) + x2
doble = @base + @base
cuadruple = @doble + @doble
```

Cada nivel mantiene una representación pequeña. La ejecución construye el orden de dependencias iterativamente y memoriza cada `(habilidad, argumentos)` durante la evaluación.

La recuperación tiene dos modos:

- `concept_index`: usa metadatos conceptuales para recuperar un vecindario pequeño;
- `fallback_scan`: examina la biblioteca compatible cuando no existe contexto.

El segundo modo es deliberadamente visible porque no escala a bibliotecas arbitrariamente grandes.

## Síntesis recursiva

El meta-sintetizador convierte una secuencia en ejemplos derivados. Para un retardo 3, por ejemplo, intenta aprender un cuerpo ordinario:

```text
body(n, f(n-1), f(n-2), f(n-3)) -> f(n)
```

Ese cuerpo se sintetiza con el mismo DSL aritmético general. Así descubrió factorial, Fibonacci, una recurrencia con `f(n-3)` y Tribonacci sin ramas especiales por nombre. El retardo máximo actual es 3; una recurrencia genuina de orden 4 sirve como control negativo.

Esto amplía el espacio de programas, pero no equivale a descubrir cualquier algoritmo computable.


## Grounding contrastivo V3.1

Cuando una frase no está reconocida, Leobot no asigna un significado por coincidencia de palabras. Recupera hechos que contienen las entidades mencionadas y construye candidatos semánticos auditables. La superficie se delexicaliza y cada episodio aporta un conjunto de hipótesis.

```text
episodio A -> {vive, trabaja}
episodio B -> {vive, posee}
intersección -> {vive}
```

La construcción entra en la gramática activa solo cuando queda una hipótesis y existen al menos dos apoyos independientes. Repetir el mismo hecho no aumenta el apoyo. Esta regla redujo un fallo observado donde una única coincidencia podía enseñar erróneamente que «odia» significaba `trabaja`.

El mecanismo admite hechos explícitamente negativos (`!pred`) y conserva hipótesis pendientes a través de reinicios, incluido el backend SQLite. Aun así, dos correlaciones accidentales repetidas podrían engañarlo; el mecanismo reduce riesgo, no demuestra grounding semántico perfecto.

La selección de parseo también favorece construcciones que explican más palabras mediante estructura fija. Esto evita que una construcción positiva genérica absorba modificadores adicionales dentro de un slot cuando existe una construcción más específica.

## V3.2: significado operativo desde transiciones

`leobot/procedures.py` introduce un grounding procedural auditable:

`instrucción natural + estado antes + estado después -> programa explícito`.

No existe tabla `frase -> operación` preparada. Una construcción de superficie reúne episodios independientes; cada coordenada del estado final se sintetiza como programa sobre el estado inicial y, cuando existen, parámetros numéricos mencionados por la instrucción. Las habilidades adquiridas entran en la misma biblioteca composicional de `ProgramLearner`, por lo que pueden reducir la búsqueda de procedimientos posteriores.

La representación actual es un tuple de 1–4 enteros contando parámetros lingüísticos. Es una restricción experimental explícita, no una representación general del mundo.

## V3.3: equivalencia procedural y planificación acotada

Las superficies procedurales promovidas reciben una familia semántica conservadora basada en: (1) forma del estado y parámetros, (2) programa ejecutable canonizado para conmutatividad y llamadas directas, y (3) comportamiento en probes fijos sin etiquetas del benchmark. Solo dentro de una misma familia se extraen sustituciones locales de superficie. Las sustituciones no pueden reescribir placeholders numéricos.

```text
Suma <n> al valor ──┐
Añade <n> al valor ─┼─ mismo procedimiento → suma ↔ añade
Suma <n> a la cantidad ─ mismo procedimiento → al valor ↔ a la cantidad
                                           │
                                           └→ Añade <n> a la cantidad (no observada)
```

El ejecutor prueba primero la frase completa. Solo si no existe evidencia específica para ella intenta composición secuencial. Esto evita convertir una hipótesis completa no resuelta en un éxito artificial mediante fragmentación.

El planner V3.3 es BFS con límites de profundidad y nodos. Sus operadores son procedimientos realmente promoted, no funciones escritas específicamente para el objetivo. Alias de una misma familia se deduplican para no inflar el branching factor. Por ahora solo se enumeran automáticamente operadores sin parámetros lingüísticos; proponer parámetros de forma general queda pendiente.

Los objetivos naturales usan el mismo `ProgramLearner`: los números de la frase son entradas y cada coordenada del objetivo es una salida sintetizada. Así puede aprender, por ejemplo, que `A más que B` corresponde a `A+B` dentro de ese patrón sin una rama llamada `mas_que`.

## V3.4: inducción de modelos de acción desde cambios factuales

`SymbolicWorldLearner` delexicaliza entidades mencionadas, compara estados antes/después y conserva esquemas de hechos. Los efectos se obtienen de diferencias; las precondiciones candidatas proceden de la intersección de éxitos. Intentos sin cambio generan restricciones contrastivas y se busca un hitting-set mínimo único dentro de un presupuesto. Si hay ambigüedad, el modelo no elige arbitrariamente.

El planner usa los operadores promoted como esquemas parametrizados. Las variables se ligan por joins sobre precondiciones, no enumerando todas las combinaciones cuando las precondiciones bastan. Predicados nunca modificados por operadores se tratan como estáticos durante BFS; solo el componente dinámico forma la clave de estados visitados.

Esta familia tiene antecedentes claros en action-model learning (ARMS, LOCM y aprendizaje STRIPS como planificación). La contribución experimental aquí no se considera una prueba de novedad; se está probando si su integración con grounding textual contrastivo y aprendizaje acumulativo sirve como sustrato más general.

## V3.5: aliases semánticos con reasignación de roles

Una nueva formulación no necesita reaprender un operador completo si un operador anterior ya explica sus transiciones. Leobot prueba biyecciones acotadas entre los roles textuales de la nueva superficie y las variables del operador conocido. Una hipótesis solo sobrevive si reproduce exactamente el estado posterior; la intersección de episodios independientes reduce el espacio. Al quedar una hipótesis con apoyo suficiente, se guarda un alias `superficie -> operador + mapa_de_roles`.

Esto permite que el conocimiento adquirido reduzca la cantidad de experiencia necesaria para adquirir una formulación sintácticamente diferente. El mecanismo se invalida ante contraevidencia posterior.


## V3.6: capa jerárquica sobre operadores simbólicos

Cada macro se aprende de trazas primitivas ya verificadas. La canonicalización asigna roles `<eN>` por relaciones de identidad entre bindings del plan, de modo que la instancia concreta no se conserva como solución. La composición calcula precondiciones iniciales y efectos netos, pero la macro también conserva la secuencia original para poder expandirla y auditarla.

```text
planes primitivos independientes
        ↓ canonicalización de roles
misma estructura paramétrica
        ↓ soporte mínimo
macro
 ├─ precondiciones
 ├─ efectos netos / subobjetivos
 ├─ secuencia primitiva expandible
 └─ fingerprints de dependencias
```

La planificación jerárquica tiene dos rutas:

- **rollout monotónico rápido:** solo cuando una consecuencia macro logra al menos un objetivo pendiente, no destruye objetivos ya satisfechos y existe un efecto mejor inequívoco;
- **búsqueda explícita fallback:** ante ambigüedad, falta de progreso o ausencia de macro aplicable se conserva el planner completo con primitivas y macros.

El índice mutable del rollout mantiene hashes por predicado/aridad y por posición de argumento. Los joins se reordenan después de cada binding según el número real de candidatos, evitando elegir una tabla aparentemente pequeña que produzca un producto cartesiano innecesario.

Esto comprime profundidad, pero no constituye una solución general a planificación: las macros son secuencias fijas, los objetivos negativos no están modelados de forma general y estados enormes siguen teniendo coste de ingestión/materialización.

## V3.8–V3.9: formación e invención de representación relacional

La ruta conceptual nueva es:

```text
texto natural con entidades conocidas
        ↓
superficie deslexicalizada + polaridad
        ↓
predicado opaco concept_*
        ↓
ejemplos contrastivos
        ↓
inducción relacional
        ↓
concepto ejecutable y trazable
```

Si la definición no cabe en el presupuesto y la búsqueda directa fue completa:

```text
predicados relevantes
        ↓
composiciones auxiliares acotadas
        ↓
predicado invent_* temporal
        ↓
reintento del objetivo
        ↓
se conserva solo si el objetivo depende de él
```

Los predicados inventados son reglas explícitas, no embeddings. El recuperador expande un vecindario relacional local para encontrar predicados intermedios y las reglas de camino se compilan como composiciones de extensiones. El mecanismo sigue restringido a relaciones binarias y un DSL acotado; no constituye representación abierta general.
