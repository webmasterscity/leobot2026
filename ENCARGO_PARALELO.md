# Encargo para investigar Leobot en paralelo

## En palabras fáciles de entender

Tu tarea es buscar y probar otra forma de que Leobot comprenda más preguntas,
sin programarle respuestas. Trabajarás en una carpeta separada del mismo proyecto.
Otra sesión sigue trabajando en la carpeta principal: no cambies sus archivos
ni combines los trabajos por tu cuenta. Entrega resultados reproducibles,
incluidos los fracasos. El objetivo sigue siendo responder bien al menos seis
de cada diez preguntas, con información respaldada y en menos de cinco
milisegundos, al cambiar de negocio.

## Prompt para la otra sesión

Trabaja como investigador e implementador paralelo de Leobot. Tienes
autorización para investigar, preregistrar hipótesis, implementar, entrenar y
evaluar mecanismos generales dentro de tu worktree. No eres el auditor
independiente de la regla 5.10 y tu trabajo no sustituye esa auditoría.

### Carpeta e independencia

Tu carpeta preparada es:

```text
/media/leonardo/data/leobot2026-paralelo
```

Empieza comprobando `pwd`, `git status --short`, `git rev-parse HEAD` y
`git rev-parse HEAD:leobot`. Trabaja solamente en esa carpeta. Está separada de
`/media/leonardo/data/leobot2026`, que sigue activa. La copia educativa local
`.leobot-data/base_kiosco.json` es independiente, no un enlace compartido.

El worktree comienza en HEAD separado —sin apuntar a una rama— para no inventar
un nombre de Jira ni mover `main`. Puedes hacer commits locales allí. Conserva
tu trabajo con tags exclusivos `freeze-PAR-1`, `freeze-PAR-2`, etc. Los tags y
las ramas se comparten entre worktrees: no muevas, borres ni reutilices los de
la sesión principal. No crees una rama sin tarjeta si las instrucciones lo
prohíben. Al entregar, indica los hashes de tus commits.

No hagas checkout, reset, rebase, merge, cherry-pick, limpieza ni push en el
worktree principal. No escribas en sus archivos, `.leobot-data/`, pruebas,
estado o preregistros. No elimines ni limpies otros worktrees. No hagas merge
de tu trabajo: entrega commits y evidencias para comparar e integrar después.
Cumple las preferencias de autoría y PR de AGENTS.md; no abras un PR por iniciativa
propia. Si se pide uno, debe tener exactamente un commit, sin coautores de IA.

### Objetivo y restricciones

Queremos aumentar la capacidad general de aprendizaje y comprensión de
Leobot, con prioridad en su uso como cerebro de kioscos. Recibe en texto plano
los datos e instrucciones de cualquier negocio y responde preguntas con historial.

Metas simultáneas:

1. Al menos 60 % de respuestas útiles en negocios nuevos.
2. Cero invenciones observadas; medir también citas engañosas e irrelevantes.
3. Menos de 5 ms por respuesta: informar p50, p95 y máximo, además del costo de
   educar y cargar. No esconder el aprendizaje en el tiempo de respuesta.
4. Transferir a negocios, nombres y formulaciones distintos.

Nada de reglas por negocio, listas de palabras elegidas para las preguntas,
excepciones para horarios, tablas de respuestas, soluciones en metadatos ni
cambios de pruebas para aparentar progreso. El conocimiento debe aprenderse
de datos y experiencia. El algoritmo puede ser general; los significados o
respuestas particulares no deben ser escritos por el desarrollador.

El motor `leobot/` no usa LLM, redes neuronales, representaciones neuronales ni
servicios que escondan esas capacidades. Solo biblioteca estándar de Python y
CPU, salvo las excepciones que autorice explícitamente el usuario. No usar
respuestas generadas por LLM como conocimiento de Leobot. Las evaluaciones
externas con otro modelo se rigen por MISION.md.

### Antes de proponer un mecanismo

Lee completos `AGENTS.md`, `MISION.md` y el estado pertinente de `LEOBOT_STATE.md`.
Este encargo paralelo tiene prioridad sobre reanudar la tarea que la otra sesión
tiene reservada: no dupliques G-73 ni numeres tus ensayos como G-74, G-75, etc.
Usa `PAR-1`, `PAR-2` en tus preregistros, scripts, resultados y tags. Puedes
actualizar el estado en tu copia; además, resume tus hallazgos en
`results_v3/PAR_ESTADO.md` para facilitar la comparación.

Lee `results_v3/investigacion_2026_g71.md` y los preregistros G-65 a G-72.
Busca artículos científicos primarios recientes, incluidos los de 2026, y
comprueba método, dependencias, controles, costo y límites. Contrasta cada idea
con las capacidades y resultados negativos existentes. Reutiliza los aprendices,
memoria, lectura, gramática y control ya presentes antes de añadir otro sistema.

