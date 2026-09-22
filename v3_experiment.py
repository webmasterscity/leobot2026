from __future__ import annotations
import json, os, platform, random, statistics, tempfile, time
from pathlib import Path
from leobot.core import Atom, Engine, KnowledgeBase
from leobot.learning import RelationalLearner
from leobot.programs import ProgramLearner, Expr
from leobot.language import Language
from leobot.diskkb import SQLiteKnowledgeBase
from leobot.bot import Bot

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results_v3';OUT.mkdir(exist_ok=True)

def ms(fn):
    t=time.perf_counter(); v=fn(); return v,(time.perf_counter()-t)*1000

def numeric_dag(depth=10000):
    p=ProgramLearner();p.examples['s0']={(1,):{1}};p.solutions['s0']=[Expr('var',0)];p.dependencies['s0']=set()
    for i in range(1,depth+1):
        name,prev=f's{i}',f's{i-1}'
        p.examples[name]={(1,):{i+1}}
        p.solutions[name]=[Expr('add',children=(Expr('call',prev),Expr('const',1)))]
        p.dependencies[name]={prev}
    pred,t=ms(lambda:p.predict(f's{depth}',(7,)))
    return {'depth':depth,'value':pred['value'],'expected':depth+7,'correct':pred['value']==depth+7,
            'prediction_ms':t,'top_repr':str(p.solutions[f's{depth}'][0]),'top_repr_chars':len(str(p.solutions[f's{depth}'][0]))}

def numeric_auto_router(junk=2000):
    rng=random.Random(1107);p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=5,auto_library_top_k=16)
    train=[]
    for _ in range(8):
        a=tuple(rng.randint(2,12) for _ in range(3));train.append(a);p.add_example('base',a,a[0]*a[1]+a[2])
    base=p.fit('base')
    # Many already-learned same-arity skills irrelevant to the target.
    for i in range(junk):
        name=f'junk_{i}'
        p.examples[name]={(0,0,0):{i+10}}
        p.solutions[name]=[Expr('add',children=(Expr('var',0),Expr('const',i+10)))]
        p.dependencies[name]=set()
    for a in train:p.add_example('double',a,2*(a[0]*a[1]+a[2]))
    p.max_size=3
    rep,t=ms(lambda:p.fit('double'))
    pred=p.predict('double',(17,19,11))
    return {'junk_skills':junk,'status':rep['status'],'selected_count':len(rep.get('library_selected',[])),
            'base_selected':'base' in rep.get('library_selected',[]),'library_seeded':rep.get('library_seeded'),
            'fit_ms':t,'prediction':pred['value'],'expected':668,'correct':pred['value']==668,
            'candidates':rep['candidates']}

def numeric_semantic_router(junk=50000):
    rng=random.Random(2112);p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=5,auto_library_top_k=16)
    train=[]
    for _ in range(8):
        a=tuple(rng.randint(2,12) for _ in range(3));train.append(a)
        p.add_example('base',a,a[0]*a[1]+a[2],concepts=['commerce_math'])
    p.fit('base')
    for i in range(junk):
        name=f'junk_{i}'
        p.examples[name]={(0,0,0):{i+10}}
        p.solutions[name]=[Expr('add',children=(Expr('var',0),Expr('const',i+10)))]
        p.dependencies[name]=set();p.set_concepts(name,['unrelated'])
    for a in train:p.add_example('double',a,2*(a[0]*a[1]+a[2]),concepts=['commerce_math'])
    p.max_size=3
    rep,t=ms(lambda:p.fit('double'))
    pred=p.predict('double',(17,19,11))
    return {'junk_skills':junk,'status':rep['status'],'retrieval':rep.get('library_retrieval'),
            'selected':rep.get('library_selected'),'fit_ms':t,'correct':pred['value']==668,'prediction':pred['value']}

