from __future__ import annotations
import hashlib,json,random,statistics
from pathlib import Path
from time import perf_counter
from leobot.bot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v34_symbolic_world.json'
F=lambda *x:tuple(x)
def S(*x):return set(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def train_full(bot:Bot, failures=True):
    bot.symbolic.min_support=3;bot.symbolic.goal_min_support=2
    move_success=[('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','cuarto','laboratorio')]
    pick_success=[('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]
    reports=[]
    for person,src,dst in move_success:
        before=S(F('at',person,src),F('road',src,dst),F('autorizado',person),F('person',person),F('place',src),F('place',dst))
        after=(before-{F('at',person,src)})|{F('at',person,dst)}
        reports.append(bot.observe_symbolic_transition(f'Mueve a {person} de {src} a {dst}.',before,after))
    if failures:
        before=S(F('at','lila','patio'),F('autorizado','lila'),F('person','lila'),F('place','patio'),F('place','taller'))
        reports.append(bot.observe_symbolic_transition('Mueve a lila de patio a taller.',before,before))
        before=S(F('road','cocina','plaza'),F('autorizado','hugo'),F('person','hugo'),F('at','hugo','cuarto'),F('place','cocina'),F('place','plaza'),F('place','cuarto'))
        reports.append(bot.observe_symbolic_transition('Mueve a hugo de cocina a plaza.',before,before))
    for person,item,loc in pick_success:
        before=S(F('at',person,loc),F('item_at',item,loc),F('entrenado',person),F('person',person),F('item',item),F('place',loc))
        after=(before-{F('item_at',item,loc)})|{F('holding',person,item)}
        reports.append(bot.observe_symbolic_transition(f'{person} toma {item} en {loc}.',before,after))
    if failures:
        before=S(F('at','diego','garaje'),F('entrenado','diego'),F('person','diego'),F('item','mapa'),F('place','garaje'))
        reports.append(bot.observe_symbolic_transition('diego toma mapa en garaje.',before,before))
        before=S(F('item_at','carta','salon'),F('entrenado','eva'),F('person','eva'),F('item','carta'),F('place','salon'),F('at','eva','patio'),F('place','patio'))
        reports.append(bot.observe_symbolic_transition('eva toma carta en salon.',before,before))
    bot.observe_symbolic_goal('Logra que Ana tenga caja.',S(F('holding','ana','caja')))
    bot.observe_symbolic_goal('Logra que Bruno tenga libro.',S(F('holding','bruno','libro')))
    return reports

class EpisodicControl:
    def __init__(self):self.transitions={};self.goals={}
    def observe(self,text,before,after):self.transitions[(text,tuple(sorted(before)))]=frozenset(after)
    def execute(self,text,before):return self.transitions.get((text,tuple(sorted(before))))

def train_episodic(ctrl):
    # Same successful experience content, but only exact episodes are remembered.
    for person,src,dst in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','cuarto','laboratorio')]:
        before=S(F('at',person,src),F('road',src,dst),F('autorizado',person),F('person',person),F('place',src),F('place',dst));after=(before-{F('at',person,src)})|{F('at',person,dst)}
        ctrl.observe(f'Mueve a {person} de {src} a {dst}.',before,after)
    for person,item,loc in [('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]:
        before=S(F('at',person,loc),F('item_at',item,loc),F('entrenado',person),F('person',person),F('item',item),F('place',loc));after=(before-{F('item_at',item,loc)})|{F('holding',person,item)}
        ctrl.observe(f'{person} toma {item} en {loc}.',before,after)

def world(i,length,noise=0):
    p=f'persona{i}';item=f'paquete{i}';locs=[f'lugar{i}_{j}' for j in range(length+1)]
    facts={F('at',p,locs[0]),F('item_at',item,locs[-1]),F('person',p),F('item',item)}|{F('place',x) for x in locs}
    facts|={F('road',locs[j],locs[j+1]) for j in range(length)}
    for j in range(noise):facts.add(F('ruido',f'n{i}_{j}',f'v{i}_{j}'))
    return p,item,locs,facts


def verify_reference(state,steps,person,item):
    cur=set(state)
    for step in steps:
        b=step.get('binding',{});op=step.get('operator','')
        if op.startswith('mueve a '):
            a,src,dst=b.get('<e0>'),b.get('<e1>'),b.get('<e2>')
            if F('at',a,src) not in cur or F('road',src,dst) not in cur:return False
            cur.remove(F('at',a,src));cur.add(F('at',a,dst))
        elif ' toma ' in op:
            a,obj,loc=b.get('<e0>'),b.get('<e1>'),b.get('<e2>')
            if F('at',a,loc) not in cur or F('item_at',obj,loc) not in cur:return False
            cur.remove(F('item_at',obj,loc));cur.add(F('holding',a,obj))
        else:return False
    return F('holding',person,item) in cur

def transfer(seed=3401):
    full=Bot();positive=Bot();train_full(full,True);train_full(positive,False)
    episodic=EpisodicControl();train_episodic(episodic)
    rng=random.Random(seed);scores={'full':0,'independent_reference_valid':0,'positive_only_ablation':0,'episodic_memory':0};steps=[];lat=[];samples=[]
    for i in range(200):
        length=rng.randint(1,4);p,item,locs,state=world(i,length,noise=rng.randint(0,8));text=f'Logra que {p} tenga {item}.'
        t=perf_counter();out=full.plan_symbolic_goal(text,state,max_steps=5,max_nodes=5000);lat.append((perf_counter()-t)*1e6)
        scores['full']+=out.get('status')=='plan_found' and F('holding',p,item) in out.get('result',())
        scores['independent_reference_valid']+=out.get('status')=='plan_found' and verify_reference(state,out.get('steps',[]),p,item)
        po=positive.plan_symbolic_goal(text,state,max_steps=5,max_nodes=5000);scores['positive_only_ablation']+=po.get('status')=='plan_found'
        scores['episodic_memory']+=episodic.execute(text,state) is not None
        if out.get('status')=='plan_found':steps.append(len(out['steps']))
        if len(samples)<4:samples.append({'text':text,'path_len':length,'status':out.get('status'),'actions':[x['action'] for x in out.get('steps',[])]})
    return {'heldout':200,'scores':scores,'median_us':statistics.median(lat),'p95_us':sorted(lat)[int(.95*len(lat))-1],
            'median_steps':statistics.median(steps),'operators':full.symbolic.operators(),'positive_only_operators':positive.symbolic.operators(),'samples':samples}

def distractor_scale():
    b=Bot();train_full(b,True);rows=[]
    for noise in (0,1000,5000,10000):
        p,item,locs,state=world(9000+noise,2,noise=noise);text=f'Logra que {p} tenga {item}.'
        times=[];last=None
        for _ in range(7):
            t=perf_counter();last=b.plan_symbolic_goal(text,state,max_steps=4,max_nodes=500);times.append((perf_counter()-t)*1e6)
        rows.append({'noise_facts':noise,'total_facts':len(state),'median_us':statistics.median(times),'status':last.get('status'),'steps':len(last.get('steps',[]))})
    return rows

def persistence():
    import tempfile
    from pathlib import Path
    b=Bot();train_full(b,True)
    with tempfile.TemporaryDirectory() as td:
        pth=Path(td)/'s.json';b.save(pth);c=Bot.load(pth)
        p,item,locs,state=world(777,2);out=c.plan_symbolic_goal(f'Logra que {p} tenga {item}.',state,max_steps=4,max_nodes=500)
        return {'status':out.get('status'),'goal_reached':F('holding',p,item) in out.get('result',()),'operators':len(c.symbolic.operators())}

def main():
    frozen=code_hash();t=perf_counter()
    result={'version':'0.3.4','experiment':'symbolic_action_model_induction_and_cross_operator_planning','code_hash_before':frozen,
            'transfer':transfer(),'distractor_scale':distractor_scale(),'persistence':persistence()}
    result['code_hash_after']=code_hash();result['code_unchanged_during_evaluation']=result['code_hash_after']==frozen;result['elapsed_s']=perf_counter()-t
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
