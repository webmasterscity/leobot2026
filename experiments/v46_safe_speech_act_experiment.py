"""V4.6: compositional questions without extensional semantic guessing."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot.bot import Bot
from leobot.core import KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]; RESULT=ROOT/'results_v3'/'v46_safe_speech_act.json'
def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def main():
    bot=Bot(KnowledgeBase())
    for t in ['equipo alfa enlaza modulo rojo','grupo beta enlaza pieza azul','unidad gamma enlaza nodo verde']:
        learned=bot.respond(t)
    for i in range(100):
        assert bot.respond(f'sujeto {i} enlaza objeto {i}')['status']=='stored'
    before=code_hash(); facts=bot.kb.stats()['facts']; yes=wh=fronted=wrong=0; times=[]
    for i in range(100):
        t=perf_counter(); r=bot.respond(f'¿sujeto {i} enlaza objeto {i}?');times.append((perf_counter()-t)*1000)
        yes += r.get('status')=='supported'
        r=bot.respond(f'¿sujeto {i} enlaza que?')
        wh += r.get('status')=='bindings' and any(p['atom']['args']==[f'sujeto {i}',f'objeto {i}'] for p in r.get('proofs',[]))
        fronted += bot.respond(f'¿que enlaza sujeto {i}?').get('status')=='unrecognized'
        wrong += bot.respond(f'¿sujeto {i} separa objeto {i}?').get('status')=='unrecognized'
    after_facts=bot.kb.stats()['facts']; after=code_hash()
    report={'version':'0.4.6','experiment':'safe_speech_act_composition',
            'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'yes_no_supported':yes,'yes_no_cases':100,
            'in_situ_wh_correct':wh,'in_situ_wh_cases':100,
            'fronted_wh_abstained':fronted,'fronted_wh_cases':100,
            'wrong_anchor_abstained':wrong,'wrong_anchor_cases':100,
            'fact_delta_from_questions':after_facts-facts,
            'median_yes_no_ms':median(times),
            'limits':['WH frontal puede reordenar roles y permanece sin soporte hasta aprender una transformacion sintactica valida.','No demuestra comprension abierta ni AGI/ASI.']}
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