def relational_router(junk=5000):
    kb=KnowledgeBase()
    for i in range(12):kb.add(Atom('signal',(f'n{i}',f'n{i+1}')))
    for pair,val in [(('n0','n2'),True),(('n2','n4'),True),(('n4','n6'),True),(('n0','n3'),False)]:kb.add_example('twice',pair,val)
    for i in range(junk):kb.add(Atom(f'junk{i}',(f'x{i}',f'y{i}')))
    rep,t=ms(lambda:RelationalLearner(kb,max_length=2,max_candidates=2000).fit('twice'))
    q=Engine(kb).query(Atom('twice',('n6','n8')))
    return {'junk_predicates':junk,'status':rep['status'],'selected':rep.get('predicate_selected'),
            'total_relevant_candidates':rep.get('predicate_candidates_total'),'learn_candidates':rep['candidates'],
            'fit_ms':t,'new_case_correct':bool(q['answers'])}

def closure_scale(nodes=20000):
    kb=KnowledgeBase()
    for i in range(7):kb.add(Atom('p',(f'n{i}',f'n{i+1}')))
    for pair,val in [(('n0','n3'),True),(('n1','n4'),True),(('n3','n1'),False)]:kb.add_example('reach',pair,val)
    learn=RelationalLearner(kb,max_length=1,max_pairs=1000).fit('reach',allowed=['p'])
    for i in range(7,nodes-1):kb.add(Atom('p',(f'n{i}',f'n{i+1}')))
    q,t=ms(lambda:Engine(kb,max_work=nodes+100).query(Atom('reach',('n0',f'n{nodes-1}'))))
    return {'nodes':nodes,'learned':learn.get('selected'),'correct':bool(q['answers']) and q['complete'],
            'compiled':q['stats'].get('compiled',False),'work':q['stats']['work'],'query_ms':t}

def language_composition():
    l=Language();f=lambda who:{'act':'query','pred':'vive','args':[who,'?lugar']}
    l.teach('¿Dónde vive Ana?',f('ana'));l.teach('¿Dónde reside Bruno?',f('bruno'));l.teach('¿En qué ciudad vive Carla?',f('carla'))
    tests=['¿En qué ciudad reside Diego?','¿En qué ciudad reside Eva?','¿En qué ciudad reside Luis?']
    rows=[l.parse(x) for x in tests]
    open_prompts=['Resume este párrafo por sus ideas centrales','Explica por qué esta broma es graciosa','Diseña un experimento sobre memoria','Planea una ruta con tres restricciones','Compara dos teorías rivales']
    open_rows=[l.parse(x) for x in open_prompts]
    return {'unseen_combinations':len(tests),'parsed_unseen':sum(r['status']=='parsed' for r in rows),
            'composed_flags':sum(bool(r.get('composed_paraphrase')) for r in rows),
            'open_requests':len(open_prompts),'open_parsed':sum(r['status']=='parsed' for r in open_rows),
            'rewrite_rules':sum(len(v) for v in l.rewrites.values())}

