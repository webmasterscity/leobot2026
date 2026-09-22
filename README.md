# Leobot Lab V3.9 — arquitectura no neuronal escalable

Leobot V3.9 es un laboratorio experimental en Python para aprender y reutilizar conocimiento sin redes neuronales, LLM ni GPU en el camino de respuesta. La V3 corrige varios cuellos de botella encontrados en V2: expansión exponencial de habilidades, selección de conocimiento irrelevante, profundidad recursiva, memoria factual ligada a RAM y falta de algoritmos recursivos simples.

**No es una demostración de AGI ni ASI.** Es una base experimental que permite probar hipótesis de crecimiento acumulativo de capacidad con trazabilidad completa.

## Qué cambió en V3

- **Habilidades como DAG de referencias.** Una habilidad aprendida puede llamar a otra mediante `@habilidad` sin copiar su árbol. Miles de capas no expanden el programa exponencialmente.
- **Invalidación transitiva.** Si cambia una habilidad base, se invalidan automáticamente todas las habilidades que dependían de ella.
- **Enrutamiento automático de conocimiento.** Las relaciones usan un índice entidad→predicado; las habilidades numéricas pueden usar un índice concepto→habilidad. El fallback sin contexto sigue existiendo y se reporta explícitamente.
- **Síntesis de recurrencias.** Aprende esquemas recursivos generales dentro de un DSL acotado. En las pruebas descubre factorial y Fibonacci a partir de ejemplos, sin casos especiales por nombre.
- **Cierre transitivo compilado.** Las consultas de alcance aprendidas se ejecutan por BFS indexado en lugar de depender de recursión profunda de Python.
- **Lenguaje composicional + grounding contrastivo.** Puede inducir construcciones a partir de hechos ya conocidos sin recibir un frame semántico manual en cada episodio. Mantiene un espacio de hipótesis, exige apoyos independientes antes de activar una construcción, aprende negaciones explícitas y reutiliza equivalencias léxicas entre afirmaciones y preguntas.
- **Memoria SQLite opcional.** Los hechos masivos pueden vivir en disco con índices posicionales y entidad→predicado. El estado pequeño de lenguaje, reglas y habilidades queda en un sidecar JSON.
- **Jerarquías aprendidas de planes.** V3.6 abstrae trazas primitivas verificadas en macros parametrizadas, mantiene dependencias sobre los operadores base, invalida macros obsoletas y usa un rollout jerárquico conservador con fallback al planner completo.
- **Joins adaptativos.** Las precondiciones se ordenan según selectividad bajo los bindings actuales, evitando cruces cuadráticos cuando una relación grande queda filtrada por roles ya ligados.
- **Sin dependencias de terceros.** Python 3.10+; las mediciones incluidas se hicieron con Python 3.13.5.

## Inicio rápido

### Modo simple en memoria

```bash
python -m leobot --state memoria.json --load examples/curso_inicial.json
```

### Modo escalable en disco

```bash
python -m leobot \
  --db memoria_factual.db \
  --state estado_cognitivo.json \
  --load examples/curso_inicial.json
```

En modo `--db`, los hechos no se serializan dentro del JSON. SQLite conserva la memoria factual; `estado_cognitivo.json` conserva lenguaje, reglas aprendidas, programas y trazas de entrenamiento.

Una consulta de una sola vez:

```bash
python -m leobot \
  --db memoria_factual.db \
  --state estado_cognitivo.json \
  --ask "Calcula doble de 9."
```

## Etiquetas conceptuales para bibliotecas muy grandes

Los ejemplos numéricos pueden incluir `concepts`:

```json
{
  "skill": "total_pedido",
  "inputs": [3, 20, 5],
  "output": 65,
  "concepts": ["comercio", "precio", "pedido"]
}
```

Las etiquetas no contienen la respuesta. Funcionan como un índice semántico para evitar revisar una biblioteca completa de habilidades cuando el problema ya aporta contexto relevante.

Si no hay conceptos, el sistema usa un fallback exhaustivo sobre habilidades de aridad compatible. Ese fallback es correcto para bibliotecas pequeñas, pero su coste crece con la cantidad de habilidades y se registra como `fallback_scan`.

## Resultados reproducibles de esta versión

Ejecuta:

```bash
python -m unittest discover -s tests -v
python v3_experiment.py
python v31_grounding_experiment.py
python v32_procedure_grounding_experiment.py
python v33_procedure_composition_experiment.py
python v34_symbolic_world_experiment.py
python v35_symbolic_alias_experiment.py
python v36_hierarchical_skills_experiment.py
```

Resultados obtenidos en la ejecución incluida:

- **117/117 pruebas automatizadas aprobadas.**
- DAG de **10.000 capas**: respuesta correcta; representación superior de 12 caracteres (`(@s9999 + 1)`) y ~25,7 ms para evaluar toda la cadena en la máquina de prueba.
- **50.000 habilidades irrelevantes** con índice conceptual: se recuperaron 2 candidatas, se seleccionó la habilidad útil y el aprendizaje tardó ~2,2 ms.
- **5.000 predicados irrelevantes**: el índice entidad→predicado seleccionó solo `signal`; aprendizaje ~0,40 ms.
- Cierre transitivo sobre **20.000 nodos**: correcto, 19.999 aristas visitadas, ~314 ms.
- SQLite con **200.000 hechos**: 500/500 consultas correctas; mediana ~0,051 ms y p95 ~0,070 ms para consultas puntuales indexadas.
- Factorial descubierto como `f(n)=n*f(n-1)`; `f(8)=40320`.
- Fibonacci descubierto como `f(n)=f(n-1)+f(n-2)`; `f(12)=144`.
- También descubre una recurrencia con `f(n-3)` y Tribonacci sintetizando el cuerpo recursivo como otro programa.
- Combinaciones de paráfrasis no enseñadas: 3/3 interpretadas en la prueba composicional.
- Grounding sin frame manual: 3 construcciones promovidas tras apoyo independiente; 6/6 afirmaciones nuevas almacenadas y 6/6 consultas nuevas respondidas.
- Grounding contrastivo: dos episodios individualmente ambiguos `{vive, trabaja}` y `{vive, posee}` se intersectan en `vive`; la ablación que descarta episodios ambiguos no aprende ni transfiere.
- Control de coincidencia: una sola correlación accidental queda pendiente y no se transfiere; la ablación de un solo apoyo sí reprodujo el falso aprendizaje.
- Jerarquía simbólica V3.6: 200/200 mundos nuevos con profundidad 2 frente a 0/200 del control primitivo; mediana 2 vs 23 nodos cuando ambos tienen profundidad suficiente.
- Horizonte V3.6: 256 macros equivalentes a 1.024 acciones primitivas, 256 nodos/transiciones (~34 ms en la corrida incluida).
- Peticiones realmente abiertas no enseñadas: **0/5 interpretadas**. Este fallo se conserva porque sigue siendo un límite real.

Consulta `RESULTADOS_V3.md` para interpretación y límites.

## Qué significa “escalable” aquí

No significa infinito. Significa que se eliminaron varios crecimientos innecesarios:

- el tamaño de una habilidad compuesta ya no duplica árboles previos;
- la profundidad de una cadena aprendida no depende de la pila recursiva de Python;
- la memoria factual puede superar la RAM porque vive en disco;
- la búsqueda relacional puede depender del vecindario relevante y no del número total de predicados;
- con contexto conceptual, la selección de habilidades puede depender del vecindario conceptual y no de toda la biblioteca.

Persisten costes inevitables: una consulta que realmente necesita recorrer N hechos sigue necesitando trabajo proporcional al subgrafo relevante; sin contexto semántico, encontrar una función arbitraria en una biblioteca arbitraria no puede asumirse gratuito.

## Límites actuales importantes

1. No comprende lenguaje natural abierto como un LLM de frontera.
2. El lenguaje ya puede adquirir algunas construcciones mediante grounding contrastivo, pero depende de que durante la adquisición existan entidades y hechos relevantes en memoria; todavía no equivale a comprensión abierta del español.
3. La síntesis recursiva aprende cuerpos sobre `n` y hasta `f(n-3)`; todavía no cubre programas recursivos arbitrarios. Una recurrencia genuina de orden 4 queda sin solución.
4. El índice conceptual de habilidades necesita contexto semántico; sin él existe un fallback lineal.
5. La memoria SQLite almacena hechos estructurados; cargar un libro bruto no implica comprenderlo automáticamente.
6. No hay todavía un mecanismo general para inventar cualquier nueva primitiva, crear sus propios objetivos, diseñar experimentos físicos o operar herramientas externas de manera autónoma.
7. Los benchmarks son internos y de dominios restringidos; no equivalen a una evaluación independiente de AGI.

## Archivos principales

