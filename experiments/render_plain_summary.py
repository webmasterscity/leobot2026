"""Regenerate the one-page, nontechnical PDF shipped with the checkpoint.

Optional publication dependency: WeasyPrint.  The Leobot engine does not use it.
Run from the repository root: python3 -m experiments.render_plain_summary
"""
from pathlib import Path

from weasyprint import HTML


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'EN_PALABRAS_FACILES.pdf'

HTML_TEXT = '''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>En palabras fáciles de entender — Leobot</title>
<style>
@page { size: A4; margin: 17mm 19mm 16mm; }
body { font-family: "DejaVu Sans", sans-serif; color: #203047; font-size: 10.2pt;
       line-height: 1.43; }
.eyebrow { font-size: 8.3pt; font-weight: 700; letter-spacing: .08em;
           text-transform: uppercase; color: #365e83; margin-bottom: 6mm; }
h1 { font-family: "DejaVu Serif", serif; font-size: 20pt; line-height: 1.18;
     color: #173a61; margin: 0 0 7mm; font-weight: 700; }
h2 { font-size: 10.8pt; color: #173a61; margin: 5.2mm 0 1.7mm; }
p { margin: 0; text-align: justify; hyphens: auto; }
.rule { border-top: 2pt solid #aec7d8; margin: 0 0 5mm; }
.closing { border-left: 3pt solid #5a94b5; padding: 3mm 0 3mm 4mm; margin-top: 6mm; }
.closing p { font-size: 9.3pt; }
</style>
</head>
<body>
<div class="eyebrow">Leobot · 22 de septiembre de 2026</div>
<h1>En palabras fáciles de entender</h1>
<div class="rule"></div>

<h2>Qué es Leobot</h2>
<p>Leobot es un programa de investigación que intenta aprender reglas a partir de ejemplos y usarlas después. Se juntaron tres líneas de trabajo que antes estaban separadas: leer frases y documentos pequeños, elegir cómo abordar una tarea y usar acciones enseñadas dentro de una conversación. Sus partes principales y las pruebas están ordenadas en un solo proyecto.</p>

<h2>Qué cambió ahora</h2>
<p>Cuando dos explicaciones encajan igual con los ejemplos recibidos, Leobot puede elegir entre varias pruebas posibles la que mejor las separaría. Pide hacer esa prueba y espera el resultado real; no inventa lo que pasó. Después usa la nueva experiencia para revisar la regla que había aprendido.</p>

<h2>Qué mostró la prueba</h2>
<p>En un ejercicio preparado con números, Leobot se equivocaba en 96 de 96 casos nuevos porque seguía una pista engañosa. Eligió dos experiencias que separaban esa pista de la útil y, al recibir sus resultados, acertó los 96 casos. Otra copia, con el mismo tiempo para dos experiencias poco útiles, siguió fallando los 96. Al recibir después información contraria, retiró la regla anterior. La prueba confirma una mejora en este ejercicio concreto; no demuestra que haya descubierto una causa ni que pueda hacerlo con cualquier tema.</p>

<h2>Qué todavía falta</h2>
<p>Leobot sigue sin entender bien frases humanas corrientes: leyó cuatro frases del encargo y no pudo responder ninguna de las cuatro preguntas sobre ellas. También puede unir de forma equivocada partes de un documento. La nueva manera de elegir pruebas necesita que alguien o el entorno ofrezca casos que realmente se puedan comprobar. Aún no se ha visto que la mejora pase a tareas de estructura diferente.</p>

<h2>Próximo paso</h2>
<p>Probar la lectura de textos escritos por personas sin adaptarlos al programa y comparar lo aprendido con una copia que solo busca y repite fragmentos. Si vuelve a fallar, registrar qué información le faltó antes de agregar más reglas escritas por nosotros.</p>

<div class="closing"><p>Leobot todavía es un laboratorio. No hay pruebas para afirmar que sustituye a los asistentes actuales, que posee inteligencia general o que supera a especialistas humanos.</p></div>
</body>
</html>'''


def main():
    HTML(string=HTML_TEXT, base_url=str(ROOT)).write_pdf(OUTPUT)
    print(OUTPUT)


if __name__ == '__main__':
    main()
