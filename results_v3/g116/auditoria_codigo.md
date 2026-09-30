# Auditoría G-116 (regla 5.10): revisión de `1f22417..freeze-G116-1`

**Resultado:** las correcciones de negación son correctas, las ha aprendido el programa y no están escritas a mano. La corrección de la carga de biblioteca **tiene un defecto grave**: rechaza bibliotecas que el propio motor produce. La comparación sigue pendiente; no declaro ninguna mejora del kiosco ni ningún tag estable.

Huella del motor congelado: `git rev-parse freeze-G116-1:leobot` → `c9359662c19c22e41d250ff9d8fc3630dbe328f6`. No modifiqué nada del repositorio (`git status` limpio). Los archivos temporales en `/tmp` ya están borrados.

## Comprobaciones hechas

| Punto | Resultado |
|---|---|
| Pruebas focales en el motor congelado: `PYTHONHASHSEED=0 timeout 40 python3 -m unittest tests.test_g106_saber tests.test_g108_biblioteca` | 14 pasan, 0 fallan |
| Las mismas pruebas nuevas sobre el motor anterior (`git archive 1f22417 leobot` a `/tmp`) | 13 fallos: las pruebas sí reproducen los fallos de antes |
| Reglas escritas a mano, servicios o modelos nuevos | Ninguno. La lista de negaciones sale de `negator_words()`, que se aprende de `Polarity=Neg` y de la concordancia (ver más abajo) |
| Negaciones que aprendió la base real (solo lectura) | `negators=["no"]`, `concord_negators=["nada","nadie","ni","ninguno","nunca","tampoco"]` |
| Negación en las rutas de plantillas e intersección | «¿El perro no es un animal?», «¿No es el perro un animal?» y «¿El perro NO es un animal?» ya no reciben «Sí». La pregunta positiva sigue respondiéndose. Por defecto las rutas generales siguen apagadas |
| Una biblioteca válida reemplaza un análisis fallido anterior | Correcto: `not trees.get(text)` sustituye el valor `False` y conserva los análisis válidos que ya había |
| Detección de ciclos y raíces | Es correcta y en tiempo lineal |

## Defectos

**1. Prioridad alta: la carga rechaza bibliotecas que el propio motor compila.**
- `_eisner` (`leobot/syntax.py:725`) no obliga a que haya una sola raíz, así que el analizador puede devolver árboles con varias.
- `attach_library` exige `head_list.count(0) == 1` y rechaza la biblioteca **entera**. El motor anterior la cargaba sin problema.
- Reproducción: entrenar con «El perro es un animal .» y «Hola .», compilar «Hola . El perro es un animal .» con `compile_sentences` y cargar el resultado con `attach_library`. Sale `heads '0,1,4,7,7,7,0,7'` y `ValueError: Análisis de biblioteca incompleto: 2`.
- Consecuencia: con textos reales (frases con punto y coma, dos puntos o varias oraciones seguidas) es probable que una biblioteca grande no cargue nada. Al usarla en el kiosco fallaría al arrancar.
- El subcaso `'0,0','root root'` de `test_invalid_library_is_rejected_without_partial_changes` fija este comportamiento como correcto. Se añadió en este mismo commit. Decidir entre corregir la carga o el analizador le toca a la sesión, con su preregistro.

**2. Prioridad media: una biblioteca compilada con otra base se rechaza entera.**
- La biblioteca guarda el texto, pero al cargarla las palabras se vuelven a separar con el modelo de la base actual (`split_words`). Si esa base aprendió otra forma de separar (por ejemplo «del» → «de el»), las longitudes no coinciden.
- Antes, en ese caso solo se omitía el análisis de esa frase. Ahora se lanza `ValueError` y no se carga ninguna fila.
- Reproducción: compilar «El perro es del barrio.» con la base A, añadir `split_table['del']=['de','el']` en la base B y cargar allí la biblioteca. Resultado: `RECHAZADA ENTERA: Análisis de biblioteca incompleto: 1` (con el motor anterior: `library_attached`).
- La causa de fondo es que la biblioteca no guarda las palabras separadas.

**3. Prioridad baja: la validación no está libre de efectos.**
- `split_words` llama a `consolidate_syntax()` si el modelo no está compilado, así que una biblioteca rechazada puede cambiar `syntax_model` (reproducido: `cambió=True`).
- Es un estado derivado que se calcularía igual con la primera pregunta. No toca frases, análisis guardados ni índices, que es lo que exigía el preregistro.

## Límites experimentales (no son defectos del código)

- **Negación:** la guarda es gruesa. Cualquier palabra de negación en cualquier parte de la pregunta hace que el programa no conteste, aunque la negación no afecte a la relación preguntada (por ejemplo «¿…es un animal o no?»). El preregistro lo admite. La ruta `reading` no lleva guarda propia: depende del lector literal, y no pude comprobarla porque con el modelo mínimo tampoco responde a la pregunta positiva.
- **`experiments/g116_comparar.py`:**
  - La base `actual` se ejecuta con `soft_prefix` y `candidate_model` apagados (reproduce `estable-G-19`); las candidatas los llevan encendidos. Si solo se ejecuta así, una ganancia no distingue «base aprendida» de «interruptores de código».
  - Falta el control `base_kiosco` con los interruptores encendidos. El script lo permite si se pasa un segundo nombre, por ejemplo `actual_on=base_kiosco.json`. Conviene exigirlo antes de afirmar la hipótesis 3 del preregistro.
  - `rss_mib` acumula el pico de todo el proceso, no el de cada sistema.
  - Los bancos que usa ya se vieron: sirven como desarrollo, no como reserva.

## En palabras fáciles de entender

Revisé tres arreglos. El primero hace que el programa ya no conteste «sí» cuando alguien pregunta algo con un «no» dentro; funciona, y las palabras que niegan las aprendió leyendo, nadie se las dio escritas. El segundo le deja usar un libro ya preparado aunque antes no hubiera entendido una frase, y también funciona. El tercero debía impedir que cargue libros dañados, pero es demasiado estricto: rechaza libros que el propio programa preparó, y con que falle una sola frase no carga ninguna. Hay que arreglarlo antes de usarlo en el kiosco. La comparación con la versión que Leonardo usa todavía no se ha hecho, así que aún no se puede decir que el kiosco haya mejorado.
