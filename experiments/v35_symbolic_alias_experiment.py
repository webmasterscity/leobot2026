from __future__ import annotations
import hashlib,json,random,statistics
from pathlib import Path
from time import perf_counter
from leobot.bot import Bot
from experiments.v34_symbolic_world_experiment import train_full,F,S
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results_v3'/'v35_symbolic_alias.json'


def _jsonable(x):
 if isinstance(x,(set,frozenset,tuple)):return [_jsonable(v) for v in x]
 if isinstance(x,list):return [_jsonable(v) for v in x]
 if isinstance(x,dict):return {k:_jsonable(v) for k,v in x.items()}
 return x

def code_hash():
 h=hashlib.sha256()
 for p in sorted((ROOT/'leobot').glob('*.py')):h.update(p.name.encode());h.update(p.read_bytes())
 return h.hexdigest()

def teach_aliases(bot:Bot):
 reports=[]
 for person,src,dst in [('marta','patio','escuela'),('leo','garaje','parque')]:
  before=S(F('at',person,src),F('road',src,dst),F('person',person),F('place',src),F('place',dst));after=(before-{F('at',person,src)})|{F('at',person,dst)}
  reports.append(bot.observe_symbolic_transition(f'Desde {src} lleva a {person} hasta {dst}.',before,after))
 for person,item,loc in [('marta','mapa','deposito'),('leo','carta','archivo')]:
  before=S(F('at',person,loc),F('item_at',item,loc),F('person',person),F('item',item),F('place',loc));after=(before-{F('item_at',item,loc)})|{F('holding',person,item)}
  reports.append(bot.observe_symbolic_transition(f'En {loc}, {person} recoge {item}.',before,after))
 return reports

def transfer(seed=3501):
 full=Bot();train_full(full,True);reports=teach_aliases(full)
 scratch=Bot();teach_aliases(scratch)
 rng=random.Random(seed);scores={'prior_skill_alias_move':0,'scratch_move':0,'prior_skill_alias_pickup':0,'scratch_pickup':0};lat=[]
 for i in range(200):
  p=f'nueva{i}';src=f'origen{i}';dst=f'destino{i}'
  st=S(F('at',p,src),F('road',src,dst),F('person',p),F('place',src),F('place',dst))
  text=f'Desde {src} lleva a {p} hasta {dst}.';t=perf_counter();o=full.execute_symbolic_transition(text,st);lat.append((perf_counter()-t)*1e6)
  scores['prior_skill_alias_move']+=F('at',p,dst) in o.get('result',()) and o.get('status')=='executed_symbolic_action'
  scores['scratch_move']+=scratch.execute_symbolic_transition(text,st).get('status')=='executed_symbolic_action'
  loc=f'almacen{i}';item=f'objeto{i}';st2=S(F('at',p,loc),F('item_at',item,loc),F('person',p),F('item',item),F('place',loc))
  text2=f'En {loc}, {p} recoge {item}.';o2=full.execute_symbolic_transition(text2,st2)
  scores['prior_skill_alias_pickup']+=F('holding',p,item) in o2.get('result',()) and o2.get('status')=='executed_symbolic_action'
  scores['scratch_pickup']+=scratch.execute_symbolic_transition(text2,st2).get('status')=='executed_symbolic_action'
 # Give scratch one third success: it can then induce the raw operator, showing the advantage was acquisition cost.
 p,src,dst='tercero','muelle','torre';st=S(F('at',p,src),F('road',src,dst),F('person',p),F('place',src),F('place',dst));aft=(st-{F('at',p,src)})|{F('at',p,dst)}
 third=scratch.observe_symbolic_transition(f'Desde {src} lleva a {p} hasta {dst}.',st,aft)
 return {'alias_training_reports':reports,'learned_aliases':full.symbolic.aliases(),'heldout':200,'scores':scores,
         'median_move_us':statistics.median(lat),'scratch_third_support_report':third,
         'sample':_jsonable(full.execute_symbolic_transition('Desde casa lleva a Nora hasta plaza.',S(F('at','nora','casa'),F('road','casa','plaza'),F('person','nora'),F('place','casa'),F('place','plaza'))))}

def withdrawal():
 b=Bot();train_full(b,True);teach_aliases(b);before_aliases=len(b.symbolic.aliases())
 before=S(F('at','olga','cocina'),F('road','cocina','patio'),F('person','olga'),F('place','cocina'),F('place','patio'));after=before|{F('visited','olga','patio')}
 report=b.observe_symbolic_transition('Desde cocina lleva a Olga hasta patio.',before,after)
 return {'aliases_before':before_aliases,'counterevidence_report':report,'aliases_after':len(b.symbolic.aliases())}

def main():
 frozen=code_hash();t=perf_counter();r={'version':'0.3.5','experiment':'prior_symbolic_skill_accelerates_reordered_language_grounding','code_hash_before':frozen,
 'transfer':transfer(),'withdrawal':withdrawal()};r['code_hash_after']=code_hash();r['code_unchanged_during_evaluation']=r['code_hash_after']==frozen;r['elapsed_s']=perf_counter()-t
 OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
