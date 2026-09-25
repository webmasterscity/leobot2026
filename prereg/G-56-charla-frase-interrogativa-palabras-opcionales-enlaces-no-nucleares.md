# G-56 — la charla: la frase interrogativa completa, las palabras de la pregunta que no hacen falta y los enlaces no nucleares

Fecha: 2026-09-25. Preregistro previo al código. Base: `freeze-G-54r` (árbol `5c6f2d59`). Se congela y evalúa junto con [G-55](G-55-no-por-lo-dicho-con-clase-aprendida.md).

## Fallo medido

Charla en primera persona de G-54 (material ya gastado, que pasa a desarrollo): Leobot **31/64**, el subagente 64/64. Casi todos los fallos son «No lo sé» a datos que sí se dijeron.

Causas, contadas en los 33 fallos:

**1. El complemento de la frase interrogativa se exige a la frase (4).**
- Ejemplo: «¿Qué día **de la semana** son mis clases?» frente a «tomo clases los jueves».
- G-42 aparta de las palabras exigidas la interrogativa y su sustantivo, pero no los complementos de ese sustantivo, que son parte del hueco.

**2. Palabras de la pregunta que la frase no necesita decir (5).**
- Ejemplos: «¿**Ya** tenemos sofá?» frente a «Todavía no tenemos sofá»; «¿Cuántos minutos aguanto corriendo **ahora**?».
- Toda palabra de contenido de la pregunta se exige, aunque sea de las que casi nunca repite la frase que contesta.

**3. El analizador y los enlaces estrictos (unos 9).**
- Ejemplo: «¿Fui a visitar a mi abuela el fin de semana pasado?» frente a la misma frase dicha.
- Con el verbo delante, el analizador cuelga «el fin de semana» de «abuela» como aposición. En la frase dicha lo tomó como sujeto.
- G-43 y G-47 exigen que se cumplan todos los enlaces de la pregunta. Sirven para distinguir quién hace qué: «Juan ama a María» no es «María ama a Juan».

Hay otras causas que este ciclo no ataca: datos repartidos entre dos frases (unos 5) y paráfrasis.

## Cambio (5.8)

**1. La frase interrogativa completa** (interruptor `gap_phrase`).
- La frase interrogativa es la interrogativa, su sustantivo y los dependientes nominales de ese sustantivo (`nmod` y lo que cuelga de ellos), según el análisis de la pregunta.
- Ninguna de esas palabras se exige a la frase recordada. Si están en ella, siguen sirviendo para colocar el hueco (G-47b).

**2. Palabras opcionales aprendidas** (interruptor `optional_words`).
- **Qué se cuenta.** Al educar, en los 87 595 ejemplos de SQuAD-es `train` y en los 2000 de MLQA se cuenta cuántas veces cada palabra de la pregunta (por lema) aparece en la oración del contexto que contiene la respuesta, y cuántas no. Solo se cuenta; no se analiza nada.
- **Cuándo una palabra es opcional.** Tiene apoyo ≥ 30 y falta de la oración de la respuesta en ≥ 80 % de los casos.
- **Qué palabras son candidatas.** Solo las que la sintaxis aprendida deja como modificadores y no como argumentos nucleares: adverbios y palabras colgadas como `advmod` en la pregunta.
- **Efecto.** Una palabra opcional que la frase recordada no tiene no se exige para buscar ni para colocar. Si la tiene, cuenta como siempre.
- **Límite.** Ninguna palabra negadora aprendida es opcional, porque cambia la polaridad.

**3. Enlaces no nucleares con holgura** (interruptor `core_links`).
- Solo en las preguntas de sí o no y en las abiertas: los enlaces de la pregunta entre dos palabras de contenido se dividen según la función de la palabra que cuelga.
- **Nucleares** (`nsubj`, `obj`, `iobj`, `ccomp`, `xcomp`, `csubj`): se exigen como hasta ahora. Son los que dicen quién hace qué.
- **Los demás** (modificadores, complementos de lugar y tiempo, aposiciones): basta con que las dos palabras estén colocadas en la misma oración y no haya otra entidad nombrada por medio, con la regla de G-47.
- La negación y la subordinación no cambian.

5.8:
- **Qué fallo resuelve:** los tres de arriba, medidos en la charla gastada.
- **Por qué no bastan los actuales:**
  - la frase interrogativa se toma sin sus complementos;
  - toda palabra de contenido se exige;
  - todos los enlaces son estrictos, aunque el analizador falla sobre todo en los modificadores.
- **Qué lo distingue:**
  - las tres ablaciones;
  - el control de **palabras barajadas**: las tasas de ausencia se reasignan al azar entre palabras;
  - el control de **roles invertidos** en desarrollo: «Juan ama a María» frente a «¿María ama a Juan?» debe seguir sin decir «sí».
- **Qué se elimina, si funciona:** nada. Se mide si el enlace estricto sigue haciendo falta para los modificadores.

## Evaluación

Junto con G-55, en material nuevo escrito después de congelar:
- reserva cuádruple con el encargo fijo;
- referencias;
- **charla doble** con el encargo de charla de G-54.

Los redactores son subagentes nuevos con la herramienta Agent, sin ningún mensaje del usuario. Los conjuntos se guardan en git antes de ejecutar.

**Desarrollo:** los 23 conjuntos gastados, con la charla de G-54.

**Se miden:**
- el tratamiento, cada ablación y todas juntas;
- palabras barajadas;
- sin memoria, barajada, renombrado y reinicio;
- SQuAD-es 2400 nuevos;
- errores confiados;
- la naturalidad con el juez a ciegas, solo como dato.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la charla doble | ≥ `freeze-G-54r` + 5 |
| Aporte de G-56 (tratamiento − sus tres ablaciones juntas), los tres conjuntos juntos | ≥ +5 |
| Afirma lo falso, los tres conjuntos juntos | ≤ `freeze-G-54r` + 1 |
| Errores confiados, los tres conjuntos juntos | ≤ `freeze-G-54r` + 2 |
| Palabras barajadas | aporte de `optional_words` ≤ la mitad del tratamiento |
| Roles invertidos (prueba focal) | ningún «sí» |
| Reinicio, barajada, renombrado, SQuAD-es, latencia | como en G-54 |

**Retirada (5.9):** se retira cada punto con aporte ≤ 0 en los tres conjuntos juntos.

## En palabras fáciles de entender

Cuando alguien te cuenta «tomo clases de guitarra los jueves» y luego pregunta «¿qué día de la semana son mis clases?», la respuesta es «los jueves». Leobot no la encontraba, porque buscaba también la palabra «semana», que nadie dijo. Pasaba lo mismo con palabras como «ya» o «ahora», que casi nunca se repiten al contar algo. Además, se enredaba cuando la pregunta empezaba con el verbo. Ahora aprenderá, contando miles de preguntas resueltas, qué palabras de una pregunta no hace falta que se hayan dicho. Seguirá siendo estricto con quién hizo qué a quién.
