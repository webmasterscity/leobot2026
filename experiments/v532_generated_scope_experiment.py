"""V5.32 frozen experiment: choose among generated event scopes by prior predictive utility."""
from __future__ import annotations
import hashlib, json, copy
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v532_generated_scope.json'
PAIR=(('pa0','qa0'),('pa1','qa1'),('pa2','qa2'),('pa3','qa3'))
TRI=(('ta0','ua0','va0'),('ta1','ua1','va1'))
TARGET=('nova','novb','novc')

class MaximalClusterBot(Bot):
    """Ablation: V5.31/V5.26 behavior, always discard strict subclusters."""
    def _select_document_event_scopes(self,candidates,predicate,slot):
        viable=[c for c in candidates if self._document_event_reference_gate_allows(c,predicate,slot)]
        return self._maximal_document_event_candidates(viable),{'status':'maximal_cluster_ablation'}

def core_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()

def relations(pair_count=4):
    return tuple(x for fam in PAIR[:pair_count] for x in fam)+tuple(x for fam in TRI for x in fam)+TARGET+('activa',)

def ground(bot,pair_count=4):
    lines=[]
    for j,name in enumerate(relations(pair_count)):
        lines += [f'g{j}a {name} h{j}a.',f'g{j}b {name} h{j}b.',f'g{j}c {name} h{j}c.']
    out=bot.ingest_document_text(' '.join(lines),source=f'v532_grammar_{pair_count}')
    assert out['relations_promoted']==len(relations(pair_count))

def train_pair(bot,names,prefix):
    p,q=names
    for i in range(3):
        bot.ingest_document_text(f'{prefix}{i} {p} {prefix}x{i}. {prefix}{i} {q} {prefix}y{i}.',source=f'{prefix}_train_{i}')
    out=bot.ingest_document_text(f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. Eso activa {prefix}alarm.',source=f'{prefix}_use')
    assert out['sentence_results'][-1]['status']=='document_coreference_resolved'

def train_triple(bot,names,prefix):
    p,q,r=names
    for i in range(3):
        bot.ingest_document_text(f'{prefix}{i} {p} {prefix}x{i}. {prefix}{i} {q} {prefix}y{i}. {prefix}x{i} {r} {prefix}z{i}.',source=f'{prefix}_train_{i}')
    out=bot.ingest_document_text(f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}obj {r} {prefix}time. Eso activa {prefix}alarm.',source=f'{prefix}_use')
    assert out['sentence_results'][-1]['status']=='document_coreference_resolved'

def prepare(cls,pair_count=4):
    b=cls(allow_extensional_grounding=False);ground(b,pair_count)
    for i,fam in enumerate(PAIR[:pair_count]): train_pair(b,fam,f'P{i}')
    for i,fam in enumerate(TRI): train_triple(b,fam,f'T{i}')
    return b

def target(bot,i):
    p,q,r=TARGET;prefix=f'h{i:03d}'
    return bot.ingest_document_text(
        f'{prefix} {p} {prefix}obj. {prefix} {q} {prefix}loc. {prefix}obj {r} {prefix}time. Eso activa {prefix}alarm.',
        source=f'v532_target_{i}')

def main():
    before=core_hash()
    treatment=prepare(Bot,4)
    control=prepare(MaximalClusterBot,4)
    t2=t3=c2=c3=0
    for i in range(100):
        # Every held-out item starts from the identical pre-evaluation learner
        # state. The test set therefore cannot promote an exact schema and teach
        # later test cases.
        bt=copy.deepcopy(treatment); bc=copy.deepcopy(control)
        rt=target(bt,i);rc=target(bc,i)
        et=rt['sentence_results'][-1]['references'][0]['evidence'][0]['event_candidate']
        ec=rc['sentence_results'][-1]['references'][0]['evidence'][0]['event_candidate']
        t2 += len(et['member_fact_ids'])==2; t3 += len(et['member_fact_ids'])==3
        c2 += len(ec['member_fact_ids'])==2; c3 += len(ec['member_fact_ids'])==3
    # Separate equal-support preparation: generated alternatives must remain ambiguous.
    tie=prepare(Bot,2)
    tie_ambiguous=0
    for i in range(100):
        bt=copy.deepcopy(tie)
        r=target(bt,1000+i)
        tie_ambiguous += r['sentence_results'][-1]['status']=='document_coreference_ambiguous' and r['document_events_materialized']==0
    gate_supports=sorted(s['support'] for s in treatment.document_event_reference_hypotheses.values() if s.get('promoted'))
    after=core_hash(); assert before==after
    assert t2==100 and t3==0 and c2==0 and c3==100 and tie_ambiguous==100
    report={
        'version':'0.5.32','experiment':'generated_event_scope_competition',
        'code_hash':before,'code_frozen':True,
        'predictive_supports_initial':[2,4],
        'treatment':{'heldout_cases':100,'selected_two_fact_subevent':t2,'selected_three_fact_event':t3},
        'maximal_cluster_ablation':{'heldout_cases':100,'selected_two_fact_subevent':c2,'selected_three_fact_event':c3},
        'equal_support_control':{'heldout_cases':100,'safe_ambiguity':tie_ambiguous},
        'post_run_gate_supports':gate_supports,
        'claim':'generated competition among multiple event scopes using non-circular prior predictive evidence; not AGI/ASI'
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
