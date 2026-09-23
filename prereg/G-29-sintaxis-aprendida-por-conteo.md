# G-29 — clases de palabras y dependencias sintácticas aprendidas por conteo

Fecha: 2026-09-23. Preregistro previo al código. Base: motor de `freeze-G-28b` (`2b285c28`). Último estable: `estable-G-2`.

## Por qué

[CMP-1](cmp-1-leobot-frente-a-subagente.md) mostró que un subagente Claude lee muy por encima de Leobot (MLQA F1 0,77). G-28/G-28b dieron a Leobot memoria de lo leído y respuesta por alineación, pero la [curva de educación](../results_v3/g28b_learning_curve_dev.json) sube solo ~0,011 F1 por duplicación de ejemplos: es un «no pudo». El motor compara palabras sueltas; no sabe qué palabra depende de cuál. Sin estructura no puede alinear «Berners-Lee escribió Weaving the Web» con «¿Qué libro escribió Berners-Lee?» más allá del orden, ni distinguir el sujeto del objeto. G-23–G-25 usaron árboles **dados** por el corpus; ninguna pieza del motor aprende a producirlos.

## Hipótesis y alternativa

Un etiquetador de clases de palabras (modelo oculto de Markov de trigramas con modelo de sufijos para palabras desconocidas, como TnT: [Brants, 2000](https://aclanthology.org/A00-1031.pdf)) y un analizador de dependencias por arcos con puntajes de conteo y decodificación proyectiva de Eisner ([Eisner, 1996](https://aclanthology.org/C96-1058.pdf)), aprendidos **solo contando** sobre oraciones anotadas —sin redes, perceptrones ni gradientes—, dan a Leobot árboles útiles de oraciones nuevas. Alternativa: con conteos y rasgos simples la precisión queda cerca de las líneas base triviales, o el costo de CPU/RAM no cabe en un procesador común.

## Mecanismo (5.8)

- **Fallo que resuelve:** Leobot no puede representar la estructura de una oración que no le enseñaron.
- **Por qué no bastan los actuales:** construcciones y raíces crudas necesitan superficies repetidas; G-23–G-25 dependían del árbol del corpus.
- **Experimento que lo distingue:** reserva de oraciones nuevas, frente a líneas base de cadena, entrenamiento con cabezas barajadas y bot fresco.
- **Qué eliminaría:** si un ciclo posterior demuestra que la alineación por árboles supera a la de G-28b, la raíz de 5 letras y los rasgos de vecindad lineal quedarían reemplazados.

Interfaz pública: `observe_parsed_sentence(palabras, clases, cabezas)` como demostración; `consolidate_syntax()` compila las tablas; `parse_sentence(texto)` devuelve palabras, clases, cabezas y la fuente del modelo. Rasgos de arco: clases de cabeza y dependiente, dirección, distancia agrupada, y versiones léxicas de palabras vistas ≥3 veces con respaldo hacia las no léxicas; puntaje = log-razón de la tasa suavizada de «es arco» frente a «oportunidad de arco». Oraciones de más de 60 palabras no se analizan (se informan).

## Datos, controles y puerta

UD Spanish-AnCora, revisión `20adddbfcdd773c6dc97ba48ea11ca9364e74185`: educación = `train` completo (14 287 oraciones; SHA-256 `47b6fc49…6deb6`); desarrollo visible = 300 oraciones de `dev`; **reserva** = 300 oraciones de `test` (SHA-256 `679f1c05…e67fa6f`) de ≤60 palabras elegidas con los primeros 8 hexadecimales de `git rev-parse freeze-G-29:leobot`. Se usan palabras, UPOS y HEAD; se omiten tokens multipalabra y nodos vacíos.

Controles: **fresco** (sin modelo: `parse_sentence` no analiza); **líneas base** cadena a la derecha y cadena a la izquierda; **cabezas barajadas** (misma educación con cada cabeza sustituida por otra posición al azar de su oración); **renombrado** (en la reserva, cada palabra no vista en la educación se reemplaza por otra inventada con el mismo sufijo de 3 letras y mayúscula: diagnóstico del modelo de sufijos, no puerta); **reinicio** (guardar/cargar da árboles idénticos); **hashseed 0/1** idénticos.

Puerta: precisión de clases ≥ 0,92; UAS (con puntuación) ≥ 0,70; ventaja ≥ 0,20 sobre la mejor cadena; cabezas barajadas ≤ 0,35 UAS; fresco sin análisis; reinicio idéntico; análisis p95 ≤ 100 ms por oración de ≤40 palabras; educación + consolidación ≤ 180 s CPU; RSS ≤ 512 MiB; huella idéntica antes/después. Si falla, se registra sin relajar. Si pasa, el ciclo siguiente preregistra la alineación pregunta–oración por árboles en MLQA con los controles de G-28.

## En palabras fáciles de entender

Hasta ahora Leobot compara palabras sueltas, como quien busca coincidencias sin entender la frase. Ahora le mostraremos miles de oraciones en las que un experto marcó qué palabra es verbo, cuál es nombre y de qué palabra depende cada una. Leobot contará esos patrones y tratará de marcar por sí solo oraciones que nunca vio. Si lo logra, podrá entender mejor quién hace qué en un texto.