Escoge una vía diferente de las construcciones y compatibilidad sintáctica
G-71/G-72. La sesión principal está examinando las anotaciones originales
AnCora-Nom/IARG-AnCora en G-73. Puedes elegir libremente otra hipótesis compatible;
no cambies de nombre mecanismos fallidos ni copies toda una arquitectura por
el resultado de un artículo que depende de redes neuronales.

### Estado real al preparar este encargo

- Motor estable `estable-G-19`, fase G en curso. Huella:
  `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.
- El 35,9 % proviene del juez del banco de G-62; no es una medición nueva de
  cada código posterior. Compara siempre ambos modelos en el mismo conjunto.
- G-65–G-67: alineación competitiva, preferencias y selección de unidades;
  ningún candidato pasó. Acertar una unidad candidata no equivale a que
  `Bot.answer` entregue una respuesta útil.
- G-68: árboles para confianza con los mismos rasgos, negativo.
- G-69: más correspondencias aprendidas, 275/816 frente a 269/816;
  mejora insuficiente y sin corregir la panadería.
- G-70: correspondencias condicionadas por parejas de palabras, 262/816.
- G-71: construcciones completas de participantes; ganancia pequeña que también
  aparece al barajar los enlaces. No demuestra aprendizaje de relaciones.
- G-72: compatibilidad entre verbos y construcciones a partir de sintaxis;
  la calibración descartó el mecanismo en las dos particiones. Sin aporte.
- No se promovió ningún cambio de esos ensayos. Las condiciones de la meta
  y el ejemplo completo del usuario siguen sin resolverse.

Los conjuntos existentes son desarrollo gastado, incluidos G-62/G-63/G-64 y
AnCora usado previamente. No los presentes como reserva nueva. No uses los
casos privados de duxiV2 para desarrollar.

### Reproducción exacta del fallo comunicado por el usuario

Usa la base educada, no `Bot()` vacío ni un texto mínimo distinto. SHA256 de la base:
`6fff61c20fcd5812d785eec22b6c595e19568f98ec31559e689c7fb95fe6d79f`.

Desde tu worktree:

```bash
python3 - <<'PY'
from leobot import Bot
b = Bot.load('.leobot-data/base_kiosco.json')
b.load_context("""Panadería La Espiga
Horario: lunes a sábado de 7:00 a 19:00. Domingos cerrado.
Dirección: Calle Real 12, frente a la plaza.
Pagos: efectivo y tarjeta. No aceptamos cheques.
Productos: pan de trigo, pan integral, croissants y tortas por encargo.
Las tortas por encargo se piden con dos días de anticipación.
""", '')
h = []
for q in ['¿A qué hora abren?', '¿Aceptan cheques?', '¿Tienen estacionamiento?']:
    r = b.answer(q, h)
    print(q, '->', r['status'], '|', r['text'])
    h += [q, r['text']]
r = b.answer('¿Dónde quedan?', [])
print('¿Dónde quedan? ->', r['status'], '|', r['text'])
PY
```

Resultado estable: horario desconocido; cheques citado correctamente;
estacionamiento desconocido correctamente por falta de dato; dirección
desconocida. Horario y dirección ya quedan primeros al buscar, pero su
confianza es insuficiente. Bajar umbrales no demuestra comprender y las
variantes de confianza ya fallaron. Este ejemplo es diagnóstico visible:
no lo uses para entrenar ni ajustar decisiones y no lo llames reserva.

### Proceso y entrega

Preregistra hipótesis, comparación, datos separados, controles, umbrales y
presupuesto; haz commit antes de implementar. Congela el código antes de
evaluar; mide frente a la referencia y al mecanismo desactivado. Usa controles
de señal barajada, renombrado, reinicio y ausencia de datos según correspondan.
Los casos nuevos para decidir una promoción se redactan tras congelar y se
juzgan independientemente. Mide respuestas reales mediante `Bot.answer`.

Hay otra sesión usando esta máquina: empieza con un solo proceso pesado,
CPU y RAM acotadas, timeout explícito. No lances trabajos sin límite ni
acciones que afecten a sus procesos. Puedes leer corpus públicos existentes
en `/media/leonardo/data/corpus_ud`; las escrituras y cachés van a tu copia.

Conserva negativos y costos. Si falla, cambia la hipótesis, no los criterios.
Entrega: explicación del mecanismo aprendido, fuentes, comandos reproducibles,
resultados frente a referencia/controles, límites, archivos educativos producidos
y hashes de commits. Distingue progreso parcial de haber alcanzado la meta.
Incluye una sección breve «En palabras fáciles de entender». Continúa de forma
autónoma y no pidas confirmación por decisiones reversibles ya autorizadas.
