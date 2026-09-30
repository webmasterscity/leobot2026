# G-106 — Saber general humano y comparación de cantidades como rasgos de candidata (kiosco)

Fecha: 2026-09-29. Estado: diseñado (precede al código). Motor de partida: `fa15c4a` (huella `2d651fbd…`). Entorno: nube, línea base B0
reconstruida (`experiments/nube_base.py` + `nube_educar.py`, `base_kiosco_nube.json` SHA `b9aafc1b…`; la de la sesión anterior no se
registró, así que las cifras absolutas de B0 difieren: B0 104/383 frente a 92/383 con conteo automático en `congelado_g103`).

## Qué fallo concreto resuelve
Desarrollo (banco `congelado_g103`, ya gastado; `experiments/g106_diagnostico.py`, modelo sin pares, 383 directas + sí/no con claves):
cita la unidad correcta 133; **elige otra unidad teniendo la correcta entre las 8 candidatas 104**; elige bien pero calla 55; ninguna
unidad contiene las claves 41; la correcta queda fuera de las 8 candidatas 38; sin ninguna palabra en común 12.
Tipos de fallo observados en una muestra de 14 elecciones erradas (desarrollo, no reserva): la palabra del cliente es un caso de la palabra
del texto («perro», «perrito» frente a «mascotas»), una forma corta («moto» frente a «motocicletas»), un sinónimo de uso («quedar» frente a
«estar»), y **una cantidad del cliente que cae dentro o fuera de un rango del texto** («150 transacciones» frente a «hasta 50» / «hasta 200»;
«5.000 €» frente a «hasta 3.000 €» / «más de 3.000 €»; «200 cc» frente a «150 cc o más»).

## Por qué los mecanismos actuales no bastan
- Los prefijos (G-103) solo unen palabras que empiezan igual; el puente contado de FAQ tiene 56 palabras en B0.
- Los pares palabra|palabra aprendidos de los bancos no transfieren a sectores nuevos (G-103: −0,3 puntos; en esta sesión, dev: modelo sin
  pares 129, con pares abstractos 114, prefijos solos 129 de 383). Aprender asociaciones palabra a palabra desde 216 negocios no basta.
- Sinónimos de WordNet sumados al BM25 ya se probaron sin ganancia (sesión anterior, `nube_diag/sweep3.py`): **no se repite** eso.
  Lo nuevo aquí: relaciones de inclusión y de sentido común (hiperónimo, parte, uso, lugar), y que el modelo aprenda **cuánto vale cada tipo
  de relación**, no cada palabra, de modo que lo aprendido no depende del sector.
- Ningún mecanismo compara un número de la pregunta con los números de una unidad.

## Mecanismo
1. **Saber general (motor, módulo nuevo `leobot/knowledge.py`).** Relaciones entre palabras enseñadas con
   `observe_relation(palabra_a, relación, palabra_b, fuente)`; se guardan como términos (lemas aprendidos de AnCora) en un índice de ida y
   vuelta; los nombres de relación son los de la fuente. Nada de listas de palabras en el código.
   Fuentes, todas escritas o curadas por personas y con licencia abierta (se registran SHA y URL):
   - WordNet español (MCR sobre PWN 3.0, OMW 1.4): mismo synset (sinónimo), hiperónimo, hiperónimo de instancia, meronimias
     (parte, miembro, sustancia), antónimo.
   - ConceptNet 5.7, aristas con ambos extremos en español (Wiktionary, Open Mind en español).
   - ConceptNet 5.7, sentido común de Open Mind en inglés cuyos dos extremos son una sola palabra con traducción humana inequívoca
     (Wiktionary o synset compartido de WordNet; si hay empate de votos, no se traduce). Cobertura medida: 6 123 de 226 283 aserciones.
     No se traducen frases (sería traducción hecha por el desarrollador).
