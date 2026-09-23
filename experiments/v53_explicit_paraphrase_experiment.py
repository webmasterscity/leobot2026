from __future__ import annotations
import hashlib, json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot import Bot
from leobot.core import Atom, KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v53_explicit_paraphrase.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def seed(bot):
    rows=['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']
    reports=[bot.respond(x) for x in rows]
    assert reports[-1]['status']=='raw_relation_learned',reports[-1]
    return reports[-1]['predicate']

def main():
    before=code_hash()
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
    pred=seed(bot)
    teach=bot.respond('"luis recibe caja de ana" significa lo mismo que "ana entrega caja a luis".')
    assert teach['status']=='paraphrase_learned',teach
    parsed=stored=canonical=0; times=[]
    for i in range(100):
        text=f'r{i} recibe o{i} de p{i}'
        p=bot.language.parse(text); parsed += p.get('status')=='parsed' and p.get('frame',{}).get('pred')==pred
        t=perf_counter(); r=bot.respond(text); times.append((perf_counter()-t)*1000)
        stored += r.get('status')=='stored'
        canonical += bot.answer_atom(Atom(pred,(f'p{i}',f'o{i}',f'r{i}'))).get('status')=='supported'

    # Same experiences without explicit equivalence may learn a separate opaque
    # primitive, but must not silently equate it with the original predicate.
    ctl=Bot(KnowledgeBase(),allow_extensional_grounding=False); ctl_pred=seed(ctl)
    control_status=[]; control_canonical=0
    for i in range(100):
        r=ctl.respond(f'r{i} recibe o{i} de p{i}'); control_status.append(r.get('status'))
        control_canonical += ctl.answer_atom(Atom(ctl_pred,(f'p{i}',f'o{i}',f'r{i}'))).get('status')=='supported'
    control_preds=sorted({v['predicate'] for v in ctl.raw_relation_promotions.values()})

    # Explicit instruction cannot create meaning from two unknown strings.
    blank=Bot(KnowledgeBase(),allow_extensional_grounding=False)
    unresolved=blank.respond('"alfa zumba beta" significa lo mismo que "gamma frena delta".')

    # Nor can it merge two already distinct grounded relations.
    conflict=Bot(KnowledgeBase(),allow_extensional_grounding=False)
    p1=seed(conflict)
    for x in ['ana guarda caja en luis','bea guarda libro en mario','cora guarda mapa en nora']:
        p2r=conflict.respond(x)
    p2=p2r['predicate']
    bad=conflict.respond('"ana entrega caja a luis" significa lo mismo que "ana guarda caja en luis".')

    after=code_hash()
    result={
      'version':'0.5.3-candidate','experiment':'explicit_grounded_paraphrase_role_remapping',
      'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
      'instruction':{'status':teach['status'],'mechanism':teach['mechanism'],'canonical_predicate':pred},
      'heldout':{'cases':100,'parsed_to_canonical':parsed,'stored':stored,
                 'canonical_relation_supported':canonical,'median_response_ms':median(times)},
      'no_equivalence_control':{
        'canonical_relation_supported':control_canonical,'cases':100,
        'separate_raw_predicate_learned':any(x!=ctl_pred for x in control_preds),
        'distinct_predicates':control_preds,
        'statuses':sorted(set(control_status)),
      },
      'safety':{
        'two_unknown_status':unresolved.get('status'),
        'known_conflict_status':bad.get('status'),
        'conflict_predicates_were_distinct':p1!=p2,
      },
      'limits':[
        'This is explicit supervised semantic instruction, not autonomous synonym discovery.',
        'The quoted metalinguistic interface is intentionally narrow and does not yet understand arbitrary paraphrase requests.',
        'One grounded example is generalized compositionally by the existing slot learner; broader language variation still needs evidence.',
        'Internal synthetic evaluation does not demonstrate AGI/ASI.'
      ]
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