def grounded_language_learning():
    known=[('bruno','merida'),('carla','valencia'),('eva','barquisimeto'),
           ('luis','maracay'),('marta','cumana'),('pedro','coro')]
    # Two independent grounded episodes per surface construction.  No semantic
    # frame is supplied to respond(); the canonical vive forms are seed grammar.
    assertions=[
      'Bruno reside en Mérida.', 'Carla reside en Valencia.',
      'Eva habita en Barquisimeto.', 'Luis habita en Maracay.',
      'Marta tiene su hogar en Cumaná.', 'Pedro tiene su hogar en Coro.',
    ]
    transfer=[
      'Diego reside en Acarigua.', 'Sofia reside en Maturín.',
      'Raul habita en Guanare.', 'Nora habita en Trujillo.',
      'Iris tiene su hogar en Carúpano.', 'Omar tiene su hogar en Cabimas.',
    ]
    # These question phrasings are never grounded/taught directly.  They rely
    # on lexical equivalences acquired from assertions and reused across acts.
    queries=['¿Dónde reside Bruno?','¿Dónde habita Eva?','¿Dónde tiene su hogar Marta?']
    def make(enabled):
        b=Bot(grounded_language=enabled)
        b.language.teach('Ana vive en Caracas.',{'act':'assert','pred':'vive','args':['ana','caracas']})
        b.language.teach('¿Dónde vive Ana?',{'act':'query','pred':'vive','args':['ana','?answer']})
        for who,place in known:b.kb.add(Atom('vive',(who,place)),'seed')
        return b
    control=make(False); learner=make(True)
    before_control=sum(control.language.parse(x)['status']=='parsed' for x in assertions+queries)
    before_learner=sum(learner.language.parse(x)['status']=='parsed' for x in assertions+queries)
    induction_rows=[learner.respond(x) for x in assertions]
    query_rows=[learner.respond(x) for x in queries]
    grounded_events=sum(e.get('source')=='grounded_induction' for e in learner.language.examples)
    control_rows=[control.respond(x) for x in assertions+queries]
    transfer_rows=[learner.respond(x) for x in transfer]
    stored_transfer=sum(r.get('status')=='stored' for r in transfer_rows)
    # Reuse question forms on newly learned entities.
    query_transfer=[learner.respond('¿Dónde reside Diego?'), learner.respond('¿Dónde reside Sofia?'),
                    learner.respond('¿Dónde habita Raul?'), learner.respond('¿Dónde habita Nora?'),
                    learner.respond('¿Dónde tiene su hogar Iris?'), learner.respond('¿Dónde tiene su hogar Omar?')]
    # Relevance stress with 5k irrelevant predicates: two independent supports
    # should still promote without scanning unrelated semantic neighborhoods.
    stress=Bot()
    stress.kb.add(Atom('vive',('bruno','merida')),'seed'); stress.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
    for i in range(5000):stress.kb.add(Atom(f'junk{i}',('bruno',f'x{i}')),'noise')
    s1,stress_first_ms=ms(lambda:stress.respond('Bruno reside en Mérida.'))
    stress_result,stress_ms=ms(lambda:stress.respond('Eva reside en Barquisimeto.'))
    # Ambiguous episode must remain pending and must not enter active grammar.
    ambiguous=Bot();before_amb=len(ambiguous.language.examples)
    for i in range(100):ambiguous.kb.add(Atom(f'p{i}',('ana',f'x{i}')),'noise')
    ambiguous_result,ambiguous_ms=ms(lambda:ambiguous.respond('¿Dónde está Ana?'))
    return {
      'before_control_parsed':before_control,'before_learner_parsed':before_learner,
      'grounded_events':grounded_events,
      'assertion_promotions':sum(r.get('status')=='stored' for r in induction_rows),
      'assertion_pending':sum(r.get('status')=='grounding_pending' for r in induction_rows),
      'cross_act_queries_answered':sum(r.get('status') in ('bindings','entailed') for r in query_rows),
      'cross_act_queries_total':len(query_rows),
      'control_after_success':sum(r.get('status') not in ('unrecognized','ambiguous') for r in control_rows),
      'transfer_assertions_stored':stored_transfer,'transfer_assertions_total':len(transfer),
      'transfer_queries_answered':sum(r.get('status') in ('bindings','entailed') for r in query_transfer),
      'transfer_queries_total':len(query_transfer),
      'learned_language_examples':len(learner.language.examples),
      'distractor_predicates':5000,'distractor_first_status':s1['status'],
      'distractor_first_ms':stress_first_ms,
      'distractor_grounding_status':stress_result['status'],'distractor_second_ms':stress_ms,
      'ambiguous_predicates':100,'ambiguous_status':ambiguous_result['status'],
      'ambiguous_active_grammar_changed':len(ambiguous.language.examples)!=before_amb,
      'ambiguous_possible':ambiguous_result.get('grounded_induction',{}).get('possible'),
      'ambiguous_ms':ambiguous_ms,
      'open_control':learner.respond('Resume este texto y compara sus dos ideas principales.')['status'],
    }

