from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from leobot.bot import Bot
from leobot.core import KnowledgeBase, Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v52_raw_open_arity.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def learn(bot, rows):
    reports=[]
    for x in rows: reports.append(bot.respond(x))
    return reports[-1]

def main():
    before=code_hash(); started=time.perf_counter()
    bot=Bot(KnowledgeBase())
    curricula={
        'unary':['entidad alfa destella','entidad beta destella','entidad gamma destella'],
        'binary':['equipo alfa enlaza modulo rojo','grupo beta enlaza pieza azul','unidad gamma enlaza nodo verde'],
        'ternary':['sujeto alfa coordina modulo rojo en zona norte','sujeto beta coordina modulo azul en zona sur','sujeto gamma coordina modulo verde en zona este'],
        'quaternary':['agente alfa asigna objeto rojo desde origen norte hacia destino uno','agente beta asigna objeto azul desde origen sur hacia destino dos','agente gamma asigna objeto verde desde origen este hacia destino tres',
                      # V6.3 unified: evidence proportional to arity (V5.13), so four roles need four episodes.
                      'agente delta asigna objeto cobre desde origen oeste hacia destino cuatro'],
    }
    learned={k:learn(bot,v) for k,v in curricula.items()}
    correct={k:0 for k in curricula}; total=100
    for i in range(total):
        tests={
          'unary':(f'entidad nueva{i} destella',(f'nueva{i}',)),
          'binary':(f'equipo nuevo{i} enlaza modulo m{i}',(f'equipo nuevo{i}',f'modulo m{i}')),
          'ternary':(f'sujeto p{i} coordina modulo o{i} en zona z{i}',(f'p{i}',f'o{i}',f'z{i}')),
          'quaternary':(f'agente a{i} asigna objeto q{i} desde origen r{i} hacia destino d{i}',(f'a{i}',f'q{i}',f'r{i}',f'd{i}')),
        }
        for kind,(text,args) in tests.items():
            parsed=bot.language.parse(text)
            pred=learned[kind]['predicate']
            if parsed.get('status')=='parsed' and tuple(parsed['frame'].get('args',()))==args and parsed['frame'].get('pred')==pred:
                correct[kind]+=1
    # Constant-span minimum-description control.
    control=Bot(KnowledgeBase())
    c=None
    for text in ['sujeto a1 coordina modulo b1 en zona fija','sujeto a2 coordina modulo b2 en zona fija','sujeto a3 coordina modulo b3 en zona fija']:
        c=control.respond(text)
    result={
      'version':'V5.2-development', 'code_hash_before':before,'code_hash_after':code_hash(),
      'learned':{k:{'status':v.get('status'),'arity':v.get('arity'),'surface':v.get('surface'),'predicate':v.get('predicate')} for k,v in learned.items()},
      'held_out':{k:{'correct':v,'total':total} for k,v in correct.items()},
      'constant_span_control':{'status':c.get('status'),'arity':c.get('arity'),'surface':c.get('surface')},
      'elapsed_ms':(time.perf_counter()-started)*1000,
    }
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
