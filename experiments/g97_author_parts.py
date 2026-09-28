"""Bounded independent one-business author jobs after two failed large requests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from experiments.g74_relation_coverage import ENGINE
from experiments.g57_kiosco import contains
ROOT=Path(__file__).resolve().parents[1]
SECTORS=('biblioteca','taller de bicicletas','vivero','escuela de música','lavandería',
         'alquiler de herramientas','centro de fisioterapia','hotel')


def one(index,sector):
    seed=int(hashlib.sha256((ENGINE+f':G97R2:{index}').encode()).hexdigest()[:8],16)
    prompt=f'''Eres verificador independiente (regla 5.10), redactor, sin acceso al código ni resultados.
Redacta UN negocio ficticio de tipo {sector}, semilla {seed}. Su asistente recibe un documento
y responde preguntas de visitantes usando solo ese documento. Escribe un texto natural español
de hasta 180 palabras con hechos y condiciones, y 12 preguntas: EXACTAMENTE 8 con respuesta en
el texto y 4 sin dato suficiente. Incluye paráfrasis y una repregunta dependiente de la anterior.
No repitas siempre palabras del texto en la pregunta. IMPORTANTE: question es LA PREGUNTA LITERAL
del visitante, con ¿...?, NUNCA un nombre de persona. Las claves se copian literalmente del text;
vacías cuando no hay dato. No uses hechos externos ni fecha actual. Justificación ≤12 palabras.
Responde SOLO JSON compacto con esta estructura, sin markdown ni explicación:
{{"id":"identificador","text":"documento","instructions":"instrucción breve",
"conversations":[[{{"question":"¿Pregunta real del visitante?","accion":"responder",
"tipo":"directa","claves":["fragmento literal"],"justificacion":"motivo"}}]]}}
Usa accion responder/abstenerse, tipo directa/si_no. Puedes dividir en varias conversaciones.
Comprueba los 12 turnos y la distribución 8/4 antes de terminar.'''
    begin=time.monotonic(); raw={'index':index,'sector':sector,'prompt':prompt,'seed':seed}
    try:
        with tempfile.TemporaryDirectory(prefix='leobot-g97r2-author-') as folder:
            cmd=['/home/leonardo/.local/bin/claude','-p','--model','sonnet','--effort','low','--tools','',
                 '--no-session-persistence','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                 '--output-format','json']
            result=subprocess.run(cmd,input=prompt,cwd=folder,text=True,capture_output=True,timeout=60)
        raw.update(stdout=result.stdout,stderr=result.stderr,exit_code=result.returncode)
        if result.returncode: raise RuntimeError(result.returncode)
        parsed=json.loads(result.stdout); text=parsed['result'].strip()
        if text.startswith('```'):
            text='\n'.join(text.splitlines()[1:-1])
        business=json.loads(text)
        turns=[t for c in business['conversations'] for t in c]
        assert len(turns)==12 and sum(t['accion']=='responder' for t in turns)==8
        for t in turns:
            q=t.pop('question'); assert '¿' in q and '?' in q and len(q)>=6
            t['cliente']=q
            assert bool(t['claves'])==(t['accion']=='responder')
            assert all(contains(business['text'],k) for k in t['claves'])
        business['id']=f'part{index+1}-'+business['id']
        raw.update(cost_usd_reported=parsed.get('total_cost_usd'),model_usage=parsed.get('modelUsage'),valid=True)
        return business
    except Exception as exc:
        raw.update(error=repr(exc),valid=False)
        return None
    finally:
        raw['wall_s']=time.monotonic()-begin
        (ROOT/f'results_v3/g97_author_part{index+1}.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'part':index+1,'valid':raw['valid'],'wall_s':raw['wall_s']}),flush=True)


def main():
    begin=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        businesses=list(pool.map(lambda p:one(*p),enumerate(SECTORS)))
    if any(b is None for b in businesses): raise RuntimeError('Incomplete authored reserve; inspect preserved parts')
    target=ROOT/'results_v3/g97_reserve_v3.json'
    if target.exists(): raise FileExistsError(target)
    target.write_text(json.dumps({'businesses':businesses,'provenance':{'scope':'G97R2 independent one-business sessions',
        'engine':ENGINE,'wall_s':time.monotonic()-begin,'sectors':SECTORS}},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'complete':True,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)


if __name__=='__main__': main()
