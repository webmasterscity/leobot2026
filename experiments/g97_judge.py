"""Blind independent judgment of G97 reserve outputs; no learning."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
LABELS=['util_respaldada','abstencion_correcta','abstencion_indebida','cita_incorrecta',
        'afirmacion_sin_respaldo','problema_en_prueba']


def main():
    reserve=json.loads((ROOT/'results_v3/g97_reserve.json').read_text())
    run=json.loads((ROOT/'results_v3/g97_reserve_evaluation.json').read_text())
    indexed={}
    for r in run['rows']: indexed.setdefault(r['id'],[]).append(r)
    mapping={}; packet=[]; rng=random.Random(97)
    for business in reserve['businesses']:
        group={k:business[k] for k in ('id','text','instructions')}; questions=[]
        for ci,conversation in enumerate(business['conversations']):
            history=[]
            for ti,t in enumerate(conversation):
                identity=f'{business["id"]}/{ci}/{ti}'
                outputs={}
                for r in indexed[identity]:
                    text=r['reply'].get('text','')
                    key=hashlib.sha256((identity+'\n'+text).encode()).hexdigest()[:16]
                    outputs[key]={'id':key,'text':text}
                    mapping.setdefault(key,[]).append({'mode':r['mode'],'case':identity})
                values=list(outputs.values()); rng.shuffle(values)
                questions.append({'question':t['cliente'],'previous_customer_questions':history.copy(),
                                  'outputs':values,'author_expected_action':t['accion'],
                                  'author_justification':t.get('justificacion','')})
                history.append(t['cliente'])
        group['questions']=questions; packet.append(group)
    prompt='''Eres verificador independiente (regla 5.10), juez ciego. No conoces los sistemas ni sus reglas.
Evalúa cada respuesta por su utilidad y respaldo en el documento, considerando instrucciones,
condiciones y preguntas previas del cliente. Una cita literal irrelevante o que omite una condición
necesaria NO es útil. Abstenerse cuando el documento sí permite responder es abstencion_indebida.
Cita equivocada/irrelevante se distingue de afirmar un dato que no tiene respaldo. La etiqueta del
redactor es una hipótesis: si la pregunta está mal definida o mal etiquetada, usa problema_en_prueba.
Devuelve exactamente una etiqueta y explicación breve por cada id de output, sin omitir ninguno.
Etiquetas: util_respaldada, abstencion_correcta, abstencion_indebida, cita_incorrecta,
afirmacion_sin_respaldo, problema_en_prueba. No deduzcas identidades de sistemas.
Datos de evaluación:
'''+json.dumps(packet,ensure_ascii=False)
    schema={'type':'object','properties':{'judgments':{'type':'array','items':{'type':'object',
              'properties':{'id':{'type':'string'},'label':{'enum':LABELS},'reason':{'type':'string'}},
              'required':['id','label','reason'],'additionalProperties':False}}},
            'required':['judgments'],'additionalProperties':False}
    (ROOT/'results_v3/g97_blind_input.json').write_text(json.dumps({'packet':packet,'mapping':mapping},ensure_ascii=False,indent=2)+'\n')
    begin=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='leobot-g97-judge-') as folder:
        args=['/home/leonardo/.local/bin/claude','-p','--model','sonnet','--tools','',
              '--no-session-persistence','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
              '--output-format','json','--json-schema',json.dumps(schema)]
        p=subprocess.run(args,input=prompt,cwd=folder,text=True,capture_output=True,timeout=600)
    raw={'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'wall_s':time.monotonic()-begin,
         'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'outputs':len(mapping),
         'scope':'fresh independent session; no tools; model identities excluded from prompt'}
    (ROOT/'results_v3/g97_judge_raw.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    if p.returncode: raise RuntimeError(f'judge failed {p.returncode}')
    response=json.loads(p.stdout)
    output=response.get('structured_output')
    if output is None: output=json.loads(response['result'])
    judgments={r['id']:r for r in output['judgments']}
    assert len(judgments)==len(output['judgments']) and set(judgments)==set(mapping)
    counts={m:{label:0 for label in LABELS} for m in run['reports']}
    case_labels={}
    for key,links in mapping.items():
        for link in links:
            counts[link['mode']][judgments[key]['label']]+=1
            case_labels[link['mode'],link['case']]=judgments[key]['label']
    comparisons={}
    for mode in counts:
        changed=[(case,lab) for (m,case),lab in case_labels.items() if m==mode and lab!=case_labels['baseline',case]]
        comparisons[mode]={'new_useful':sum(lab=='util_respaldada' for _,lab in changed),
                           'new_incorrect':sum(lab in ('cita_incorrecta','afirmacion_sin_respaldo') for _,lab in changed)}
    report={'counts':counts,'comparisons':comparisons,'judgments':output['judgments'],
            'wall_s':raw['wall_s'],'model_usage':response.get('modelUsage'),
            'cost_usd_reported':response.get('total_cost_usd'),'remote_cpu':'not reported',
            'source_evaluation_sha256':hashlib.sha256((ROOT/'results_v3/g97_reserve_evaluation.json').read_bytes()).hexdigest()}
    (ROOT/'results_v3/g97_judgment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'counts':counts,'comparisons':comparisons,'wall_s':raw['wall_s']}),flush=True)


if __name__=='__main__': main()