- `leobot/core.py`: hechos, reglas, pruebas y motor lógico.
- `leobot/diskkb.py`: memoria factual SQLite.
- `leobot/learning.py`: inducción relacional y selección por relevancia.
- `leobot/programs.py`: síntesis aritmética, DAG de habilidades, recurrencias y routing conceptual.
- `leobot/language.py`: construcciones lingüísticas, especificidad de parseo y recombinación de paráfrasis.
- `leobot/bot.py`: grounding contrastivo, espacios de hipótesis y conversación.
- `leobot/scalable.py`: bot con memoria factual en disco.
- `tests/test_system.py`: regresión V1/V2.
- `tests/test_v3.py`: pruebas nuevas de escalabilidad y capacidades V3.
- `v3_experiment.py`: benchmark reproducible.
- `v31_grounding_experiment.py`: validación y ablaciones del aprendizaje lingüístico por grounding.
- `v32_procedure_grounding_experiment.py`: grounding y transferencia de procedimientos.
- `v33_procedure_composition_experiment.py`: paráfrasis procedurales, secuencias, planificación y objetivos.
- `v34_symbolic_world_experiment.py`: modelos de acción sobre hechos.
- `v35_symbolic_alias_experiment.py`: reutilización de operadores para adquirir lenguaje con menos experiencia.
- `v36_hierarchical_skills_experiment.py`: inducción de macros parametrizadas, profundidad, branching, invalidación y controles.
- `LEOBOT_STATE.md`: estado compacto para continuar el desarrollo.


## V3.2 — grounding de procedimientos observando cambios de estado

V3.2 añade `ProcedureGrounder`. La entrada de aprendizaje es una instrucción en español junto con un estado observable antes y después; no se proporciona un nombre de operación ni un frame semántico. La frase agrupa evidencia independiente y el significado ejecutable se sintetiza con `ProgramLearner`.

```python
from leobot import Bot
b = Bot()
for text, before, after in [
    ('Suma 3 al valor.', (10,), (13,)),
    ('Suma 5 al valor.', (7,), (12,)),
    ('Suma 8 al valor.', (-2,), (6,)),
]:
    print(b.observe_transition(text, before, after))
print(b.execute_transition('Suma 11 al valor.', (31,)))
# result == (42,)
```

Los enteros escritos en la instrucción se convierten en parámetros del programa (`Suma <n0> al valor`) y no en respuestas hardcodeadas. El backend actual admite estados enteros pequeños porque este ciclo evalúa adquisición y transferencia; no representa todavía objetos generales, texto libre, planes o acciones físicas.

La evaluación reproducible está en `v32_procedure_grounding_experiment.py` y `results_v3/v32_procedure_grounding.json`.


## V3.3 — paráfrasis procedurales, secuencias y planificación desde objetivos

V3.3 conserva V3.2 y añade tres mecanismos generales acotados:

- **equivalencia procedural aprendida:** dos superficies grounded independientemente pueden aportar sustituciones locales cuando sus programas canónicos y probes coinciden; esas sustituciones se recombinan en superficies nunca observadas;
- **composición secuencial:** una orden de varios pasos se simula paso a paso usando únicamente procedimientos ya adquiridos;
- **planificación desde objetivos:** BFS acotado selecciona procedimientos grounded sin parámetros para llegar a un estado objetivo. Un objetivo natural numérico puede aprenderse desde ejemplos sin frame manual y sintetizar expresiones sobre sus parámetros.

Ejemplo después de groundear las habilidades correspondientes:

```python
out = b.execute_transition(
    'Añade 11 a la cantidad y luego dobla el resultado.',
    (7,)
)
# out['result'] == (36,)

for text, goal in [
    ('Lleva el valor a 2 más que 5.', (7,)),
    ('Lleva el valor a 3 más que 8.', (11,)),
    ('Lleva el valor a 4 más que 10.', (14,)),
]:
    b.observe_goal(text, goal)

plan = b.plan_goal('Lleva el valor a 6 más que 9.', (1,), max_steps=6)
# objetivo resuelto == (15,), plan encontrado
```

La evaluación V3.3 está en `v33_procedure_composition_experiment.py`. Sus controles desactivan por separado reescrituras, secuencias, habilidades previas y grounding de objetivos.

**Límites de esta planificación:** el estado sigue siendo un tuple de 1–4 enteros; el planner autónomo excluye acciones con parámetros no instanciados; la gramática secuencial solo cubre conectores generales explícitos; y los objetivos naturales requieren construcciones grounded. No es planificación abierta comparable a un LLM/agente general.

## V3.4–V3.5 — estados factuales, operadores inducidos y transferencia de lenguaje

`leobot/symbolic.py` añade un experimento de aprendizaje de modelos de acción sobre conjuntos de hechos. La entrada de aprendizaje es texto natural + estado antes + estado después. No se proporciona un frame semántico ni un operador manual. V3.4 induce roles, efectos y precondiciones contrastivas; V3.5 reutiliza operadores anteriores para aprender con menos ejemplos formulaciones nuevas, incluso con orden diferente de argumentos.