def recurrence_learning():
    seq_lag3=[0,1,1]
    for _ in range(3,11):seq_lag3.append(seq_lag3[-1]+seq_lag3[-3])
    trib=[0,0,1]
    for _ in range(3,11):trib.append(trib[-1]+trib[-2]+trib[-3])
    cases={
      'factorial':([(1,1),(2,2),(3,6),(4,24),(5,120),(6,720)],8),
      'fibonacci':([(0,0),(1,1),(2,1),(3,2),(4,3),(5,5),(6,8),(7,13)],12),
      'lag3':(list(enumerate(seq_lag3)),12),
      'tribonacci':(list(enumerate(trib)),12),
    }
    out={}
    for name,(vals,probe) in cases.items():
        p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=3)
        for x,y in vals:p.add_example(name,(x,),y)
        rep,t=ms(lambda:p.fit(name))
        out[name]={'status':rep['status'],'recurrence_discovered':rep.get('recurrence_discovered',False),
                   'programs':rep.get('programs',[])[:4],'fit_ms':t,'probe':probe,'prediction':p.predict(name,(probe,))['value']}
    # Control outside current meta-DSL: order-4 Tetranacci while max learned lag is 3.
    tet=[0,0,0,1]
    for _ in range(4,15):tet.append(sum(tet[-4:]))
    p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=3)
    for n,y in enumerate(tet):p.add_example('order4',(n,),y)
    rep,t=ms(lambda:p.fit('order4'))
    out['order4_control']={'status':rep['status'],'search_complete':rep['search_complete'],'fit_ms':t,
                           'recurrence_discovered':rep.get('recurrence_discovered',False)}
    return out

def abstraction_transfer():
    train=[(2,3,5),(4,5,7),(3,7,2),(5,2,9),(7,4,6),(8,3,1),(9,6,4)]
    families={
      'mul':lambda a:a[0]*a[1],
      'sub':lambda a:a[0]-a[1],
      'add':lambda a:a[0]+a[1],
      'max':lambda a:max(a[0],a[1]),
      'min':lambda a:min(a[0],a[1]),
    }
    rng=random.Random(20260921)
    heldout=[]
    while len(heldout)<200:
        row=tuple(rng.randint(15,80) for _ in range(3))
        if row not in train:heldout.append(row)
    out={}
    for label,shared in families.items():
        rows={}
        for auto in (False,True):
            p=ProgramLearner(max_size=5,max_candidates=120000,max_seconds=5,
                             auto_abstraction=auto,auto_library_top_k=0)
            source_reports=[]
            for skill,sign in [('source_plus',1),('source_minus',-1)]:
                for a in train:p.add_example(skill,a,shared(a)+sign*a[2])
                source_reports.append(p.fit(skill,library=[]))
            p.auto_library_top_k=16
            for a in train:p.add_example('target',a,shared(a)+a[0])
            rep,t=ms(lambda:p.fit('target'))
            correct=0
            for a in heldout:
                pred=p.predict('target',a)
                correct += pred.get('value')==shared(a)+a[0]
            rows['with_abstraction' if auto else 'control']={
              'status':rep['status'],'fit_ms':t,'candidates':rep['candidates'],
              'program_size':rep.get('size'),'programs':rep.get('programs',[]),
              'heldout_correct':correct,'heldout_total':len(heldout),
              'abstractions':[dict(name=k,**v) for k,v in p.abstractions.items()],
              'source_programs':[r.get('programs',[]) for r in source_reports]
            }
        c=rows['control'];a=rows['with_abstraction']
        rows['candidate_reduction']=c['candidates']-a['candidates']
        rows['candidate_ratio']=c['candidates']/max(1,a['candidates'])
        out[label]=rows

    # Harder decision test: with search depth capped at 3, the memory-only
    # control cannot express the target, while a learner-created primitive can.
    def constrained(auto):
        p=ProgramLearner(max_size=5,max_candidates=120000,max_seconds=5,
                         auto_abstraction=auto,auto_library_top_k=0)
        shared=families['sub']
        for skill,sign in [('source_plus',1),('source_minus',-1)]:
            for a in train:p.add_example(skill,a,shared(a)+sign*a[2])
            p.fit(skill,library=[])
        p.max_size=3;p.auto_library_top_k=16
        for a in train:p.add_example('target',a,shared(a)+a[0])
        rep=p.fit('target')
        return {'status':rep['status'],'candidates':rep['candidates'],'programs':rep.get('programs',[]),
                'abstractions':[dict(name=k,**v) for k,v in p.abstractions.items()]}
    out['bounded_search_control']={'control':constrained(False),'with_abstraction':constrained(True)}

    # Parametric transfer: sources expose multiplication on x0,x1 in arity-3
    # tasks; the held-out target uses the learned primitive on x2,x3 in arity 4.
    source=train
    target4=[(2,3,5,7),(4,5,7,2),(3,7,2,9),(5,2,9,4),(7,4,6,3),(8,3,1,5)]
    def parametric(auto):
        p=ProgramLearner(max_size=5,max_candidates=120000,max_seconds=5,
                         auto_abstraction=auto,auto_library_top_k=0)
        for skill,sign in [('source_plus',1),('source_minus',-1)]:
            for a in source:p.add_example(skill,a,a[0]*a[1]+sign*a[2])
            p.fit(skill,library=[])
        p.max_size=3;p.auto_library_top_k=16
        for a in target4:p.add_example('target4',a,a[2]*a[3]+a[0])
        rep,t=ms(lambda:p.fit('target4'))
        rng2=random.Random(91822);correct=0
        for _ in range(200):
            a=tuple(rng2.randint(20,90) for _ in range(4))
            pred=p.predict('target4',a)
            correct += pred.get('value')==a[2]*a[3]+a[0]
        return {'status':rep['status'],'fit_ms':t,'candidates':rep['candidates'],
                'programs':rep.get('programs',[]),'heldout_correct':correct,'heldout_total':200,
                'abstractions':[dict(name=k,**v) for k,v in p.abstractions.items()]}
    out['parametric_cross_arity']={'control':parametric(False),'with_abstraction':parametric(True)}
    return out

