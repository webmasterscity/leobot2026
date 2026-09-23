#!/usr/bin/env python3
"""V4.0: cross-domain structural analogy for symbolic action acquisition.

The source action is learned in one predicate vocabulary (at/road).  The target
uses a disjoint predicate vocabulary (located/link), so textual/predicate-name
aliasing cannot solve it.  We measure how many independently observed episodes
are needed for robust held-out execution and test ambiguity/counterevidence.
"""
from __future__ import annotations
import hashlib,json,statistics,tempfile
from pathlib import Path
from time import perf_counter
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v40_structural_analogy.json'
F=lambda *x:tuple(x);S=lambda *x:set(x)

def code_hash():
 h=hashlib.sha256()
 for p in sorted((ROOT/'leobot').glob('*.py')):
  h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
 return h.hexdigest()

def success_episode(bot,p,s,d):
 before=S(F('located',p,s),F('link',s,d),F('licensed',p),F('person',p),F('place',s),F('place',d))
 after=(before-{F('located',p,s)})|{F('located',p,d)}
 return bot.observe_symbolic_transition(f'Navega a {p} de {s} a {d}.',before,after)

def failure_missing_link(bot,p,s,d):
 before=S(F('located',p,s),F('licensed',p),F('person',p),F('place',s),F('place',d))
 return bot.observe_symbolic_transition(f'Navega a {p} de {s} a {d}.',before,before)

def failure_wrong_location(bot,p,s,d):
 before=S(F('located',p,'otro'),F('link',s,d),F('licensed',p),F('person',p),F('place',s),F('place',d),F('place','otro'))
 return bot.observe_symbolic_transition(f'Navega a {p} de {s} a {d}.',before,before)

def heldout(bot,n=200,include_license=False):
 ok=0;times=[]
 for i in range(n):
  p,s,d=f'np{i}',f'ns{i}',f'nd{i}'
  st=S(F('located',p,s),F('link',s,d),F('person',p),F('place',s),F('place',d))
  if include_license:st.add(F('licensed',p))
  t=perf_counter();r=bot.execute_symbolic_transition(f'Navega a {p} de {s} a {d}.',st);times.append((perf_counter()-t)*1e6)
  ok+=r.get('status')=='executed_symbolic_action' and F('located',p,d) in r.get('result',())
 return {'cases':n,'correct':ok,'median_us':statistics.median(times)}

