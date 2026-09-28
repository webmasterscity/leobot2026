"""External independent test author/judge; outputs never enter learning."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from experiments.g74_relation_coverage import ENGINE
ROOT=Path(__file__).resolve().parents[1]


def ask(prompt, schema, raw_path):
    begin=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='leobot-g97-independent-') as folder:
        args=['/home/leonardo/.local/bin/claude','-p','--model','sonnet','--tools','',
              '--no-session-persistence','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
              '--output-format','json','--json-schema',json.dumps(schema),prompt]
        result=subprocess.run(args,cwd=folder,text=True,capture_output=True,timeout=600)
    raw={'wall_s':time.monotonic()-begin,'exit_code':result.returncode,'stdout':result.stdout,
         'stderr':result.stderr,'prompt':prompt,'model_requested':'sonnet','tools':[],
         'independence':'Fresh CLI session; empty temporary cwd; no repository/files/tools supplied.'}
    raw_path.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    if result.returncode: raise RuntimeError(f'Independent CLI failed: {result.returncode}')
    parsed=json.loads(result.stdout)
    if parsed.get('is_error'): raise RuntimeError('Independent model returned an error')
    answer=parsed.get('structured_output')
    if answer is None: answer=json.loads(parsed['result'])
    return answer,{'wall_s':raw['wall_s'],'model_usage':parsed.get('modelUsage'),
                   'cost_usd_reported':parsed.get('total_cost_usd'),'remote_cpu':'not reported'}


def author():
    seed=int(hashlib.sha256((ENGINE+':G97').encode()).hexdigest()[:8],16)
    prompt=f'''Eres verificador independiente (regla 5.10), redactor de pruebas, no implementador.
Solo conoces esta tarea: un asistente recibe el texto de un negocio y sus instrucciones con
load_context(texto,instrucciones), y contesta answer(pregunta,historial). Debe contestar
con evidencia del texto o reconocer que falta información. No tienes herramientas ni acceso
al repositorio, implementación, material educativo o resultados. No inventes resultados del asistente.
Semilla de redacción derivada del motor: {seed}. Crea ocho negocios ficticios nuevos de sectores
diversos, con documentos naturales en español y preguntas plausibles de clientes. Cada negocio
debe tener exactamente doce turnos, ocho con respuesta en su documento y cuatro sin información
suficiente. Distribúyelos en conversaciones e incluye paráfrasis, condiciones, confusiones plausibles
y alguna repregunta que necesite su historial. Redacta libremente, sin limitarte a una lista de temas.
Las preguntas no deben repetir siempre las mismas palabras del documento. No suministres la
respuesta en la propia pregunta. Evita preguntas sobre la fecha de hoy o datos externos.
Cada turno lleva cliente, accion (responder o abstenerse), tipo (directa o si_no), claves
(fragmentos literales cortos necesarios para una respuesta útil; vacío si no hay dato),
y justificacion breve. Las claves de responder deben aparecer literalmente en el documento.
Cada negocio lleva id, text, instructions y conversations (lista de listas de turnos).
Entrega solo el objeto JSON de la estructura solicitada. No incluyas explicaciones externas.'''
    turn={'type':'object','properties':{'cliente':{'type':'string'},'accion':{'enum':['responder','abstenerse']},
          'tipo':{'enum':['directa','si_no']},'claves':{'type':'array','items':{'type':'string'}},
          'justificacion':{'type':'string'}},'required':['cliente','accion','tipo','claves','justificacion'],
          'additionalProperties':False}
    business={'type':'object','properties':{'id':{'type':'string'},'text':{'type':'string'},
              'instructions':{'type':'string'},'conversations':{'type':'array','items':{'type':'array','items':turn}}},
              'required':['id','text','instructions','conversations'],'additionalProperties':False}
    schema={'type':'object','properties':{'businesses':{'type':'array','items':business,'minItems':8,'maxItems':8}},
            'required':['businesses'],'additionalProperties':False}
    answer,cost=ask(prompt,schema,ROOT/'results_v3/g97_author_raw.json')
    from experiments.g57_kiosco import contains
    assert len(answer['businesses'])==8
    assert len({b['id'] for b in answer['businesses']})==8
    for b in answer['businesses']:
        turns=[t for c in b['conversations'] for t in c]
        assert len(turns)==12
        assert sum(t['accion']=='responder' for t in turns)==8
        for t in turns:
            assert (bool(t['claves']))==(t['accion']=='responder')
            assert all(contains(b['text'],key) for key in t['claves'])
    answer['provenance']={'engine':ENGINE,'prompt_seed':seed,'cost':cost,
                          'author_model':'sonnet alias; resolved model in raw modelUsage',
                          'scope':'independent LLM-written business reserve, not human-authored data'}
    path=ROOT/'results_v3/g97_reserve.json'
    if path.exists(): raise FileExistsError(path)
    path.write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'businesses':8,'turns':96,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cost':cost}),flush=True)


if __name__=='__main__': author()
