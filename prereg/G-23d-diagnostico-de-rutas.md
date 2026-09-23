# G-23d — diagnóstico posterior del fracaso de rutas

Fecha: 2026-09-23. **Análisis exploratorio posterior a G-23**, sin valor confirmatorio: la reserva 1361 ya fue puntuada y G-23 falló F1 ≥0,65. El motor y evaluador G-23 no se modifican ni se rescata su puerta. Este preregistro solo fija qué error medir antes de escoger una hipótesis nueva.

Repetir la misma educación/reserva documental y de lemas de [G-23](G-23-papeles-por-rutas-sintacticas.md) sobre las mismas fuentes UP/UD fijadas, reconstruir las tablas del evaluador congelado e inspeccionar agregados para A0/A1/A2, sin publicar oraciones. Entre cabezas gold representables, contar: clave completa nunca vista; clave vista pero sin ningún apoyo del papel; apoyo del papel presente pero regla no promovida; regla promovida con papel equivocado; regla promovida correcta. Entre predicciones positivas erróneas, separar cabeza no gold de papel incorrecto en cabeza gold. Esto distingue brecha de representación de decisión conservadora y de confusión semántica.

Decisión posterior, **no promoción**: si ≥50 % de los falsos negativos con cabeza representable corresponden a claves vistas con apoyo del papel pero sin promoción, la siguiente hipótesis prioritaria será valoración probabilística/competencia de hipótesis bajo desbalance. Si ≥50 % tienen clave completa nunca vista, priorizar abstracción de rutas y clases. Si ≥30 % de los falsos positivos tienen cabeza gold y papel equivocado, priorizar valencia léxica. Los criterios pueden solaparse; reportar todos sin forzar un diagnóstico único. El A2 con F1 cero se desglosa aparte.

Presupuesto CPU ≤30 s, pared ≤60 s, RSS ≤256 MiB, dos ejecuciones `PYTHONHASHSEED=0/1` y conteos discretos iguales; H0 idéntico. No se usan datos oficiales `dev/test` ni se cambian umbrales G-23. No integra un learner, no abre nueva reserva y no crea tag. El siguiente mecanismo requiere otro preregistro y held-out nuevo.

## En palabras fáciles de entender

La prueba anterior falló. Ahora contaremos si se equivocó porque nunca había visto una estructura parecida, porque una regla quedó demasiado insegura para usarla, o porque confundió el papel de una persona u objeto. Este recuento ayudará a escoger qué cambiar después; no contará como una victoria nueva.
