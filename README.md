# Leobot 0.10.1 — sistema experimental

<p lang="es" style="text-align: justify; hyphens: auto;">Leobot reúne tres líneas de trabajo: lectura de frases y documentos, elección de estrategias aprendida de experiencias y uso en conversación de procedimientos y metas enseñados. Funciona en Python con procesador común; el motor usa solo la biblioteca incluida con Python. Es un proyecto de investigación: las pruebas actuales no demuestran conversación abierta, inteligencia general ni superioridad frente a los asistentes más avanzados.</p>

```bash
./run_tests.sh --solo-pruebas
./run_tests.sh
python3 -m leobot --help
python3 -m experiments.meta_feature_order_probe  # sonda opcional del orden
python3 -m experiments.user_text_probe           # lectura de frases del encargo
python3 -m experiments.meta_active_probe          # elección de pruebas para separar reglas
```

<p lang="es" style="text-align: justify; hyphens: auto;">La primera orden ejecuta las pruebas automáticas. La segunda también vuelve a ejecutar los experimentos y actualiza sus resultados en <code>results_v3/</code>. La sonda del orden comprueba que mover los datos útiles no impida aprender la misma regla. Sigue existiendo otro límite: dos señales que siempre coinciden en los ejemplos pueden confundirse al cambiar las condiciones.</p>

<p lang="es" style="text-align: justify; hyphens: auto;">El ensayo de pruebas activas muestra que Leobot puede elegir, entre casos posibles, uno que separe dos reglas compatibles con lo observado. Dos resultados del entorno corrigieron una elección errónea en una tarea preparada; sin esos resultados sigue equivocándose. Esto no demuestra que pueda distinguir causas ni comprender textos nuevos. Las cifras y controles están en <a href="LEOBOT_STATE.md">LEOBOT_STATE.md</a>.</p>

<p lang="es" style="text-align: justify; hyphens: auto;">El estado, las cifras, las decisiones de fusión, los fallos y la siguiente prueba están en <a href="LEOBOT_STATE.md">LEOBOT_STATE.md</a>. Los ZIP existentes son copias históricas; el estado actual es el código de este repositorio. No se generan ZIP nuevos como parte del trabajo habitual.</p>

## Kiosco: interfaz para integrar (G-57/G-58)

Carga una vez la información de un negocio y responde a cada persona. Todo ocurre en el mismo proceso, con la biblioteca estándar de Python. La base educada ocupa unos 100 MB. Para reconstruir la educación de la versión estable, incluyendo sus fuentes verificadas y la confianza de G-62:

```bash
timeout 1500s python3 -m experiments.reconstruir_kiosco /ruta/corpus_ud .leobot-data
```

La carpeta de entrada debe contener `es_ancora-ud-train.conllu` y `es_coser-ud-train.conllu`. La salida queda en `.leobot-data/base_kiosco.json`; `manifest.json` registra las fuentes, sus huellas y los tiempos. Esa carpeta persiste al reiniciar y no entra en Git. Este proceso reconstruye lo ya aprendido; no acredita capacidades nuevas.

```python
from leobot import Bot
bot = Bot.load('.leobot-data/base_kiosco.json')     # una vez
bot.load_context(texto_del_negocio, instrucciones)  # una vez por negocio
r = bot.answer('¿Cuánto cuesta la habitación doble?', historial)
r['text']      # lo único que se dice a la persona
r['status']    # 'answered' | 'closest' | 'unknown' | 'phatic'
r['evidence']  # la línea del texto que respalda la respuesta (si hay)
```

**Estados de la respuesta:**
- `answered`: respuesta plana. Solo aparece si la calibración lo permite; hoy no ocurre.
- `closest`: «No lo tengo seguro. Lo más cercano que dice el texto es: «…».». Solo cita texto del negocio.
- `unknown`: «No lo sé…».
- `phatic`: devuelve un saludo corto sin cifras.

