from __future__ import annotations

import hashlib, json, random, statistics
from pathlib import Path
from time import perf_counter

from leobot.bot import Bot
from leobot.language import normalize

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results_v3'/'v32_procedure_grounding.json'


def code_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()


class EpisodicControl:
    """Same observations, but only exact episode recall; no synthesis/composition."""
    def __init__(self):self.memory={}
    def observe(self,text,before,after):self.memory[(normalize(text),tuple(before))]=tuple(after)
    def execute(self,text,state):return self.memory.get((normalize(text),tuple(state)))


def parameter_generalization(seed=3201):
    bot=Bot();bot.procedures.min_support=3
    mem=EpisodicControl()
    training=[('Suma 3 al valor.',(10,),(13,)),('Suma 5 al valor.',(7,),(12,)),('Suma 8 al valor.',(-2,),(6,))]
    reports=[]
    for row in training:
        reports.append(bot.observe_transition(*row));mem.observe(*row)
    rng=random.Random(seed);correct=episodic=0;lat=[]
    cases=[]
    for _ in range(200):
        x=rng.randint(-5000,5000);k=rng.randint(11,1000);text=f'Suma {k} al valor.';expected=(x+k,)
        t=perf_counter();out=bot.execute_transition(text,(x,));lat.append((perf_counter()-t)*1e6)
        correct += out.get('result')==expected
        episodic += mem.execute(text,(x,))==expected
        cases.append((x,k))
    return {'training':training,'last_report':reports[-1],'heldout':len(cases),'correct':correct,
            'episodic_correct':episodic,'median_us':statistics.median(lat),'sample_cases':cases[:5]}


def vector_generalization(seed=3202):
    bot=Bot();bot.procedures.min_support=3;mem=EpisodicControl()
    train=[(2,9),(5,-3),(11,4)]
    for before in train:
        after=(before[1],before[0]);r=bot.observe_transition('Intercambia los valores.',before,after);mem.observe('Intercambia los valores.',before,after)
    rng=random.Random(seed);correct=episodic=0
    for _ in range(200):
        a,b=rng.randint(-10000,10000),rng.randint(-10000,10000);exp=(b,a)
        correct += bot.execute_transition('Intercambia los valores.',(a,b)).get('result')==exp
        episodic += mem.execute('Intercambia los valores.',(a,b))==exp
    return {'training':train,'last_report':r,'heldout':200,'correct':correct,'episodic_correct':episodic}


def _learn_base(bot,samples):
    bot.procedures.min_support=3
    bot.programs.max_size=5;bot.programs.max_candidates=120000;bot.programs.max_seconds=5
    report=None
    for a in samples:
        report=bot.observe_transition('Combina los valores.',a,(a[0]*a[1]+a[2],))
    return report


def compositional_transfer(seed=3203):
    samples=[(2,3,1),(4,5,3),(3,7,2),(5,2,4),(7,4,6),(8,3,5)]
    full=Bot();ablated=Bot();no_prior=Bot();episodic=EpisodicControl()
    base_full=_learn_base(full,samples);base_ablated=_learn_base(ablated,samples)
    for a in samples: episodic.observe('Combina los valores.',a,(a[0]*a[1]+a[2],))
    for bot in (full,ablated,no_prior):
        bot.procedures.min_support=3;bot.programs.max_size=3;bot.programs.max_candidates=3000;bot.programs.max_seconds=2
    ablated.programs.auto_library_top_k=0
    full_report=ablated_report=no_prior_report=None
    for a in samples:
        y=(2*(a[0]*a[1]+a[2]),)
        full_report=full.observe_transition('Combina los valores y duplica el resultado.',a,y)
        ablated_report=ablated.observe_transition('Combina los valores y duplica el resultado.',a,y)
        no_prior_report=no_prior.observe_transition('Combina los valores y duplica el resultado.',a,y)
        episodic.observe('Combina los valores y duplica el resultado.',a,y)
    rng=random.Random(seed);scores={'full':0,'ablated':0,'no_prior':0,'episodic':0};semantic_changes=0
    for _ in range(200):
        a=(rng.randint(2,50),rng.randint(2,50),rng.randint(1,25));base=a[0]*a[1]+a[2];expected=(2*base,)
        scores['full'] += full.execute_transition('Combina los valores y duplica el resultado.',a).get('result')==expected
        scores['ablated'] += ablated.execute_transition('Combina los valores y duplica el resultado.',a).get('result')==expected
        scores['no_prior'] += no_prior.execute_transition('Combina los valores y duplica el resultado.',a).get('result')==expected
        scores['episodic'] += episodic.execute('Combina los valores y duplica el resultado.',a)==expected
        semantic_changes += (full.execute_transition('Combina los valores.',a).get('result') != expected)
    return {'base_full':base_full,'base_ablated':base_ablated,'target_full':full_report,
            'target_ablated':ablated_report,'target_no_prior':no_prior_report,'heldout':200,
            'scores':scores,'semantic_change_detected':semantic_changes,
            'full_target_library': full_report.get('reports',[{}])[0].get('library_selected',[]) if full_report else []}


def duplicate_support():
    bot=Bot();bot.procedures.min_support=3
    reports=[]
    for _ in range(7):reports.append(bot.observe_transition('Suma 3 al valor.',(10,),(13,)))
    return {'statuses':[x['status'] for x in reports],'final_support':reports[-1]['support'],'final_duplicate':reports[-1]['duplicate']}


def main():
    frozen=code_hash()
    started=perf_counter()
    result={'version':'0.3.2','experiment':'grounding_procedures','code_hash_before':frozen,
            'parameter_generalization':parameter_generalization(),
            'vector_generalization':vector_generalization(),
            'compositional_transfer':compositional_transfer(),
            'duplicate_support':duplicate_support()}
    result['code_hash_after']=code_hash();result['code_unchanged_during_evaluation']=result['code_hash_after']==frozen
    result['elapsed_s']=perf_counter()-started
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
