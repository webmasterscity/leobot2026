# G-48 — correspondencia de caminos aprendida de ejemplos resueltos

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-47b` (árbol `20a694f4`).

## Por qué (replanteo)

**Cinco diseños seguidos sin superar su puerta** (G-45, G-46, G-46b, G-47, G-47b). En reservas nuevas, la conversación queda en torno al 60 %; el subagente, en torno al 97 %. Lo que ganó G-47b en desarrollo (+18) no se repitió en su reserva (0).

La mayor parte de los fallos que quedan son **paráfrasis**: la oración dice el dato con otras palabras o con otra estructura que la pregunta.
- «un perro **llamado** Rocko» / «una panadería **llamada** El Trigal» → «¿Cómo **se llama**…?»;
- «trabaja **como** electricista» → «¿A qué **se dedica**…?»;
- «Marta **tiene** un perro» → «el perro **de** Marta».

Añadir cada equivalencia a mano sería un parche y no escala. La regla 4 manda buscar investigación cuando un obstáculo general resiste los mecanismos existentes:
- [DIRT](https://www.cis.upenn.edu/~danroth/Teaching/CS598-05/Papers/PantelLinDirt.pdf) (Lin y Pantel, 2001) aprende paráfrasis entre caminos de dependencias por distribución.
- [Cui et al., SIGIR 2005](https://www.comp.nus.edu.sg/~kanmy/papers/f66-cui.pdf) aprenden, de pares pregunta-respuesta, qué relación de la pregunta corresponde a qué relación de la oración (información mutua o EM).
- [Shen y Klakow, ACL 2006](https://aclanthology.org/P06-1112) puntúan la correlación entre el camino de la pregunta y el de la oración con pesos aprendidos.

Los tres son simbólicos y estadísticos, sin redes neuronales. No encontré un trabajo de 2025-2026 que lo haga sin redes; lo reciente es híbrido. La idea es compatible con Leobot: el conocimiento de las paráfrasis **se aprende educándolo**, no se programa.

## Hipótesis

Con ejemplos resueltos (contexto, pregunta, respuesta), Leobot puede aprender qué camino de la oración contesta cada camino de la pregunta. Con eso contestaría preguntas abiertas cuya estructura no coincide con lo dicho, sin reglas nuevas escritas por el desarrollador. **Refutación:** en la reserva nueva, el mecanismo no aporta al menos +2 frente a su ablación, o sube las afirmaciones falsas o las respuestas abiertas equivocadas por encima de la puerta.

## Cambio (5.8) — interruptor `learned_paths`

**Aprendizaje, en cada ejemplo resuelto y con la sintaxis ya aprendida:**
1. Se analizan la pregunta y la oración del contexto que contiene la respuesta. El núcleo de la respuesta es la palabra del tramo cuyo núcleo queda fuera del tramo.
2. Las palabras de contenido de la pregunta se alinean con la oración por lema (G-47b), una aparición cada una: la más cercana en el árbol al núcleo de la respuesta.
3. Para cada palabra alineada (**ancla**), se registran dos caminos, cada uno como la secuencia de funciones con dirección en el árbol mejorado con sujeto compartido:
   - el **camino de la pregunta**: de la interrogativa al ancla, con el lema de cada palabra de contenido intermedia **no alineada** (por ejemplo «llamar»);
   - el **camino de la oración**: del núcleo de la respuesta al ancla, solo con funciones.
4. Se cuentan los pares (camino de la pregunta, camino de la oración).

**Consolidación.** Se conservan los pares con apoyo ≥ 3 y P(camino de la oración | camino de la pregunta) ≥ 0,1.

**Uso.** Solo cuando la alineación estructural (G-42 a G-47b) no da respuesta:
- Son oraciones candidatas las que contienen todas las anclas nominales de la pregunta (sustantivos, nombres propios, números y adjetivos), aunque falte el verbo.
- Una candidata (subárbol sin anclas, como en G-42) vale si, para **cada** ancla colocada, el par (camino de la pregunta, camino de la oración) fue aprendido.
- Las colocaciones siguen «dice lo mismo de la misma entidad» (G-47), con la negación y la subordinación.
- La puntuación es la suma de log P de los pares. El empate entre textos distintos es «No lo sé con seguridad» (como en G-43).

**Educación:**
- los 2000 ejemplos MLQA de siempre;
- 20 000 ejemplos de SQuAD-es v1.1 `train` (traducción automática; SHA-256 `196cfa14…`), muestreados con la semilla de educación de G-28b.
Solo se aprenden caminos de SQuAD-es: su lector de G-28 no se reeduca. Así la base no cambia en lo demás.

5.8:
- **Qué fallo resuelve:** la paráfrasis estructural en preguntas abiertas.
- **Por qué no bastan los actuales:** la alineación exige las mismas palabras y la misma estructura, y el lector de G-28 no lee lo dicho en conversación (G-45).
- **Qué lo distingue:**
  - la ablación `learned_paths`;
  - el control de **caminos barajados**: los mismos pares con los caminos de la oración reasignados al azar entre preguntas;
  - la educación sin SQuAD-es.
- **Qué se elimina, si funciona:** nada todavía. Si funciona, la alineación estructural podría expresarse como el caso de camino idéntico.

## Evaluación

- **Desarrollo:** los 14 conjuntos gastados (592 preguntas).
- **Reserva doble nueva** después de `freeze-G-48`, con el encargo fijo.
- **Conjunto de referencias nuevo**, con el encargo de G-47.
- **Lectura:** 600 casos nuevos de SQuAD-es `dev`, excluidos los 600 de G-47b, con la semilla de `freeze-G-48`.
- **Se miden:**
  - G-48, G-47b congelado, `estable-G-11` y el subagente;
  - la ablación, los caminos barajados y la educación sin SQuAD-es;
  - sin memoria, barajada y renombrado.
- **Costo:** CPU y memoria de la educación de caminos y tamaño de la base (tope de carga: 100 MiB).

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-11` + 3 y ≥ G-47b congelado + 2 |
| Aporte (G-48 − ablación) en la reserva doble | ≥ +2 |
| Caminos barajados | aporte ≤ +0 |
| Referencias | ≥ G-47b congelado − 1 |
| Afirma lo falso | ≤ 2 en la reserva doble, ≤ 1 en referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| SQuAD-es `dev` (600 nuevos) | F1 ≥ lector de G-28 solo − 0,005 |
| Base educada | ≤ 100 MiB |
| Regresión completa, latencia intercalada con `estable-G-11`, p95 en conversación ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-12`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Hasta ahora, cuando alguien decía algo con otras palabras («un perro llamado Rocko» en vez de «el perro se llama Rocko»), Leobot no lo reconocía. Ir enseñándole cada forma de decir a mano no tiene fin. Esta vez aprenderá solo, leyendo miles de ejemplos de preguntas con su respuesta, qué formas de decir contestan cada tipo de pregunta. Si lo logra, podrá seguir mejorando con más lectura, sin que nadie le programe reglas nuevas.
