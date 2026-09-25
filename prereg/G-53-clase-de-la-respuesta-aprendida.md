# G-53 — la respuesta debe ser de la clase que pide la pregunta (aprendida por conteo)

Fecha: 2026-09-24. Preregistro previo al código. **Sugerencia del usuario**, adoptada. Base: el motor de G-52 en desarrollo (`freeze-G-51` más G-52). Se congela y evalúa junto con G-52.

## Fallo medido

**Prueba común privada del usuario** (cierre del 24-09): `estable-G-12` sacó 20/32 con 2 respuestas equivocadas; G-51, 21/32 con 3. En las dos, la mitad o más de las equivocadas son de otra clase que la pedida: la pregunta pide un color y la respuesta es un tamaño o un nombre.

**En los conjuntos gastados:** «menor» a «¿Cuántos años…?», «en la plaza» a «¿En qué mes…?», «llamado» a «¿Cuántos años tiene el gato?», «nueva» a «¿De qué color…?».

**El hueco en el predicado de G-52 los multiplica.** En desarrollo, sus 4 pérdidas son todas de este tipo:
- «La caja roja está vacía» → «¿Dónde está la caja roja?» → «vacía»;
- «El carro es un modelo del año…» → «¿De qué color es el carro?» → «un modelo del año…» (dos veces);
- «Fueron juntos al mercado» → «¿A qué hora fueron?» → «juntos».

El filtro de G-47 (una clase nunca vista entre al menos 30 respuestas) casi no actúa. Además, con los 2000 ejemplos MLQA, «¿De qué color…?» tiene 5 ejemplos y «¿A qué hora…?» 4.

## Cambio (5.8) — interruptor `answer_kind`

**Educación.**
- Además de los 2000 MLQA, se cuentan la pregunta y la respuesta de los **87 595 ejemplos de SQuAD-es v1.1 `train`** (traducción automática; SHA-256 `196cfa14…`).
- Solo se cuentan: no se analizan ni se reeduca el lector de G-28.
- Se guardan aparte de las clases de G-47, que no cambian.

**Clase de pregunta.** Es la interrogativa con el sustantivo que la sigue («qué color»), si esa combinación tiene apoyo ≥ 30. Si no, la interrogativa sola. Si tampoco la tiene, no se comprueba nada.

**Comprobación de cada respuesta candidata**, antes de elegir entre ellas:
1. **Clase de palabra.** La clase aprendida (etiqueta) de la primera palabra de contenido de la candidata debe tener, entre las respuestas de esa clase de pregunta, una proporción ≥ **10 %**.
2. **Miembros**, solo si la clase de pregunta lleva sustantivo:
   - Alguna palabra de contenido de la candidata debe ser **miembro**. Es miembro si apareció, por lema, en respuestas de esa clase de pregunta, o si en la conversación se dijo unida a ese sustantivo («de color **café**»).
   - Excepción: la clase de palabra de esa palabra es **abierta** para esa clase de pregunta. Es abierta si hay al menos 10 casos y la probabilidad de una palabra nueva (Good-Turing: palabras vistas una sola vez / casos) es ≥ **0,5**. Así, los nombres de ciudad o las horas no necesitan haberse visto; los colores y los meses sí.
3. Una candidata que no pasa se descarta. Si no queda ninguna, la respuesta es «No lo sé».
4. Vale también para las respuestas de identidad de G-51.

5.8:
- **Qué fallo resuelve:** las respuestas de otra clase, dichas con seguridad.
- **Por qué no bastan los actuales:** el filtro de G-47 solo descarta clases nunca vistas y tiene pocos ejemplos por clase de pregunta.
- **Qué lo distingue:**
  - la ablación `answer_kind`;
  - la educación sin SQuAD-es (clases solo de MLQA).
- **Qué se elimina, si funciona:** el filtro de G-47, que queda subsumido.

## Evaluación

Junto con G-52, en su reserva cuádruple y sus dos conjuntos de referencias, escritos después de congelar. Lectura: sus 2400 casos de SQuAD-es.

Se mide además la ablación `answer_kind` y las respuestas equivocadas por clase de pregunta.

La prueba común del usuario la corre el usuario. Leobot no la lee; solo se informa la cifra que el usuario dé.

