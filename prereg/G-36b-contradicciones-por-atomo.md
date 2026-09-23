# G-36b — decidir por átomo, en tiempo constante, si una contradicción es posible

Fecha: 2026-09-23. Preregistro previo al cambio. Base: `freeze-G-36` (`b65b7729`). La auditoría 5.10 reprodujo su puerta, pero encontró dos problemas.

## Problemas medidos (auditoría 5.10)

1. **Latencia.** Para saber si existe algún hecho del predicado opuesto, G-36 llama a `kb.matches` con un patrón sin constantes, y eso ordena todo el grupo de hechos.
   - Con 100 000 hechos negados, `!padre(x1,x2)` pasa de 0,08 ms a 33,7 ms.
   - Eso rompe el límite de 10 ms (regla 5.6).
2. **Fragilidad.** La decisión es por predicado: un solo hecho `!padre` ajeno a la consulta hace volver el `incomplete` con más de 64 átomos.

## Cambio

Para cada átomo de la prueba:
- si **ninguna regla** tiene como cabeza el predicado opuesto, el opuesto solo puede valer por un hecho explícito de ese mismo átomo. Se comprueba con `kb.contains(opuesto)` en el índice, en tiempo constante: si existe, la conclusión queda impugnada (`contested`) sin lanzar ninguna consulta, y si no existe, no hay nada que revisar;
- solo si hay reglas para el predicado opuesto se lanza la consulta y cuenta para el tope de 64, como antes.

La respuesta es la misma que la de `estable-G-5` siempre que aquel terminaba, porque la consulta del opuesto solo puede usar hechos que coincidan y reglas de ese predicado. Límite que queda: con reglas para el predicado negado, la fragilidad por predicado sigue.

## Pruebas y puerta

**Prueba focal nueva** (`tests/test_conflict_checks_per_atom.py`):
- un hecho `!padre` ajeno a la consulta no vuelve `incomplete` la consulta de 40 ancestros;
- un `!ancestro` explícito sobre un átomo de la prueba sigue dando `contested`;
- la regla `!pred` sigue detectándose.

**Latencia:** con 100 000 hechos negados, `!padre(x1,x2)` y `vive(n5)` deben quedar con p95 ≤ 10 ms en 50 repeticiones.

**Confirmación:** CMP-2b con un mundo nuevo, sembrado con `freeze-G-36b`.
- Motor congelado: 100 % y 0 `incomplete`.
- Además, el mismo mundo **con un hecho negado ajeno** añadido: 100 % y 0 `incomplete`.

**Regresión:** completa, sin fallos nuevos.

**Latencia fija:** ningún p95 empeora más de un 20 %.

## En palabras fáciles de entender

La corrección anterior funcionaba, pero en memorias muy grandes podía volver lento a Leobot, y bastaba un dato negativo cualquiera para que volviera el problema. Ahora mirará, para cada conclusión concreta, si existe exactamente el dato que la contradice. Es una búsqueda instantánea en su índice.
