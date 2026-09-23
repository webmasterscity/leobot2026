from __future__ import annotations
import hashlib, json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v52_open_raw_arity.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


class V51BinaryRawControl(Bot):
    """Ablation matching the V5.1 raw learner's fixed binary scope."""
    @staticmethod
    def _raw_relation_pair_surface(left: str, right: str, max_slots: int = 3):
        proposal=Bot._raw_relation_pair_surface(left,right,max_slots=2)
        return proposal if proposal and proposal[1]==2 else None


def feed(bot, rows):
    reports=[]; times=[]
    for row in rows:
        t=perf_counter(); reports.append(bot.respond(row)); times.append((perf_counter()-t)*1000)
    return reports,times


def main():
    before=code_hash()
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)

    # Noise uses no repeated lexical content anchor; it should not invent a relation.
    noise=[f'entidad{i} verbo{i} objeto{i}' for i in range(60)]
    noise_reports,_=feed(bot,noise)
    noise_promotions=len(bot.raw_relation_promotions)

    support={
      1:['alfa vibra','beta vibra','gamma vibra'],
      2:['sujeto alfa enlaza modulo rojo','sujeto beta enlaza modulo azul','sujeto gamma enlaza modulo verde'],
      3:['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora'],
    }
    learned={}; acquisition_ms=[]
    for arity,rows in support.items():
        reports,times=feed(bot,rows); acquisition_ms.extend(times)
        last=reports[-1]
        assert last.get('status')=='raw_relation_learned',(arity,last)
        assert last.get('arity')==arity,(arity,last)
        learned[arity]=last

    held={}
    for arity,report in learned.items():
        pred=report['predicate']; parsed=stored=entailed=0; times=[]
        for i in range(100):
            if arity==1: text=f'nuevo{i} vibra'; args=(f'nuevo{i}',)
            elif arity==2: text=f'sujeto n{i} enlaza modulo m{i}'; args=(f'n{i}',f'm{i}')
            else: text=f'p{i} entrega o{i} a r{i}'; args=(f'p{i}',f'o{i}',f'r{i}')
            parsed += bot.language.parse(text).get('status')=='parsed'
            t=perf_counter(); rr=bot.respond(text); times.append((perf_counter()-t)*1000)
            stored += rr.get('status')=='stored'
            entailed += bot.answer_atom(Atom(pred,args)).get('status')=='supported'
        held[arity]={'cases':100,'parsed':parsed,'stored':stored,'entailed':entailed,
                     'median_response_ms':median(times)}

    # Demonstrate that the newly acquired ternary primitive can become background
    # knowledge for a distinct learned schema, then transfer to unseen entities.
    ternary_pred=learned[3]['predicate']
    train=['ana gestiona caja para luis','bea gestiona libro para mario',
           'ana no gestiona caja para mario','ana no gestiona libro para luis']
    schema_reports=[bot.observe_schema_statement(x) for x in train]
    schema=schema_reports[-1]
    assert schema.get('status')=='schema_learned',schema
    positive=negative=0
    for i in range(100):
        positive += bot.query_schema(f'p{i} gestiona o{i} para r{i}').get('status')=='entailed'
        negative += bot.query_schema(f'p{i} gestiona o{i} para r{(i+1)%100}').get('status')!='entailed'

    # V5.1-like binary control sees the same raw language and cannot bootstrap
    # unary or ternary primitives.  Binary acquisition remains available.
    ctl=V51BinaryRawControl(KnowledgeBase(),allow_extensional_grounding=False)
    control={}
    for arity,rows in support.items():
        reports,_=feed(ctl,rows); control[arity]={'last_status':reports[-1].get('status')}
    control['promoted_arities']=sorted(v['arity'] for v in ctl.raw_relation_promotions.values())
    ctl_schema=[ctl.observe_schema_statement(x) for x in train]
    control['composition_last_status']=ctl_schema[-1].get('status')

    # Bounded-scope safety: four varying roles are deliberately not promoted.
    four=['ana mueve caja de casa a oficina','bea mueve libro de plaza a tienda','cora mueve mapa de cuarto a taller']
    four_reports,_=feed(bot,four)
    four_promoted=any(r.get('status')=='raw_relation_learned' and r.get('arity')==4 for r in four_reports)

    after=code_hash()
    result={
      'version':'0.5.2-candidate',
      'experiment':'open_raw_relation_arity_1_to_3',
      'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
      'initial_ontology':{'facts':0,'entities':0},
      'noise_control':{'sentences':len(noise),'promotions':noise_promotions,
                       'statuses':sorted(set(r.get('status') for r in noise_reports))},
      'acquisition':{
        'learned_arities':sorted(learned),
        'surfaces':{str(k):v['surface'] for k,v in learned.items()},
        'predicates':{str(k):v['predicate'] for k,v in learned.items()},
        'median_support_response_ms':median(acquisition_ms),
      },
      'heldout_transfer':{str(k):v for k,v in held.items()},
      'downstream_schema':{
        'status':schema.get('status'),'arity':schema.get('learning',{}).get('arity'),
        'selected':schema.get('learning',{}).get('selected'),
        'uses_ternary_raw_primitive':ternary_pred in schema.get('learning',{}).get('selected',''),
        'positive_entailed':positive,'positive_cases':100,
        'mismatched_rejected':negative,'negative_cases':100,
      },
      'v51_binary_ablation':control,
      'bounded_scope':{'four_role_promoted':four_promoted,'last_status':four_reports[-1].get('status')},
      'limits':[
        'Anti-unification and predicate invention are established ideas; this is evidence about Leobot integration, not a novelty claim.',
        'The raw learner still requires lexical anchors between adjacent variable spans and is capped at three roles.',
        'Opaque relation induction does not establish intensional meaning or synonymy across different surfaces.',
        'Evaluation is internal and synthetic; it does not demonstrate AGI/ASI.'
      ]
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