def sqlite_scale(n=200000, queries=500):
    dbpath=OUT/'facts_scale.db'
    for suffix in ('','-wal','-shm'):
        try:(Path(str(dbpath)+suffix)).unlink()
        except FileNotFoundError:pass
    kb=SQLiteKnowledgeBase(dbpath)
    t=time.perf_counter()
    kb.bulk_add((Atom('located',(f'entity{i}',f'place{i%1000}')) for i in range(n)),source='scale',commit_every=10000)
    ingest_ms=(time.perf_counter()-t)*1000
    rng=random.Random(9001);times=[];correct=0
    for _ in range(queries):
        i=rng.randrange(n);t0=time.perf_counter();q=Engine(kb,max_work=100).query(Atom('located',(f'entity{i}','?x')));times.append((time.perf_counter()-t0)*1000)
        correct += bool(q['answers']) and q['answers'][0].atom.args[1]==f'place{i%1000}'
    size=dbpath.stat().st_size
    stats=kb.stats();kb.close()
    for suffix in ('','-wal','-shm'):
        try: Path(str(dbpath)+suffix).unlink()
        except FileNotFoundError: pass
    return {'facts':n,'queries':queries,'correct_queries':correct,'ingest_ms':ingest_ms,
            'median_query_ms':statistics.median(times),'p95_query_ms':sorted(times)[int(.95*len(times))-1],
            'db_bytes':size,'bytes_per_fact_file':size/n,'stats':stats}

def main():
    results={'environment':{'python':platform.python_version(),'platform':platform.platform(),'cpu_count':os.cpu_count()},
             'numeric_dag':numeric_dag(),
             'numeric_auto_router':numeric_auto_router(),
             'numeric_semantic_router':numeric_semantic_router(),
             'relational_router':relational_router(),
             'closure_scale':closure_scale(),
             'language':language_composition(),
             'grounded_language_learning':grounded_language_learning(),
             'recurrence_learning':recurrence_learning(),
             'abstraction_transfer':abstraction_transfer(),
             'sqlite_scale':sqlite_scale()}
    (OUT/'v3_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
