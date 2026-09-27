# G-67 — aprender de la parte pertinente de cada ejemplo

Fecha: 2026-09-27. Anterior al prototipo. Base estable G-19, motor
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## Hipótesis

G-65 se quedó en 57,0 % de selección frente a 54,7 % de la base. G-66 prefirió
apagar sus correcciones en las tres semillas. Ambos aprendían con respuestas
enteras de MFAQ, mientras el kiosco compara renglones cortos: las palabras
incidentales de una respuesta larga pueden dominar la enseñanza.

Probar si basta cambiar la unidad de aprendizaje, conservando los algoritmos.
Dentro de la respuesta humana correcta, el selector de la base elige su unidad
mejor relacionada con la pregunta. Solo esa unidad enseña asociaciones. Es una
elección automática y potencialmente equivocada: no se declara respuesta correcta
a nivel de oración ni se usa para inventar etiquetas de los exámenes.
El criterio de corte y el selector ya existen en el motor. No se crean palabras,
reglas de negocios, sinónimos, plantillas ni extractores específicos.

Si funciona, unifica la enseñanza con la unidad que el motor usa al contestar;
evita añadir otro subsistema. Si falla, rechaza esta vía de selección automática
como sustituto de ejemplos que identifiquen qué parte responde.

## Diseño previo

MFAQ y muestra por dominio exactamente como G-65, antes de deduplicar se sustituye
cada respuesta por la unidad seleccionada por la base. Si no hay unidades, se
omite y cuenta; solo se conservan palabras del texto humano. Se informa número
de ejemplos antes/después y longitudes antes/después. Sin selección desde bancos.

Dos algoritmos ya programados: alineación G-65 (palabras y pares) y preferencia
G-66 (palabras). Mismos cinco ciclos, presupuestos y límites. G-66 tres semillas;
G-65 determinista. No se ajustan por los resultados de esta prueba.
Mezcla elegida solo en A–D: G-65 pesos originales; G-66 pesos originales.
Comprobación separada E–F y G-59/G-60, declarada desarrollo reutilizado.

Puerta: ≥60 % y +5 puntos sobre la base (346/633), con ninguna semilla peor
que la base. Para preferencia se mide el promedio; para alineación, cada variante.
Seleccionar pares requiere +2 puntos sobre palabras. Comparar además con los
resultados ya registrados de G-65/G-66 (mismos datos completos y algoritmos).
No elegir el peso usando el conjunto de comprobación.

Si pasa, integrar, enseñar sin editar el motor y congelar antes de la reserva
nueva y el juez ciego con todas las puertas y controles de G-65. Si falla,
no se toca el motor ni la confianza y el auditor verifica la conclusión.

## Costo y controles

Preparación ≤10 min CPU, aprendizaje ≤10 min CPU, ≤1,5 GB adicionales, dos
procesos pesados máximo y timeout explícito. Registrar CPU, RAM, ejemplos,
asociaciones, latencia diagnóstica y huella idéntica antes/después. Misma
información, sin selección, sin actualización y comparación contra palabras
son controles de desarrollo. Reinicio, retirada, datos incompatibles, memoria
literal, bot fresco y renombrado se exigen para cualquier integración posterior;
no se cuentan como pasados si el experimento se detiene antes.

## En palabras fáciles de entender

Una explicación puede contener la respuesta y muchas otras cosas. Vamos a
comprobar si Leobot aprende mejor al practicar con la parte más relacionada con
la pregunta. Él la elige usando lo que ya aprendió, por lo que también puede
elegir mal. Mediremos el resultado con otros negocios y mantendremos el cambio
solo si cumple las metas acordadas.