2. **Candidatas (`_gains`).** Una palabra de la pregunta que no está en el texto puede explicarse por una palabra del texto relacionada con
   ella por una relación R (un paso; además, hiperónimo de hiperónimo). La ganancia usa la misma mezcla que los prefijos con
   δ(q)·s_R, donde s_R es la tasa, contada en los bancos de enseñanza, con que una palabra así relacionada está en la unidad correcta
   (una cifra por tipo de relación y dirección, no por palabra).
3. **Rasgos de la candidata (modelo G-103).** Nuevos rasgos densos: masa δ de la pregunta explicada por saber general; número de
   palabras explicadas así; y, para cada número de la pregunta frente a los números de la unidad, cuántos son iguales, mayores o menores.
   Nueva familia de pares `cmp`: «palabra junto al número de la unidad | comparación» (palabra anterior y posterior; comparación
   igual / la pregunta es menor / mayor), para que el significado de «hasta», «más de», «o más» se aprenda de los datos.
4. **Enseñanza.** Igual que G-103 (216 negocios de los 9 bancos gastados, validación cruzada por negocio, isotónica, umbral de cita con la
   regla de la enmienda 1 de G-103). La variante que va a la reserva se elige **solo con desarrollo**: el conteo automático en
   `congelado_g103` entre {prefijos solos, modelo sin pares, modelo + saber, modelo + comparación, modelo + saber + comparación}, exigiendo
   que las citas no útiles + sin dato no suban más de 10 % frente a prefijos solos.

## Qué eliminaría si funciona
El puente contado de FAQ (`bridge`) como única fuente de asociaciones y los pares léxicos palabra|palabra aprendidos de los bancos.

## Experimento que distingue las hipótesis
Banco **nuevo** (banco 2), escrito después de congelar el motor por redactores independientes (Agent con `isolation: "worktree"`, nunca
*fork*; encargo neutral `results_v3/kiosco/encargo_redactor_g103.md`, con la lista de sectores excluidos ampliada con los 31 de
`congelado_g103`; sin mensajes del usuario, sin este preregistro, sin ejemplos). Juez ciego doble (dos familias de modelo) con desempate,
rúbrica `encargo_juez_g103.md`, todas las respuestas no triviales de todos los sistemas mezcladas.
Sistemas: B0; prefijos solos (mejor en desarrollo hasta hoy); tratamiento; sin saber general; sin comparación; saber barajado (los
destinos de cada relación permutados dentro del mismo tipo: señal confundida); otro negocio; renombrado estricto; reinicio;
`PYTHONHASHSEED` 0 y 1.

## Umbrales de éxito (fijados ahora; no se cambian tras ver el banco 2)
Con el juez, directas + sí/no con respuesta:
1. Útiles del tratamiento ≥ prefijos solos + 4 puntos, con intervalo bootstrap por negocio (10 000) que excluye 0.
2. Aporte del saber: tratamiento − sin saber ≥ +2 puntos y tratamiento > saber barajado.
3. Aporte de la comparación: en los turnos cuya pregunta tiene un número, tratamiento − sin comparación ≥ +5 puntos de ese subconjunto
   (se informa n; si n < 30 el criterio se declara sin potencia, no aprobado).
4. Citas engañosas ≤ la tasa de prefijos solos + 1 punto; inventadas 0; sin respuesta bien manejadas ≥ 97 %; otro negocio ≤ 2 % útiles.
5. Latencia de `Bot.answer`: p95 ≤ 5 ms (presupuesto 10 ms); frente a `estable-G-19` (0,26 ms) la subida se justifica por escrito
   o no se promueve; reinicio y hashseed idénticos respuesta por respuesta; base ≤ 100 MiB.
Si 1 falla, no se promueve; los resultados se conservan.

## Presupuesto
Enseñanza ≤ 20 min de CPU; construir el saber general ≤ 10 min de CPU; RAM del proceso ≤ 1,5 GiB; sin red durante la respuesta.

## Riesgos declarados
- Relaciones léxicas amplias (hiperónimos lejanos) pueden traer ruido; por eso el peso es aprendido por tipo y se mide el barajado.
- Las traducciones inglés → español eligen el sentido más votado, no el del contexto.
- `congelado_g103` ya se usó para elegir la variante: no cuenta como reserva.