## Puerta

| Criterio | Umbral |
|---|---|
| Respuestas abiertas equivocadas (reserva y referencias juntas) | con `answer_kind` ≤ 2/3 de las de la ablación, o 0 si la ablación tiene ≤ 1 |
| Aciertos (reserva y referencias juntas) | con `answer_kind` ≥ ablación |
| Afirma lo falso | no aumenta |
| SQuAD-es `dev` (2400) | F1 ≥ lector de G-28 solo − 0,005 |
| Base educada | ≤ 100 MiB |
| Renombrado, reinicio, barajada, latencia | como en G-52 |

Si pasa junto con G-52: verificación independiente 5.10 y `estable-G-13`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando alguien pregunta «¿de qué color es la casa?», no sirve contestar «grande»: eso no es un color. Leobot a veces contestaba así, seguro de sí mismo. Ahora, antes de responder, revisará si la respuesta es de la clase que se pide: un color, un número, un lugar, una persona o un día. Esa clase la aprende contando qué se respondió en decenas de miles de preguntas ya resueltas, sin listas escritas a mano. Si la respuesta no calza, dirá «No lo sé», que es mejor que equivocarse.

## Enmienda antes de congelar (2026-09-24), por lo visto en desarrollo

Medida en los 18 conjuntos gastados (791 preguntas), con G-52 encendido.

**Primera versión, tal como estaba preregistrada:** 590 frente a 599 sin `answer_kind`. Bajaban las abiertas equivocadas (17 frente a 24), pero se perdían 24 respuestas correctas, por tres defectos:
1. **La clase de la primera palabra de contenido no es la clase de la respuesta.** «Junto a la ventana» se clasificaba por «junto» y «tres kilos de naranjas» por «tres». Ahora la clase es la del **núcleo** de la respuesta en la frase («ventana», «kilos»). Si no hay núcleo, se sigue usando la primera palabra de contenido.
2. **Clase de palabra en preguntas que admiten muchas clases.** «¿Qué…?», «¿Dónde…?» y «¿Cuándo…?» reparten sus respuestas entre varias clases, y el umbral del 10 % descartaba respuestas correctas («matemáticas» a «¿Qué enseña…?»). Ahora esa comprobación se aplica solo donde una clase se lleva al menos **2/3** de las respuestas («cuántos»: número 81 %).
3. **Nombres propios.** «Cali», «Cartagena» y «Cuenca» se descartaban porque «qué ciudad» salía cerrada (Good-Turing 0,44). Un nombre propio es una etiqueta arbitraria: no haberlo visto no dice nada. **Los nombres no necesitan haberse visto.**

Además:
- **Orden de la educación.** Las clases se cuentan después de consolidar las preguntas de educación. Si no, «cuántos» y «cuántas» todavía no se conocían como interrogativas y no se contaban.
- **Good-Turing sobre toda la clase de pregunta.** El cálculo de Good-Turing se hace sobre todas las respuestas de esa clase de pregunta, no por clase de palabra. Por clase, los pocos sustantivos de «qué color» (22 vistos una vez de 42, en su mayoría restos de traducción) la abrían. Sobre toda la clase de pregunta da 0,34: cerrada, como corresponde a los colores.

| Variante (desarrollo, 791) | Aciertos | Afirma lo falso | Abiertas equivocadas | «no lo sé» |
|---|---|---|---|---|
| G-52 + G-53 (enmendado) | **607** | 6 | **16** | 148/151 |
| sin `answer_kind` | 599 | 6 | 24 | 143/151 |
| G-53 preregistrado | 590 | 6 | 17 | 149/151 |

**G-53 enmendado frente a la ablación:** 10 preguntas ganadas y 2 perdidas.
- **Ganadas:** «¿Cuántos años tiene…?» ya no responde «llamado», «menor» ni «un gato llamado Rayo»; «¿De qué color…?» responde «rojo» o «es azul» en vez de «un modelo del año…»; «¿En qué mes…?» responde «Cada agosto» en vez de «en la plaza»; «nueve gallinas» en vez de «blancas».
- **Perdidas:** «se llama Ignacio Rojas» y «de la empresa será el próximo jueves». Eran respuestas mal cortadas que acertaban por la expresión regular.

La puerta no cambia.
