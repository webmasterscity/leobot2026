# G-115: δ contrastivo dentro del documento (solo datos, motor congelado `d1c92eb7…`)

Preregistro: `prereg/G-115-delta-contrastivo-en-documento.md`.

## Selección en desarrollo
Cinco bancos gastados (N = 1838 turnos directa/sí-no con claves). Conteo automático por claves: útiles con a lo sumo 0,26 N / 0,39 N / 0,65 N citas malas. Datos en `kiosco/g115_desarrollo/`.

| Sistema | 0,26 N | 0,39 N | 0,65 N |
|---|---|---|---|
| G-112 actual (δ de SQuAD-es) | 704 | 796 | 927 |
| Solo la mezcla, δ antiguo | 641 | 759 | 892 |
| Solo la mezcla, δ' reemplazo | 752 | 857 | 976 |
| Solo la mezcla, δ' media | 722 | 829 | 954 |
| **δ' reemplazo + G-112 reenseñado** | **802** | **900** | **1017** |
| δ' media + G-112 reenseñado | 775 | 878 | 1001 |
| δ' confundido + G-112 reenseñado (control) | 511 | 615 | 727 |

- Por banco, con 0,39 N, reemplazo frente a G-112: `g103` 177/161, `g111` 192/175, `g112` 201/165, `g114` 174/162, `g114b` 152/145. Ninguno empeora.
- Criterios de selección:
  - criterio 1 (≥ +2 puntos con 0,39 N y con 0,65 N): **pasa**, con +5,66 y +4,90 puntos;
  - criterio 2 (ningún banco peor en más de 1 punto): **pasa**.
- Se elige **reemplazo** para la reserva.
- δ' aprendido de 2264 turnos de los 216 negocios de enseñanza, con 15 s de CPU. Por ejemplo, δ(haber) baja de 0,50 a 0,12, δ(hora) de 0,46 a 0,08 y δ(costar) de 0,54 a 0,05, y δ(estacionamiento) sube a 0,79. Por clase: sustantivo 0,54, nombre propio 0,61, verbo 0,14 y determinante 0,13.
- El control confundido da δ' = 0 en todas las palabras y cae muy por debajo de G-112: la señal viene de la unidad correcta, no del procedimiento.
- Lectura: el δ antiguo medía cuánto repite una respuesta la palabra de su pregunta. El nuevo mide cuánto **distingue** esa palabra a la unidad que responde de sus vecinas del mismo documento, que es lo que decide la elección. Es una estadística por palabra, pero se concentra en palabras comunes a todos los sectores (verbos ligeros, interrogativos, preposiciones) y en el respaldo por clase gramatical, y por eso puede transferir a sectores nuevos. Eso es lo que debe probar la reserva.

## Reserva: banco nuevo `congelado_g115`, juez ciego doble. **Gran mejora de utilidad, pero no promovible: fallan los criterios 2 y 3**
- Banco: 32 negocios y 842 turnos de 8 redactores independientes, con commit `99e9eb1` antes de ejecutar.
- Jueces: A (Opus) y B (Sonnet) en 16 lotes, con 478 respuestas distintas. Los 26 desacuerdos (5,4 %) los resolvió un tercero (Opus).
- Datos: `kiosco/evaluacion_g115/`. `b0.json` es aquí el **control G-112** y `tratamiento.json` es G-115.

| | G-112 | G-115 (δ' + G-112 reenseñado) |
|---|---|---|
| Útiles en directas + sí/no (N = 392, juez) | 127 (32,4 %) | **199 (50,8 %)** |
| Engañosas (todos los turnos) | **17** | 32 |
| Sin respuesta coherentes bien manejadas | **161/165 (97,6 %)** | 157/165 (95,2 %) |
| Conteo automático, útiles | 117 | 185 |
| Conteo automático, citas sin dato / no útiles | 38 / 63 | 72 / 114 |
| `Bot.answer` p50/p95 | 1,29 / 2,06 ms | 1,29 / 2,14 ms |

Umbrales preregistrados:
1. **Pasa:** +18,37 puntos, con bootstrap por negocio [+13,52, +23,35]. Es la mayor mejora medida con juez en un banco nuevo en todo el proyecto.
2. **Falla:** 32 engañosas, por encima del tope de 17 + 3,9 = 20,9.
3. **Falla:** 95,2 % < 97 %.
4. **Pasa:** reinicio idéntico (0 diferencias en 842 respuestas) y p95 de 2,14 ms.

**Veredicto: no se promueve** (el preregistro exige 1–4). Se conserva así.

Diagnóstico (causa, no síntoma):
- δ' se contó en los mismos 216 negocios con los que después se calibra el umbral de cita de G-112, que sale de las puntuaciones cruzadas de esos mismos turnos.
- Esas puntuaciones «cruzadas» ya tienen dentro a δ', aprendido con su propia respuesta correcta, así que la calibración es optimista: `cite_from` baja de 0,5167 a 0,3971.
- En texto nuevo el sistema cita de más: +72 útiles, pero también +15 engañosas y 4 abstenciones perdidas.
- El remedio general es contar δ' fuera de pliegue (cada negocio calibrado con un δ' que no lo vio). Va en un preregistro nuevo, G-115b, con banco nuevo; no se toca este umbral.
