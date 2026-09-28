"""Replacement for invalid named-speaker material; inference stays frozen."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from experiments.g74_relation_coverage import ENGINE
from experiments.g57_kiosco import contains
ROOT=Path(__file__).resolve().parents[1]


def main():
    seed=int(hashlib.sha256((ENGINE+':G97R').encode()).hexdigest()[:8],16)
    prompt=f'''Eres verificador independiente (regla 5.10), redactor de pruebas.
Un asistente recibe texto e instrucciones de un negocio y una pregunta de un visitante.
Debe responder solo con información del documento o reconocer que falta información.
No tienes acceso al código, modelos, datos educativos ni resultados del asistente.
Escribe ocho negocios ficticios diferentes en español. Cada uno necesita un documento natural,
instrucciones breves y doce preguntas plausibles, divididas en conversaciones. Ocho preguntas
deben tener respuesta en el texto y cuatro deben carecer de información suficiente.
IMPORTANTE: el campo question contiene LA PREGUNTA LITERAL que pronuncia el visitante,
con signos ¿...?; jamás un nombre de persona, etiqueta, rol ni resumen de la pregunta.
Incluye paráfrasis, condiciones, confusiones plausibles y una repregunta dependiente del historial
por negocio. No repitas siempre palabras idénticas al documento. Las claves deben ser fragmentos
literales cortos que una respuesta útil tendría que contener; vacías si falta el dato.
No uses la fecha actual ni conocimientos externos para responder. La justificación explica
brevemente por qué es contestable o qué información falta. Semilla de redacción: {seed}.
Entrega únicamente los datos estructurados solicitados, sin comentarios adicionales.'''
    turn={'type':'object','properties':{'question':{'type':'string','description':'Pregunta literal completa del visitante, con ¿ y ?, nunca nombre de persona.'},
          'accion':{'enum':['responder','abstenerse']},'tipo':{'enum':['directa','si_no']},
          'claves':{'type':'array','items':{'type':'string'}},'justificacion':{'type':'string'}},
          'required':['question','accion','tipo','claves','justificacion'],'additionalProperties':False}
    business={'type':'object','properties':{'id':{'type':'string'},'text':{'type':'string'},
              'instructions':{'type':'string'},'conversations':{'type':'array','items':{'type':'array','items':turn}}},
              'required':['id','text','instructions','conversations'],'additionalProperties':False}
    schema={'type':'object','properties':{'businesses':{'type':'array','items':business,'minItems':8,'maxItems':8}},
            'required':['businesses'],'additionalProperties':False}
    begin=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='leobot-g97r-author-') as folder:
        cmd=['/home/leonardo/.local/bin/claude','-p','--model','sonnet','--effort','low','--tools','',
             '--no-session-persistence','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
             '--output-format','json','--json-schema',json.dumps(schema)]
        result=subprocess.run(cmd,input=prompt,cwd=folder,text=True,capture_output=True,timeout=600)
    raw={'prompt':prompt,'stdout':result.stdout,'stderr':result.stderr,'exit_code':result.returncode,
         'wall_s':time.monotonic()-begin,'effort':'low','independence':'Fresh empty cwd, no tools or repository context.'}
    (ROOT/'results_v3/g97_author_v2_raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    if result.returncode: raise RuntimeError(result.returncode)
    parsed=json.loads(result.stdout)
    answer=parsed.get('structured_output')
    if answer is None: answer=json.loads(parsed['result'])
    assert len(answer['businesses'])==8 and len({b['id'] for b in answer['businesses']})==8
    for b in answer['businesses']:
        turns=[t for c in b['conversations'] for t in c]
        assert len(turns)==12 and sum(t['accion']=='responder' for t in turns)==8
        for t in turns:
            q=t.pop('question')
            assert len(q)>=6 and '¿' in q and '?' in q
            t['cliente']=q
            assert bool(t['claves'])==(t['accion']=='responder')
            assert all(contains(b['text'],k) for k in t['claves'])
    answer['provenance']={'engine':ENGINE,'seed':seed,'model_usage':parsed.get('modelUsage'),
                          'cost_usd_reported':parsed.get('total_cost_usd'),'wall_s':raw['wall_s'],
                          'scope':'Replacement LLM-written reserve, question field mechanically renamed cliente.'}
    target=ROOT/'results_v3/g97_reserve_v2.json'
    if target.exists(): raise FileExistsError(target)
    target.write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'businesses':8,'turns':96,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                      'cost':answer['provenance']}),flush=True)


if __name__=='__main__': main()
