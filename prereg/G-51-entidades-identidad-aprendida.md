# G-51 — entidades: identidad por aposición, cópula y marcos de identidad aprendidos

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-49` (árbol `a0130092`), con G-49 encendido.

## Fallo medido

En los 16 conjuntos gastados (703 preguntas; G-49 congelado acierta 509), la causa más repetida de los fallos en preguntas abiertas es que **dos menciones de la misma persona o cosa no se tratan como la misma**:

- **Aposición:** «Camila vive en Manizales con su esposo **Julián**» → «¿Cómo se llama el esposo de Camila?»; «la panadería **El Trigo Dorado**» → «¿Cómo se llama la panadería?»; «Los hermanos **Ana y Luis** viven en Medellín» → «¿Dónde viven Ana y Luis?».
- **Identidad con «ser»:** «**Elena** es la hermana de Daniel» → «¿Quién es la hermana de Daniel?»; «Fernando es el padre de Camila» → «¿Cómo se llama el padre de Camila?».
- **Nombre dado con un verbo:** «El equipo del barrio Santa Rita **se llama Los Halcones**. … Los Halcones tienen catorce jugadores» → «¿Cuántos jugadores tiene el equipo?»; «Sofía tiene un perro llamado Rocko. … El perro duerme en el patio» → «¿Dónde duerme Rocko?».
- **Frase definida que retoma algo dicho:** «el perro», «el equipo» retoman «un perro», «El equipo del barrio Santa Rita».

Son unos 20–25 de los 194 fallos. Además, el analizador tiene un error sistemático: «Fernando es el padre de Camila» sale con «Fernando» como raíz y «padre» como aposición con cópula. En los dos análisis la relación es de identidad, pero la alineación estructural (G-42 a G-49) exige la misma forma en la pregunta y en la frase.

**Diagnósticos previos que no sirvieron (sin tocar el motor; se registran como negativos):**
- Educar la sintaxis con UD GSD además de AnCora: 502 frente a 509 en desarrollo.
- Contextos de arco anidados más raíz única, en un prototipo del analizador: UAS en AnCora `dev` de 0,797 a 0,807, pero 504 frente a 509 en desarrollo.

Un analizador mejor en AnCora no mejora la conversación. Lo que falla es la identidad.

## Cambio (5.8) — interruptor `entities`

**1. Pares de identidad en cada frase dicha** (copia resuelta de G-47):
- aposición (`appos`), en ambas direcciones: es identidad por la definición de las dependencias universales;
- cópula: el predicado nominal con `cop` y su sujeto. También cuenta una aposición que lleva `cop`, porque es el mismo error sistemático del analizador;
- **verbos de identidad aprendidos** (punto 3): el sujeto del verbo, o el sustantivo que el verbo modifica («un perro **llamado** Rocko»), y su complemento nominal sin preposición.

No se usan pares de una frase negada ni subordinada.

**2. Entidades de la conversación:**
- Los pares de identidad de una frase unen sus menciones.
- Entre frases distintas se unen solo:
  - dos nombres propios con la misma forma;
  - una frase con artículo definido (rasgo `Definite=Def` aprendido de AnCora) con la mención anterior más reciente del mismo lema, dentro de la ventana de G-47, con el mismo número y sin modificadores que se contradigan.
- Un predicado sin artículo («Marta es **enfermera**») une solo dentro de su frase: una clase no une a dos personas.

**3. Marcos de identidad aprendidos de preguntas resueltas.** Al consolidar la lectura, en cada ejemplo de educación (los 2000 MLQA de siempre) se analizan la pregunta y la frase del contexto que contiene la respuesta.
- El marco de la pregunta es (interrogativa, lema del verbo o `cop`).
- El ancla es el argumento nominal de ese verbo que no es la interrogativa; se alinea por lema con la frase.
- Se cuenta si el núcleo de la respuesta es un par de identidad del ancla, por aposición o cópula.
- **Un marco es de identidad** si tiene apoyo ≥ 10 y una tasa de identidad ≥ 0,2.
- Los lemas de verbo (no `cop`) de esos marcos son los **verbos de identidad** del punto 1: una frase de la misma forma que responde a una pregunta de identidad afirma una identidad.

**4. Uso al responder:**
- **Alineación.** Cada mención de una frase recordada lleva también las claves de los núcleos de las demás menciones de su entidad, como los lemas alternativos de G-47b. Esas claves entran también en la búsqueda. Lo demás de G-47 (colocaciones, negación, subordinación) no cambia.
- **Preguntas de identidad.** Son las de un marco aprendido, o aquellas cuya interrogativa es el sujeto de un predicado con cópula. La frase nominal de la pregunta se coloca en una frase recordada, con las colocaciones de G-47. La respuesta es otra mención de su entidad: primero un nombre propio. Si hay dos respuestas distintas, «No lo sé con seguridad».
- **El nombre como respuesta.** Si la clase de respuesta aprendida (G-43) más frecuente para la interrogativa es el nombre propio, y la respuesta encontrada es un sustantivo común cuya entidad tiene un nombre, se responde con el nombre.

5.8:
- **Qué fallo resuelve:** la identidad no reconocida (aposición, cópula, nombre dado con un verbo, frase definida) y el error sistemático del analizador con «ser».
- **Por qué no bastan los actuales:**
  - G-47 solo resuelve pronombres, posesivos y sujetos omitidos;
  - la alineación exige la misma forma en la pregunta y en la frase;
  - las pruebas de arriba muestran que mejorar el analizador no basta.
- **Qué lo distingue:**
  - la ablación `entities`;
  - la ablación de los marcos aprendidos (solo aposición y cópula);
  - el control de **marcos barajados**: las respuestas se reasignan al azar entre los ejemplos de educación; así no debe aprenderse ningún verbo de identidad.
- **Qué se elimina, si funciona:** nada todavía. Si funciona, la regla de «compañeros» de G-47 (sujeto de la cópula, aposición) se podría expresar como pares de identidad.

## Evaluación

- **Desarrollo:** los 16 conjuntos gastados (703 preguntas).
- **Reserva doble nueva** y **conjunto de referencias nuevo** después de `freeze-G-51`, con los encargos de siempre.
- **Lectura:** 600 casos nuevos de SQuAD-es `dev`, excluidos los de G-47b y G-49, con la semilla de `freeze-G-51`.
- **Se miden:**
  - G-51, G-49 congelado, `estable-G-12` y el subagente;
  - la ablación `entities`, la de marcos aprendidos y los marcos barajados;
  - sin memoria, barajada, renombrado y reinicio.
- **Costo:** CPU y memoria de la educación con marcos, y tamaño de la base (tope de carga: 100 MiB).
- **Controles no aplicables, con su justificación:**
  - **contraevidencia:** la memoria literal no retira lo dicho (G-41);
  - **señal confundida:** los marcos barajados cumplen ese papel, porque separan el aprendizaje del marco de la mera presencia del verbo.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-12` + 2 y ≥ G-49 congelado + 1 |
| Aporte (G-51 − ablación `entities`) en la reserva doble y referencias juntas | ≥ +2 |
| Marcos barajados | ningún verbo de identidad aprendido |
| Referencias | ≥ `estable-G-12` − 1 |
| Afirma lo falso | ≤ 2 en la reserva doble, ≤ 1 en referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Reinicio | respuestas idénticas en el 100 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| SQuAD-es `dev` (600 nuevos) | F1 ≥ lector de G-28 solo − 0,005 |
| Base educada | ≤ 100 MiB |
| Regresión completa, latencia intercalada con `estable-G-12`, p95 en conversación ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-13`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando alguien dice «Fernando es el padre de Camila» o «su esposo Julián», entendemos que se habla de una sola persona con dos maneras de nombrarla. Leobot todavía no lo entendía: si luego le preguntaban «¿Cómo se llama el padre de Camila?», no sabía que era Fernando. Ahora juntará las distintas maneras de nombrar a la misma persona o cosa. Además, aprenderá solo, leyendo preguntas ya resueltas, qué verbos sirven para dar un nombre («se llama», «llamado»), sin que nadie se lo escriba.
