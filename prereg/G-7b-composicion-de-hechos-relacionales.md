# G-7b — composición de hechos relacionales

## Decisión que cambia el experimento

G-7 cubrió 51/51 rutas de unión **elegibles**, pero no filtros, columnas proyectadas, grupos, orden ni significado del español. Enumerar consultas SQL completas como producto cartesiano puede agotar 1 000 candidatos antes de llegar a la ruta útil. La [descomposición relacional de IJCAI 2025](https://www.ijcai.org/proceedings/2025/504) sugiere conservar hechos pequeños comprobables y combinarlos después; la [reutilización progresiva sin RL de IJCAI 2026](https://www.ijcai.org/proceedings/2026/564) respalda conservar fragmentos útiles. Son antecedentes, no evidencia para Leobot.

Hipótesis: una representación factorizada de ruta, proyección, filtro, grupo, orden y límite cubrirá una parte sustancial de preguntas reales con ≤1 000 **fragmentos propuestos** por pregunta, sin enumerar primero todos los productos. Alternativa: incluso los fragmentos del SQL gold no pueden generarse a partir del esquema y la pregunta, o la gramática excluye demasiado; entonces se detiene esta vía antes de construir un learner. Si funciona, sustituiría la enumeración monolítica de G-6 para consultas relacionales; no añadiría otro razonador.

## Datos y separación

Fuente y hashes de G-6: solo `train_es.json` y `tables_es.json` fijados. Ocho bases y semillas 17/53/97, cinco preguntas aleatorias por base según H0; estrato simple de G-6 se informa aparte y no decide éxito. El generador recibe únicamente pregunta española, nombres/tipos de tablas y columnas, claves foráneas y valores visibles de la base. SQL gold solo entra en el evaluador **después** de generar candidatos para clasificar cobertura. No abrir `dev_es` ni nuevas bases hasta congelar un mecanismo que supere desarrollo.

## Representación y controles

Programa declarativo como unión de ≤3 tablas por ≤2 claves foráneas; proyección de ≤3 columnas simples con agregación opcional; ≤2 filtros escalares de comparación/igualdad unidos por AND u OR; ≤2 columnas agrupadas; orden por ≤1 columna con dirección; límite numérico explícito o constante universal 1. Se admiten `DISTINCT` y `COUNT(*)`. Se excluyen subconsultas, conjuntos, HAVING, expresiones aritméticas y uniones externas; cada exclusión cuenta contra cobertura total. El generador debe proponer los fragmentos de cada ranura sin SQL gold. Un plan cuenta como representable si **todos** los fragmentos gold aparecen en sus ranuras y la forma completa cabe en la gramática; esto **no** cuenta como una consulta aprendida o ejecutada, ni afirma que se pueda resolver el producto de las ranuras bajo 1 000 planes. Registrar también ese límite de combinaciones estimado.

Tratamiento: rutas de G-7 más fragmentos tipados. Ablación: mismas entradas y límite, pero sin rutas conectadas por claves, con uniones planas de columnas de mismo tipo. Control sin texto: mismo esquema y valores; medir si los nombres de pregunta ayudan a ubicar los fragmentos gold. Control de renombrado total de símbolos: conservar relaciones e índices, cambiar etiquetas. Los controles fresca/memoria, contraevidencia, reinicio y confusor no aplican a esta puerta de representación sin aprendizaje; quedan obligatorios si se pasa a un learner.

## Puerta y costo

En cada semilla, al menos **20/40** preguntas aleatorias deben tener todos sus fragmentos gold dentro del límite de 1 000 propuestas, incluidas **8/40** multitabla. El tratamiento debe superar la ablación por ≥20 puntos porcentuales en cobertura de las 40. Informar separadamente: forma del SQL admitida, ruta, columna, operador, valor, combinación y efecto de texto; no convertir una ruta gold en éxito de consulta. Tres semillas, `PYTHONHASHSEED=0/1`, motor H0 idéntico antes/después. CPU ≤60 s, pared ≤120 s y RSS ≤256 MiB por ensayo; registrar lectura, propuestas, comparación, candidatos y ejemplos. Si falla, preservar resultado y cambiar la representación antes de codificar enseñanza. Si pasa, preregistrar un ensayo de denotaciones e intervenciones con controles completos, código congelado y bases nuevas derivadas del hash; solo entonces considerar integración en `leobot/` y medir p95.