Evaluación principal:

- V3.4: 200/200 planes held-out y 200/200 validados por un simulador de referencia independiente; memoria episódica 0/200; ablación sin contraejemplos 0/200.
- V3.5: alias reordenado de movimiento 200/200 y alias de recogida 200/200 con conocimiento previo; copia desde cero con las mismas dos experiencias 0/200 en ambos casos.
- Suite completa: 111/111.

Reproducir:

```bash
python3 -m unittest discover -s tests -v
python3 v34_symbolic_world_experiment.py
python3 v35_symbolic_alias_experiment.py
```

Estos resultados muestran transferencia dentro de un mundo simbólico explícito; no demuestran AGI ni comprensión abierta del español.


## V3.6 — habilidades jerárquicas aprendidas desde planes

V3.6 no recibe una macro `entregar` escrita por el desarrollador. `learn_symbolic_macro` primero resuelve el episodio con **solo operadores primitivos**, vuelve a ejecutar la traza para verificarla, reemplaza entidades concretas por roles y exige tres instancias independientes antes de promocionar la abstracción.

Una traza recurrente de cuatro acciones puede quedar representada como una macro parametrizada con precondiciones/efectos netos y, a la vez, conservar la secuencia primitiva expandible para auditoría. La macro guarda fingerprints de todos sus operadores base: si contraevidencia invalida uno, la macro deja de estar disponible.

El planner usa dos mejoras generales:

1. **joins adaptativos por binding**, que eligen la siguiente precondición por su selectividad real después de ligar variables;
2. **rollout jerárquico monotónico**, utilizado solo cuando una macro aplicable logra subobjetivos finales pendientes sin destruir los ya logrados y la mejor consecuencia es inequívoca. Ante empate o falta de progreso, vuelve al planner explícito completo.

En la evaluación congelada incluida: 200/200 mundos nuevos se resolvieron bajo profundidad jerárquica 2 frente a 0/200 del control primitivo con el mismo límite; con profundidad primitiva suficiente, la mediana fue 2 nodos con jerarquía frente a 23 sin ella. Una cadena de 256 entregas, equivalente a 1.024 acciones primitivas, se resolvió como 256 pasos jerárquicos y 256 transiciones en ~34 ms en esa corrida. Estos resultados son internos y estructurados; no demuestran planificación abierta ni AGI.

## V3.7 — habilidad iterativa de longitud variable

V3.7 aprende, a partir de planes del mismo operador con longitudes 2, 3 y 4, una habilidad iterativa compacta que transfiere a rutas más largas. En la evaluación interna resolvió 200/200 rutas held-out de longitud 5–64; el control primitivo y el control de macros fijas con profundidad 1 obtuvieron 0/200. Se midió hasta 5.000 pasos equivalentes. La habilidad depende del operador base y se invalida si este cambia.


## V3.8 — conceptos relacionales inventados desde lenguaje natural

V3.8 añade `ConceptGrounder`. Una superficie natural con dos entidades conocidas puede crear un predicado opaco nuevo sin que el desarrollador entregue su nombre semántico. Con evidencia positiva/negativa, el sistema intenta explicar ese concepto mediante relaciones existentes y puede reutilizar el resultado como una nueva primitiva. Una nueva formulación puede asociarse a un concepto previo si la evidencia contrastiva deja una sola hipótesis compatible; contraevidencia retira el alias.

El benchmark reproducible está en `v38_concept_invention_experiment.py` y `results_v3/v38_concept_invention.json`.

## V3.9 — invención acotada de predicados auxiliares

V3.9 añade una segunda capa: si un concepto no cabe en la profundidad relacional actual y la búsqueda terminó sin solución, el aprendiz puede crear un auxiliar binario corto sobre los predicados relevantes, volver a intentar el objetivo y conservar ese auxiliar solo si el objetivo aprendido depende de él. Los auxiliares de camino se ejecutan mediante composición compilada y caché transaccional.

En el benchmark V3.9, un objetivo equivalente a `r;s;r;s` no se resolvió con profundidad 2 sin invención; con invención se descubrió un auxiliar `r;s` y transfirió 100/100. Ese auxiliar sobrevivió un reinicio y permitió luego aprender `r;s;t` con profundidad 2 y nueva invención desactivada. La primera invención todavía tiene sobrecoste frente a una búsqueda directa más profunda, y se reporta explícitamente.

Reproducir:

```bash
python3 -m unittest discover -s tests -v
python3 v38_concept_invention_experiment.py
python3 v39_predicate_invention_experiment.py
```