**Garantías y límites:**
- No inventa: solo dice texto del negocio o frases fijas del motor.
- No guarda nada de lo que dice una persona. `historial` es solo de esa persona y hoy no se usa.
- El campo `candidate` es para quien integra y **nunca** se muestra a un cliente.
- Las instrucciones del negocio se cargan, pero todavía no se aplican.
- Medido en 24 negocios nuevos, calificados por un juez ciego (`freeze-G-58r`):
  - una de cada cuatro preguntas directas recibe una cita útil;
  - el 97 % de las preguntas sin dato se llevan bien;
  - el 3,9 % de las citas son engañosas;
  - 0 respuestas inventadas.

## Dónde está cada parte

| Carpeta | Contenido |
|---|---|
| <code>leobot/</code> | Motor que aprende, guarda y responde |
| <code>experiments/</code> | Experimentos reproducibles; ejecutar con <code>python3 -m experiments.nombre</code> desde la raíz |
| <code>tests/</code> | Pruebas automáticas |
| <code>results_v3/</code> | Resultados conservados de los experimentos |
| <code>examples/</code> y <code>knowledge/</code> | Datos de ejemplo y materiales iniciales |

## Dónde cambiar cada capacidad

| Archivo | Responsabilidad |
|---|---|
| <code>leobot/bot.py</code> | Estado compartido, conexión entre aprendices y guardado en archivo |
| <code>leobot/document.py</code> | Lectura de documentos y elección de referentes |
| <code>leobot/language_acquisition.py</code> | Aprendizaje de formas de frases y relaciones sin significado previo |
| <code>leobot/conditional_learning.py</code> | Preguntas transformadas y reglas condicionales |
| <code>leobot/dialogue.py</code> | Conversación, correcciones y construcción de respuestas |
| <code>leobot/procedures.py</code> y <code>leobot/symbolic.py</code> | Acciones numéricas y planificación con estados explícitos |
| <code>leobot/metacontrol.py</code> | Elección de estrategias y búsqueda de reglas sobre experiencias anteriores |
| <code>leobot/scalable.py</code> | Guardado con los hechos en disco |
| <code>leobot/state_fields.py</code> | Campos aprendidos que ambas formas de guardado conservan |
| <code>leobot/context.py</code> | Kiosco: cargar el texto de un negocio y responder con honestidad graduada |

<p lang="es" style="text-align: justify; hyphens: auto;">Para ampliar una capacidad, modifica su módulo, añade una prueba que falle antes del cambio y compara el experimento con la versión anterior y con un control sin el mecanismo. Si agregas información que debe sobrevivir al reinicio, verifica las dos formas de guardado. Registra la medición y el límite en <a href="LEOBOT_STATE.md">LEOBOT_STATE.md</a>; no conviertas el resultado de una prueba preparada en una afirmación de inteligencia general.</p>

<p lang="es" style="text-align: justify; hyphens: auto;">Leobot puede aprender una forma nueva de pregunta si ya aprendió la relación correspondiente y observa preguntas sobre hechos distintos. Exige que las palabras propias de la relación y el orden de sus participantes sigan siendo compatibles. Este avance no cambia el resultado de la sonda con cuatro frases sueltas del encargo: continúa en 0/4. El siguiente obstáculo es aprender de textos donde cada forma aparece una sola vez.</p>

## En palabras fáciles de entender

<p lang="es" style="text-align: justify; hyphens: auto;">Leobot intenta aprender reglas que una persona pueda revisar. Se unieron tres versiones hechas por separado y se conservaron las funciones que resistieron las pruebas. El motor, los experimentos, las pruebas y los resultados están ahora en carpetas distintas para que sea fácil encontrar cada cosa. En una prueba, eligió dos experiencias útiles y corrigió una regla equivocada al recibir los resultados reales. También aprendió una forma de pregunta después de leer varias frases parecidas y recibir dos preguntas anteriores. Todavía falla con muchas frases normales: en una pequeña prueba con texto del encargo no pudo contestar ninguna de cuatro preguntas. Las cifras altas corresponden a problemas preparados y repetitivos; no significan que pueda conversar o trabajar como los asistentes actuales.</p>
