# G-113 — ¿Al kiosco le falta conocimiento («no sabía») o capacidad («no pudo»)? Curva de aprendizaje

Pregunta del usuario (2026-09-29): «¿y si la solución es la falta de conocimiento?». Diagnóstico (`experiments/g113_curva_aprendizaje.py`,
datos en `g113_curva.json`): el modelo del kiosco (G-112) enseñado con 54, 108, 216 y ≈ 280 negocios (216 antiguos + los otros dos bancos
nuevos) y medido en cada banco nuevo que no vio. Útiles con a lo sumo 0,26 N / 0,39 N / 0,65 N citas malas:
| evaluación | 54 | 108 | 216 | ≈ 280 |
|---|---|---|---|---|
| congelado_g103 (N = 383) | 138 / 162 / 178 | 152 / 166 / 181 | 142 / 160 / 177 | 142 / 159 / 178 |
| congelado_g111 (N = 372) | 153 / 173 / 192 | 149 / 170 / 192 | 146 / 170 / 195 | 148 / 173 / 192 |
| congelado_g112 (N = 365) | 151 / 173 / 203 | 150 / 172 / 207 | 147 / 168 / 213 | 147 / 171 / 212 |
**La curva es plana desde 54 negocios.** Más ejemplos de negocios con preguntas y respuestas no mejoran la elección (el «+1 a +6» con
279 negocios de la sección anterior era ruido). Junto con G-106 (saber léxico del mundo, 228 254 relaciones: sin mejora) y G-107/G-108
(Wikipedia: no mejora las respuestas), el hueco del kiosco se clasifica como **«no pudo»**: falta capacidad de representación (qué pide
la pregunta y qué afirma cada unidad), no cantidad de datos de este tipo. **No repetir**: generar más negocios de enseñanza para este
modelo.