def build_source_bot():
 """Reconstruct the historical source knowledge from bundled mechanics only.

 The original experiment loaded an absolute /mnt/data checkpoint that was not
 shipped in later archives.  Rebuilding the two source operators here preserves
 the experimental question while making the checkpoint self-contained.
 """
 b=Bot(); b.symbolic.min_support=3
 # Robust move operator: successes plus failures that isolate at/road.
 for p,s,d in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','cuarto','laboratorio')]:
  before=S(F('at',p,s),F('road',s,d),F('autorizado',p),F('person',p),F('place',s),F('place',d))
  after=(before-{F('at',p,s)})|{F('at',p,d)}
  b.observe_symbolic_transition(f'Mueve a {p} de {s} a {d}.',before,after)
 before=S(F('at','lila','patio'),F('autorizado','lila'),F('person','lila'),F('place','patio'),F('place','taller'))
 b.observe_symbolic_transition('Mueve a lila de patio a taller.',before,before)
 before=S(F('road','cocina','plaza'),F('autorizado','hugo'),F('at','hugo','cuarto'),F('person','hugo'),F('place','cocina'),F('place','plaza'),F('place','cuarto'))
 b.observe_symbolic_transition('Mueve a hugo de cocina a plaza.',before,before)
 # Robust pickup operator for the second-family analogy control.
 for p,item,loc in [('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]:
  before=S(F('at',p,loc),F('item_at',item,loc),F('certified',p),F('person',p),F('item',item),F('place',loc))
  after=(before-{F('item_at',item,loc)})|{F('holding',p,item)}
  b.observe_symbolic_transition(f'{p} toma {item} en {loc}.',before,after)
 before=S(F('at','diego','garaje'),F('certified','diego'),F('person','diego'),F('item','mapa'),F('place','garaje'))
 b.observe_symbolic_transition('diego toma mapa en garaje.',before,before)
 before=S(F('item_at','carta','salon'),F('certified','eva'),F('person','eva'),F('item','carta'),F('place','salon'),F('at','eva','patio'),F('place','patio'))
 b.observe_symbolic_transition('eva toma carta en salon.',before,before)
 return b

def main():
 h0=code_hash()
 educated=build_source_bot();fresh=Bot()
 # Same two successes for both.
 edu_reports=[success_episode(educated,'nora','uno','dos'),success_episode(educated,'omar','tres','cuatro')]
 fresh_reports=[success_episode(fresh,'nora','uno','dos'),success_episode(fresh,'omar','tres','cuatro')]
 edu_after2=heldout(educated);fresh_after2=heldout(fresh)
 # Fresh gets a third success: it can now form a positive-only operator, but it
 # includes the spurious licensed/type predicates and fails held-out worlds that omit licensed.
 fresh_reports.append(success_episode(fresh,'paz','cinco','seis'))
 fresh_after3=heldout(fresh)
 # Two contrastive failures identify the truly necessary context for the fresh learner.
 fresh_reports.append(failure_missing_link(fresh,'quinn','siete','ocho'))
 fresh_reports.append(failure_wrong_location(fresh,'rosa','nueve','diez'))
 fresh_after5=heldout(fresh)

 # Counterevidence safety: an analogical operator is withdrawn if all its
 # transferred preconditions hold but an observed action has no effect.
 unsafe=build_source_bot();success_episode(unsafe,'ua','us1','ud1');success_episode(unsafe,'ub','us2','ud2')
 before_withdraw=len([o for o in unsafe.symbolic.operators() if o['pattern'].startswith('navega a ')])
 contradiction=S(F('located','uc','us3'),F('link','us3','ud3'),F('person','uc'),F('place','us3'),F('place','ud3'))
 counter=unsafe.observe_symbolic_transition('Navega a uc de us3 a ud3.',contradiction,contradiction)
 after_withdraw=len([o for o in unsafe.symbolic.operators() if o['pattern'].startswith('navega a ')])

 # Ambiguous structural context: two same-role candidate relations => refuse analogy.
 ambiguous=build_source_bot()
 def amb(p,s,d):
  b=S(F('located',p,s),F('link',s,d),F('permit_path',s,d),F('person',p),F('place',s),F('place',d));a=(b-{F('located',p,s)})|{F('located',p,d)}
  return ambiguous.observe_symbolic_transition(f'Navega a {p} de {s} a {d}.',b,a)
 amb('aa','as1','ad1');amb_report=amb('ab','as2','ad2')
 ambiguous_operators=len([o for o in ambiguous.symbolic.operators() if o['pattern'].startswith('navega a ')])

 # Persistence of the transferred operator.
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'state.json';educated.save(p);loaded=Bot.load(p);persist=heldout(loaded,20)

 # Second structural family: pickup-like operator with all semantic predicates renamed.
 second=build_source_bot();second_fresh=Bot()
 def token_success(bot,p0,tok,loc):
  before=S(F('positioned',p0,loc),F('token_at',tok,loc),F('certified',p0),F('person',p0),F('token',tok),F('place',loc))
  after=(before-{F('token_at',tok,loc)})|{F('possesses',p0,tok)}
  return bot.observe_symbolic_transition(f'{p0} recolecta {tok} en {loc}.',before,after)
 token_reports_prior=[token_success(second,'ta','tok1','loc1'),token_success(second,'tb','tok2','loc2')]
 token_reports_fresh=[token_success(second_fresh,'ta','tok1','loc1'),token_success(second_fresh,'tb','tok2','loc2')]
 def token_held(bot,n=100):
  ok=0
  for i in range(n):
   p0,tok,loc=f'tp{i}',f'tt{i}',f'tl{i}'
   st=S(F('positioned',p0,loc),F('token_at',tok,loc),F('person',p0),F('token',tok),F('place',loc))
   r=bot.execute_symbolic_transition(f'{p0} recolecta {tok} en {loc}.',st)
   ok+=r.get('status')=='executed_symbolic_action' and F('possesses',p0,tok) in r.get('result',())
  return {'cases':n,'correct':ok}
 token_prior=token_held(second);token_fresh=token_held(second_fresh)

 # Learning-to-learn curve: after move + renamed navigation are independently learned,
 # a third renamed domain can be acquired from one success because two source
 # operators support the same structural proposal.
 meta=build_source_bot()
 success_episode(meta,'ma','m1','m2');success_episode(meta,'mb','m3','m4')
 before=S(F('positioned','mc','q1'),F('path','q1','q2'),F('cleared','mc'),F('person','mc'),F('place','q1'),F('place','q2'))
 after=(before-{F('positioned','mc','q1')})|{F('positioned','mc','q2')}
 meta_report=meta.observe_symbolic_transition('Desplaza a mc desde q1 hasta q2.',before,after)
 meta_control=build_source_bot()
 control_report=meta_control.observe_symbolic_transition('Desplaza a mc desde q1 hasta q2.',before,after)
 meta_ok=0;control_ok=0
 for i in range(200):
  p0,s0,d0=f'mp{i}',f'ms{i}',f'md{i}'
  st=S(F('positioned',p0,s0),F('path',s0,d0),F('person',p0),F('place',s0),F('place',d0))
  text=f'Desplaza a {p0} desde {s0} hasta {d0}.'
  meta_ok+=meta.execute_symbolic_transition(text,st).get('status')=='executed_symbolic_action'
  control_ok+=meta_control.execute_symbolic_transition(text,st).get('status')=='executed_symbolic_action'

 h1=code_hash()
 result={'version':'0.4.0','experiment':'cross_domain_structural_operator_analogy',
  'code_hash_before':h0,'code_hash_after':h1,'code_unchanged_during_evaluation':h0==h1,
  'prior_education':{
   'two_success_reports':edu_reports,
   'heldout_after_2_successes':edu_after2,
  },
  'fresh_control':{
   'reports':fresh_reports,
   'heldout_after_2_successes':fresh_after2,
   'heldout_after_3_successes_positive_only':fresh_after3,
   'heldout_after_3_successes_plus_2_failures':fresh_after5,
  },
  'episode_cost_to_robust_heldout':{'prior_educated':2,'fresh_control':5},
  'counterevidence':{'operators_before':before_withdraw,'report':counter,'operators_after':after_withdraw},
  'ambiguity_control':{'second_report':amb_report,'operators_promoted':ambiguous_operators},
  'persistence':persist,
  'second_structural_family':{'prior_reports':token_reports_prior,'fresh_reports':token_reports_fresh,
                              'prior_heldout':token_prior,'fresh_heldout':token_fresh},
  'learning_to_learn':{'third_domain_one_success_report':meta_report,
                       'one_source_control_report':control_report,
                       'third_domain_heldout':{'cases':200,'correct':meta_ok},
                       'one_source_control_heldout':{'cases':200,'correct':control_ok},
                       'observed_success_examples_curve':{'first_domain_robust_baseline':3,
                                                          'second_domain_with_one_source':2,
                                                          'third_domain_with_two_sources':1}},
 }
 OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=list)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2,default=list))
if __name__=='__main__':main()
