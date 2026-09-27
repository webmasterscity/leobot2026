# G-72 — compatibilidad aprendida entre verbos y construcciones

2026-09-27. Antes del código. Motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
Desarrollo externo, sin cambios en la base del kiosco ni en `leobot/`.

## En palabras fáciles de entender

La primera adaptación solo exigía que los participantes formaran una combinación
vista antes. Eso no bastó. Ahora se comprobará si aprender cómo aparecen los
verbos en otras frases ayuda a elegir la combinación adecuada. Los ejemplos
de evaluación procederán de documentos distintos. En la educación podrá haber
frases con esos verbos, pero sin decirle qué papel cumple cada participante.
Se medirá si puede trasladar lo aprendido con otros verbos.

Esto todavía entrega la estructura de la frase y marca el verbo que debe
analizar. Sirve para comprobar una idea, no para declarar que comprende cualquier
pregunta ni que resuelve el horario. Si desordenar las asociaciones aprendidas
produce el mismo resultado, se descarta otra vez.

## Hipótesis y antecedente

La [revisión de 2026](../results_v3/investigacion_2026_g71.md) identifica en
[CoNLL 2026](https://aclanthology.org/2026.conll-main.13/) una red de compatibilidad
entre elementos léxicos y construcciones. G-71 solo probó el inventario común.
G-25 aprendía palabras de enlace para decisiones individuales; no enseñaba
compatibilidad entre verbos y asignaciones completas. La diferencia experimental
será el vínculo entre cada verbo, su distribución estructural y las construcciones
aprendidas en otros verbos. Esta transferencia concreta es una **hipótesis
propia**, no un resultado ni una reproducción del artículo.

Si funciona, sustituiría el inventario indiscriminado G-71 por un índice de
compatibilidad aprendido; no se añade otro lector. Reutilizar íntegros los
conteos/calibración G-24 y el aprendiz/decisor G-71. Solo extender el cargador
para conservar documento/verbo y el decisor para recibir un conjunto de
construcciones admisibles. Ningún cambio en sus decisiones predeterminadas.

## Educación y particiones

Mismas fuentes, SHA, dos semillas y particiones supervisadas G-71, todas gastadas
para desarrollo. Las etiquetas de participantes de evaluación y calibración
quedan fuera de los conteos de enseñanza.

Un canal adicional ve **solo estructura**, sin etiquetas semánticas, en documentos
cuyos residuos `doc` y `caldoc` son distintos de cero. Incluye todos sus verbos,
incluso los excluidos de la enseñanza supervisada. No usa documentos de evaluación
ni calibración. Registrar tamaños y comprobar intersecciones vacías. No llamarlo
«verbos nunca vistos»: son verbos sin papeles enseñados, pero con ejemplos
estructurales previos. La referencia recibe la misma información; carece solo
del mecanismo que utiliza ese canal.

Para cada verbo contar las claves estructurales G-24 de las palabras candidatas,
sin sus etiquetas. Dividir por la longitud del vector y ponderar cada clave por
`log(1 + número_de_verbos / verbos_con_la_clave)`. Normalizar a longitud uno.
La cercanía entre verbos es el producto de esos conteos normalizados. No son
representaciones neuronales ni se aportan familias de verbos a mano.

En enseñanza supervisada, registrar qué construcciones completas G-71 aparecen
con cada verbo. Para cada verbo observado por el canal estructural, recuperar
los verbos de enseñanza más cercanos y permitir la unión de sus construcciones.
Conservar la puntuación local y frecuencia de G-71; no introducir otro peso
para favorecer la respuesta esperada. Ante un verbo sin evidencia estructural,
usar el inventario común. Si hay evidencia pero ningún vecino positivo, también
usar el común y contar el caso. Compilar los índices antes de decidir.

## Selección, controles y criterio

Cuatro opciones: uno, cuatro, dieciséis vecinos o todo el inventario G-71.
Elegir una vez por F1 completo en calibración; ante empate preferir el inventario
común y después el mayor número de vecinos. No cambiar opciones tras evaluar.

Comparar en desarrollo:

- G-24 independiente, G-71 común y G-72 con la selección calibrada;
- señal confundida: permutar entre verbos los perfiles estructurales durante
  la compilación, sin cambiar sus conteos ni las construcciones aprendidas;
  usar el mismo número de vecinos elegido para el tratamiento;
- reinicio: serializar los índices de compatibilidad y reproducir las decisiones;
- renombrado: cambiar biunívocamente verbos, claves y etiquetas en modelos e
  inputs ya construidos; las decisiones deshechas deben coincidir.

La puerta exige en **ambas** semillas: +0,03 F1 sobre el mejor entre G-24/G-71
y sobre la señal confundida, precisión y A2 no inferiores al mejor G-24/G-71,
asignaciones completas +5 puntos sobre el mejor G-24/G-71, controles exactos,
p95 de extracción dada más decisión <5 ms, y presupuesto válido. Reportar
también máximos, omisiones fuera del extractor y exposición de verbos.

Si el ajuste escoge inventario común, se ejecuta igualmente y se registra
«el aprendizaje de compatibilidad no aportó». No se promociona por calibración.
El resto de controles y límites de alcance de G-71 siguen pendientes antes
de cualquier integración. Sin juez ni reserva nuevos no hay medida de utilidad
del kiosco ni mejora demostrada de inteligencia general.

## Presupuesto y congelación

Por semilla: adquisición/extracción ≤120 s CPU, enseñanza/calibración/compilación
≤300 s, evaluación/controles ≤180 s, RAM ≤1 GiB, tiempo transcurrido ≤900 s.
Límites de construcciones y aplicaciones G-71 intactos. Canal estructural
≤2 millones de candidatos y ≤5 000 verbos; registrar saturaciones. Medir costes
por fase, candidatos y número de enlaces compilados. Fuentes ya en caché.

Commit de este registro antes de implementar; después congelar script y pequeñas
extensiones de G-71 bajo `freeze-G72-prototipo`. Medir huellas antes/después.

```bash
timeout 900s env PYTHONHASHSEED=0 python3 -m experiments.g72_compatibility 0
timeout 900s env PYTHONHASHSEED=0 python3 -m experiments.g72_compatibility 1
```

Pruebas focales para verificar que el filtro excluye construcciones incompatibles
y que su ausencia conserva G-71. La prueba rápida de la sesión ya pasó 13/13;
regresión completa solo si se intenta un tag estable. Auditoría independiente
solo conforme a MISION 5.10. No alterar los resultados negativos previos.
