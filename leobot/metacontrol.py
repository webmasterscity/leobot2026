"""Domain-neutral meta-control for selecting cognitive strategies and evidence.

V6.6 adds two conservative mechanisms inspired by resource-bounded reasoning and
active inference, without making either mechanism an oracle:

* ``CognitiveBudget`` keeps recency-sensitive priority, evidence-sensitive
  durability, long-run quality, and observed cost for strategy attempts.  It can
  *reorder* strategies, but it cannot delete the deterministic fallbacks owned by
  the caller.
* ``select_epistemic_action`` scores unlabeled experiments by expected
  information gain per declared cost.  It proposes an experiment only; the real
  environment/user must supply its outcome before any hypothesis can be learned.

No task words, predicate names, entities, answers, benchmark ids or source text
are stored here.  Callers supply scaled structural features only.
"""
from __future__ import annotations

from copy import deepcopy
from math import exp, log1p, log2
from itertools import combinations
import json
import hashlib
from time import process_time
from .rbf import RBFStrategyRouter
from . import meta_operators, learner_dsl


class MetaController:
    VERSION = 12

    def __init__(self) -> None:
        # decision family -> exact signature -> strategy -> aggregates
        self.exact: dict[str, dict[str, dict[str, dict]]] = {}
        # decision family -> generic RBF router over structural feature vectors
        self.routers: dict[str, RBFStrategyRouter] = {}
        # decision family -> exact signature -> strategy -> resource budget
        self.budgets: dict[str, dict[str, dict[str, dict]]] = {}
        self.observations = 0
        self.clock = 0
        self.gaps: list[dict] = []
        self.max_gaps = 256
        # V6.7: bounded raw meta-experience used only to synthesize compact
        # structural *views* of a decision problem.  A view is a learned subset
        # of structural feature dimensions; it contains no domain words, ids or
        # answers and can only reorder safe strategies.
        self.history: dict[str, list[dict]] = {}
        self.max_history_per_family = 768
        self.invented_views: dict[str, dict] = {}
        # V7.0: synthesis checkpoints keep expensive meta-program searches
        # incremental while cheap validation of an already promoted program
        # still runs whenever new evidence arrives.
        self.program_search_checkpoints: dict[str, dict[str, int]] = {}
        # A compiled subrule is admitted only after independent decision
        # families learn the same structural truth partition.
        self.meta_primitives: dict[str, dict] = {}
        self.enable_meta_primitives = True
        self.meta_operators: dict[str, dict] = {}
        self.enable_meta_operator_invention = True
        self.aggregate_candidates_evaluated: dict[str, int] = {}
        # A contradicted aggregate is withdrawn immediately. Expensive broad
        # synthesis waits for a bounded amount of genuinely new experience.
        self.aggregate_retry_after: dict[str, int] = {}
        self.enable_meta_rivals = True
        self.meta_rivals: dict[str, list[dict]] = {}
        self.meta_probe_pending: dict[str, dict] = {}
        self.meta_rival_checkpoints: dict[str, int] = {}
        self.meta_rival_retry_after: dict[str, int] = {}
        self.enable_learner_synthesis = True
        self.meta_learners: dict[str, dict] = {}
        self.learner_synthesis_counts: dict[str, dict] = {}
        self.learner_synthesis_checkpoints: dict[str, int] = {}
        self.learner_retry_after: dict[str, int] = {}
        # A caller may cap acquisition search while still delivering every
        # observation through the normal interface. Exhaustion withdraws any
        # unresolved view so old evidence cannot become a confident answer.
        self.meta_search_cpu_limit_s: float | None = None
        self.meta_search_cpu_spent_s: dict[str, float] = {}
        self.meta_search_exhausted: dict[str, int] = {}

    @staticmethod
    def _feature_tuple(features) -> tuple[float, ...]:
        vals=tuple(float(v) for v in features)
        if not vals or len(vals)>16:
            raise ValueError('MetaController requiere entre 1 y 16 rasgos estructurales.')
        return vals

    @staticmethod
    def signature(features) -> str:
        vals=MetaController._feature_tuple(features)
        return ','.join(f'{v:.6g}' for v in vals)

    def _router(self, family: str) -> RBFStrategyRouter:
        fam=str(family).strip().lower()
        if not fam:
            raise ValueError('La familia de meta-control no puede estar vacía.')
        return self.routers.setdefault(fam,RBFStrategyRouter(tau=10.0,max_nodes_per_strategy=192,max_distance=0.60))

    def _update_budget(self, fam: str, sig: str, strategy: str, *, success: bool, cost: float) -> dict:
        """Update a bounded resource-allocation summary for one strategy.

        ``priority`` is deliberately recency-sensitive so a regime change can be
        noticed. ``quality`` is the long-run verified success rate, while
        ``durability`` rises with repeated independent observations.  None of
        these values claim truth; they only schedule computation.
        """
        self.clock += 1
        table=self.budgets.setdefault(fam,{}).setdefault(sig,{})
        row=table.setdefault(strategy,{
            'trials':0,'successes':0,'priority':0.5,'durability':0.0,
            'quality':0.5,'ema_cost':max(0.001,float(cost)),'last_tick':self.clock,
        })
        trials=int(row.get('trials',0))+1
        successes=int(row.get('successes',0))+int(bool(success))
        # Decay stale recent evidence slightly if this strategy has not been used.
        dt=max(1,self.clock-int(row.get('last_tick',self.clock)))
        recent=float(row.get('priority',0.5))*(0.985 ** max(0,dt-1))
        recent=0.72*recent + 0.28*(1.0 if success else 0.0)
        old_cost=max(0.001,float(row.get('ema_cost',cost)))
        ema_cost=0.80*old_cost + 0.20*max(0.001,float(cost))
        quality=(successes+1.0)/(trials+2.0)  # Laplace-smoothed, not certainty.
        durability=min(0.995,1.0-exp(-trials/5.0))
        # Priority is scheduling urgency, discounted mildly by historically high cost.
        priority=max(0.0,min(1.0,recent/(1.0+0.04*log1p(ema_cost))))
        row.update(trials=trials,successes=successes,priority=priority,
                   durability=durability,quality=quality,ema_cost=ema_cost,
                   last_tick=self.clock)
        return row

    def observe(self, family: str, features, strategy: str, *, success: bool,
                cost: int | float = 1, failure_budget: int | float = 1) -> dict:
        fam=str(family).strip().lower(); strategy=str(strategy).strip()
        vals=self._feature_tuple(features)
        if not fam or not strategy:
            return {'status':'meta_control_observation_ignored','reason':'missing_family_or_strategy'}
        sig=self.signature(vals)
        table=self.exact.setdefault(fam,{}).setdefault(sig,{})
        row=table.setdefault(strategy,{'trials':0,'success':0,'cost':0.0})
        row['trials']=int(row.get('trials',0))+1
        row['success']=int(row.get('success',0))+int(bool(success))
        row['cost']=float(row.get('cost',0.0))+max(0.0,float(cost))
        budget=self._update_budget(fam,sig,strategy,success=bool(success),cost=max(0.001,float(cost)))
        self.observations += 1
        # RBFStrategyRouter expects integer candidate-like costs. Preserve
        # relative work at micro-resolution without coupling it to wall time.
        scaled=max(0,int(round(float(cost)*1000.0)))
        fb=max(1,int(round(float(failure_budget)*1000.0)))
        self._router(fam).observe(vals,strategy,success=bool(success),
                                  candidates=scaled,failure_budget=fb)
        if success:
            self._resolve_meta_probe(fam,sig,strategy)
        self._record_history(fam,vals,strategy,success=bool(success),cost=max(0.001,float(cost)))
        return {'status':'meta_control_observation_recorded','family':fam,
                'signature':sig,'strategy':strategy,'success':bool(success),
                'trials':row['trials'],'budget':deepcopy(budget)}


    @staticmethod
    def _transform_atom_value(features, atom):
        """Evaluate one bounded, domain-neutral meta-DSL atom.

        V6.8 deliberately starts with *relational* observables rather than task
        vocabulary: ``cmp(a,b)`` returns -1/0/+1 according to the ordering of
        two existing structural features.  The result is invariant to common
        translations and absolute magnitudes, so it can generalize where raw
        feature projections cannot.  More operators may be added only through
        the same held-out validation discipline.
        """
        vals=tuple(float(v) for v in features)
        op=str(atom.get('op','')) if isinstance(atom,dict) else ''
        if op=='cmp':
            a=int(atom.get('a',-1)); b=int(atom.get('b',-1))
            if a<0 or b<0 or a>=len(vals) or b>=len(vals) or a==b:
                raise ValueError('Átomo cmp inválido.')
            d=vals[a]-vals[b]
            if abs(d)<=1e-12:
                return 0
            return -1 if d<0 else 1
        if op in ('raw_gt','delta_gt','absdelta_gt'):
            threshold=float(atom.get('threshold',0.0))
            if op=='raw_gt':
                a=int(atom.get('a',-1))
                if a<0 or a>=len(vals):
                    raise ValueError('Átomo raw_gt inválido.')
                value=vals[a]
            else:
                a=int(atom.get('a',-1)); b=int(atom.get('b',-1))
                if a<0 or b<0 or a>=len(vals) or b>=len(vals) or a==b:
                    raise ValueError('Átomo relacional inválido.')
                value=vals[a]-vals[b]
                if op=='absdelta_gt':
                    value=abs(value)
            return 1 if value>threshold else 0
        raise ValueError('Átomo de meta-DSL no soportado.')

    @classmethod
    def _transform_key(cls, features, atoms) -> str:
        out=[]
        for atom in atoms:
            value=cls._transform_atom_value(features,atom)
            out.append(str(value))
        return '|'.join(out)

    @staticmethod
    def _candidate_thresholds(values, *, limit: int = 8) -> list[float]:
        vals=sorted(set(float(v) for v in values))
        if len(vals)<2:
            return []
        mids=[(a+b)/2.0 for a,b in zip(vals,vals[1:]) if a!=b]
        if len(mids)<=limit:
            return mids
        # Deterministic quantile-like subsampling keeps the DSL search bounded.
        idxs=[]
        for k in range(limit):
            idx=round(k*(len(mids)-1)/max(1,limit-1))
            if idx not in idxs:
                idxs.append(idx)
        return [mids[i] for i in idxs]

    def _transform_atom_candidates(self, tasks: list[dict]) -> list[dict]:
        dims=len(tasks[0]['features']) if tasks else 0
        atoms=[]
        # Pure relational comparisons are tried first because they are maximally
        # invariant to absolute scale/translation and have no fitted parameter.
        for a,b in combinations(range(dims),2):
            atoms.append({'op':'cmp','a':a,'b':b})
        # Then permit a small fitted scalar boundary.  Thresholds are discovered
        # from meta-experience, not encoded for a domain.
        for a in range(dims):
            vals=[t['features'][a] for t in tasks]
            for th in self._candidate_thresholds(vals):
                atoms.append({'op':'raw_gt','a':a,'threshold':th})
        for a,b in combinations(range(dims),2):
            deltas=[t['features'][a]-t['features'][b] for t in tasks]
            for th in self._candidate_thresholds(deltas):
                atoms.append({'op':'delta_gt','a':a,'b':b,'threshold':th})
            absd=[abs(x) for x in deltas]
            for th in self._candidate_thresholds(absd):
                atoms.append({'op':'absdelta_gt','a':a,'b':b,'threshold':th})
        return atoms

    @classmethod
    def _predicate_value(cls, features, predicate) -> int:
        """Evaluate one boolean predicate built from an existing meta-DSL atom.

        V6.9 does not add task-specific predicates.  It converts the categorical
        output of a generic structural atom into a boolean test, so several such
        tests can be composed into a tiny conditional program.
        """
        if not isinstance(predicate,dict) or predicate.get('op')!='atom_eq':
            raise ValueError('Predicado de meta-programa no soportado.')
        atom=predicate.get('atom')
        expected=predicate.get('value')
        return 1 if cls._transform_atom_value(features,atom)==expected else 0

    def _program_predicate_candidates(self, tasks: list[dict], *, limit: int = 128) -> list[dict]:
        """Create a bounded, domain-neutral predicate vocabulary from atoms.

        ``cmp`` is categorical (-1/0/+1), while fitted threshold atoms are already
        binary.  Rank comparisons by how stable and small their relative gap is
        over the observed feature ranges.  This uses no outcome labels: a relation
        that remains meaningful while its operands move is a better candidate for
        transfer than a transient comparison of unrelated magnitudes.  Truth
        columns and their complements describe the same binary partition, so only
        the best representative of each is kept before the CPU-bound search.
        """
        if not tasks:
            return []
        features=[t['features'] for t in tasks]
        dims=len(features[0]); n=len(features)
        ranges=[max(f[i] for f in features)-min(f[i] for f in features)
                for i in range(dims)]
        full_mask=(1 << n)-1
        candidates={}
        for atom in self._transform_atom_candidates(tasks):
            vals=[self._transform_atom_value(f,atom) for f in features]
            observed=sorted(set(vals))
            targets=observed if atom.get('op')=='cmp' else ([1] if 1 in observed else [])
            if atom['op']=='cmp':
                a=atom['a']; b=atom['b']
                gaps=sorted(abs(f[a]-f[b]) for f in features)
                typical_gap=gaps[n//2]
                scale=max(ranges[a],ranges[b],typical_gap,1e-12)
                # Neither position nor task winner participates in this score.
                structure=(typical_gap/scale)+(gaps[-1]-gaps[0])/scale
            for target in targets:
                truth=sum(1 << i for i,v in enumerate(vals) if v==target)
                if not truth or truth==full_mask:
                    continue
                partition=min(truth,full_mask ^ truth)
                balance=abs(truth.bit_count()/n-0.5)
                # Prefer parameter-free relations; within each kind, choose
                # stable and well-supported partitions independent of dimension.
                priority=(0,structure+balance) if atom['op']=='cmp' else (1,balance)
                previous=candidates.get(partition)
                if previous is None or priority<previous[0]:
                    candidates[partition]=(priority,{'op':'atom_eq',
                                                      'atom':deepcopy(atom),'value':target})
        # On equal scores, use the observed partition, not feature indices.
        ranked=sorted(candidates.items(),key=lambda entry:(entry[1][0],entry[0]))
        return [candidate[1] for _,candidate in ranked[:max(8,int(limit))]]

    @staticmethod
    def _subrule_descriptors(view: dict) -> list[dict]:
        """Extract minimal two-test partitions from a validated program.

        A third predicate may be redundant over the observed buckets.  Project
        the learned truth table and require every collapsed branch to agree;
        this avoids treating a genuinely three-way rule as a two-way primitive.
        """
        predicates=view.get('predicates',())
        if view.get('kind')!='feature_program' or not 2<=len(predicates)<=3:
            return []
        output=[]
        for pair in combinations(range(len(predicates)),2):
            if any(predicates[i].get('op')!='atom_eq' or
                   predicates[i].get('atom',{}).get('op')!='cmp' for i in pair):
                continue
            order=sorted(pair,key=lambda i:(predicates[i]['atom']['a'],
                                            predicates[i]['atom']['b']))
            positions=[int(predicates[i]['atom'][side]) for i in order
                       for side in ('a','b')]
            if len(set(positions))!=4:
                continue
            if any(predicates[i]['value'] not in (-1,1) for i in order):
                continue
            origin=min(positions)
            template=[{'a':int(predicates[i]['atom']['a'])-origin,
                       'b':int(predicates[i]['atom']['b'])-origin,
                       'value':-1} for i in order]
            span=max(positions)-origin+1
            if span>16:
                continue
            winners={};supports={};conflict=False
            for key,row in (view.get('buckets') or {}).items():
                bits=key.split('|')
                if len(bits)!=len(predicates) or any(bit not in ('0','1') for bit in bits):
                    continue
                if float(row.get('confidence',0))<0.8:
                    continue
                # For non-equal comparisons, "greater" and "less" encode
                # complementary bits. Canonicalize their orientation before
                # comparing independent programs; equality later abstains.
                projected=''.join(str(int(bits[i]) ^
                                      int(predicates[i]['value']==1)) for i in order)
                label=str(row.get('winner'))
                if projected in winners and winners[projected]!=label:
                    conflict=True;break
                winners[projected]=label
                supports[projected]=supports.get(projected,0)+int(row.get('support',0))
            keys=('00','01','10','11')
            if conflict or any(supports.get(key,0)<2 for key in keys):
                continue
            if len(set(winners.values()))!=2:
                continue
            reference=winners['00']
            truth=[int(winners[key]!=reference) for key in keys]
            signature=json.dumps({'template':template,'truth':truth},sort_keys=True,
                                 separators=(',',':'))
            output.append({'signature':signature,'template':template,
                           'truth':truth,'span':span,'origin':origin})
        return output

    def _reconcile_meta_primitives(self) -> None:
        """Rebuild compiled pieces from current evidence and revoke dependents."""
        grouped={}
        for family,view in sorted(self.invented_views.items()):
            for descriptor in self._subrule_descriptors(view):
                origin=descriptor['origin']
                if any(task['features'][row['a']+origin]==
                       task['features'][row['b']+origin]
                       for task in self._meta_tasks(family)
                       for row in descriptor['template']):
                    continue
                row=grouped.setdefault(descriptor['signature'],{**descriptor,'sources':[]})
                # A second label for exactly the same examples is not independent
                # confirmation. Structural equivalence is tested separately.
                evidence={task['features'] for task in self._meta_tasks(family)}
                if not evidence:
                    continue
                if any(evidence & {task['features'] for task in self._meta_tasks(source)}
                       for source in row['sources']):
                    continue
                row['sources'].append(family)
        self.meta_primitives={key:row for key,row in grouped.items()
                              if len(row['sources'])>=2}
        for family,view in list(self.invented_views.items()):
            if (view.get('kind')=='macro_program' and
                    view.get('primitive') not in self.meta_primitives):
                self.invented_views.pop(family,None)
        self._reconcile_meta_operators()

    def _reconcile_meta_operators(self) -> None:
        """Keep only operators backed by independently learned source views."""
        supported={}
        for family,view in sorted(self.invented_views.items()):
            if (view.get('kind')!='aggregate_program' or
                    view.get('operator_dependency')):
                continue
            spec=view.get('spec')
            if not isinstance(spec,dict):
                continue
            identifier=meta_operators.operator_key(spec)
            row=supported.setdefault(identifier,{'kind':'fold_boolean',
                                                   'reduce':spec.get('reduce'),
                                                   'sources':[]})
            row['sources'].append(family)
        self.meta_operators=supported
        for family,view in list(self.invented_views.items()):
            if (view.get('kind')=='aggregate_program' and
                    view.get('operator_dependency') and
                    view['operator_dependency'] not in supported):
                self.invented_views.pop(family,None)
                self.meta_rivals.pop(family,None)
        self._reconcile_meta_learners()

    @staticmethod
    def _learner_key(program: dict) -> str:
        encoded=json.dumps(program,sort_keys=True,separators=(',',':'))
        return 'learner_'+hashlib.blake2b(encoded.encode(),digest_size=8).hexdigest()

    def _reconcile_meta_learners(self) -> None:
        """Retain declarative learners only while their source views survive."""
        supported={}
        for family,view in sorted(self.invented_views.items()):
            if (view.get('kind')!='learner_product' or
                    view.get('learner_dependency')):
                continue
            program=view.get('learner_program')
            if not isinstance(program,dict):
                continue
            try:
                learner_dsl.validate(program)
            except (TypeError,ValueError,KeyError):
                continue
            key=self._learner_key(program)
            row=supported.setdefault(key,{'program':deepcopy(program),'sources':[]})
            row['sources'].append(family)
        self.meta_learners=supported
        for family,view in list(self.invented_views.items()):
            if (view.get('kind')=='learner_product' and
                    view.get('learner_dependency') and
                    view['learner_dependency'] not in supported):
                self.invented_views.pop(family,None)
                self.meta_rivals.pop(family,None)

    def _resolve_meta_probe(self, family: str, signature: str, winner: str) -> None:
        """A real successful observation can falsify a pending rival view."""
        pending=self.meta_probe_pending.get(family)
        if not pending or pending.get('signature')!=signature:
            return
        self.meta_probe_pending.pop(family,None)
        primary=self.invented_views.get(family)
        rivals=self.meta_rivals.get(family,[])
        if not primary or len(rivals)!=1:
            return
        predictions=pending.get('predictions',())
        if len(predictions)!=2:
            return
        if predictions[0]!=winner and predictions[1]==winner:
            self.invented_views[family]=rivals[0]
            self.meta_rivals.pop(family,None)
        elif predictions[1]!=winner and predictions[0]==winner:
            self.meta_rivals.pop(family,None)
        elif predictions[0]!=winner and predictions[1]!=winner:
            self.invented_views.pop(family,None)
            self.meta_rivals.pop(family,None)
        else:
            return
        self.meta_rival_retry_after[family]=len(self._meta_tasks(family))+32
        self._reconcile_meta_operators()

    @classmethod
    def _meta_primitive_value(cls, features, primitive: dict, start: int) -> int | None:
        bits=[]
        for row in primitive['template']:
            atom={'op':'cmp','a':start+int(row['a']),'b':start+int(row['b'])}
            value=cls._transform_atom_value(features,atom)
            if value==0:
                return None
            bits.append(int(value==row['value']))
        return int(primitive['truth'][2*bits[0]+bits[1]])

    def _invent_macro_view_from_tasks(self, family: str, tasks: list[dict]) -> dict:
        """Search a bounded outer program over acquired, reusable subrules."""
        if not self.enable_meta_primitives or not self.meta_primitives or len(tasks)<16:
            return {'status':'macro_program_unavailable'}
        width=len(tasks[0]['features'])
        if any(len(task['features'])!=width for task in tasks):
            return {'status':'macro_program_incompatible_features'}
        majority=self._mode_winner(tasks)
        evaluated=0; best=None
        for identifier,primitive in sorted(self.meta_primitives.items()):
            starts=list(range(width-int(primitive['span'])+1))
            for left,right in combinations(starts,2):
                if evaluated>=32:
                    break
                evaluated+=1
                pairs=[(self._meta_primitive_value(task['features'],primitive,left),
                        self._meta_primitive_value(task['features'],primitive,right))
                       for task in tasks]
                if any(a is None or b is None for a,b in pairs):
                    continue
                keys=[f'{a}|{b}' for a,b in pairs]
                counts={}
                for task,key in zip(tasks,keys):
                    row=counts.setdefault(key,{})
                    winner=task['winner'];row[winner]=row.get(winner,0)+1
                if len(counts)<4:
                    continue
                covered=correct=baseline_correct=0
                for task,key in zip(tasks,keys):
                    available={label:n-int(label==task['winner'])
                               for label,n in counts[key].items()}
                    available={label:n for label,n in available.items() if n>0}
                    if not available:
                        continue
                    prediction=min(available,key=lambda label:(-available[label],str(label)))
                    covered+=1;correct+=int(prediction==task['winner'])
                    baseline_correct+=int(majority==task['winner'])
                coverage=covered/len(tasks);accuracy=correct/max(1,covered)
                gain=accuracy-baseline_correct/max(1,covered)
                if coverage<0.70 or accuracy<0.90 or gain<0.15:
                    continue
                # Both chronological halves must predict the other half.  A
                # proxy that only marks the acquisition epoch is insufficient.
                temporal=[];cut=len(tasks)//2
                for train,test in ((range(cut),range(cut,len(tasks))),
                                   (range(cut,len(tasks)),range(cut))):
                    local={}
                    for i in train:
                        row=local.setdefault(keys[i],{})
                        w=tasks[i]['winner'];row[w]=row.get(w,0)+1
                    seen=hits=0
                    for i in test:
                        row=local.get(keys[i])
                        if row:
                            pred=min(row,key=lambda w:(-row[w],str(w)))
                            seen+=1;hits+=int(pred==tasks[i]['winner'])
                    temporal.append((seen/max(1,len(test)),hits/max(1,seen)))
                if any(c<0.8 or a<0.95 for c,a in temporal):
                    continue
                buckets={}
                for key,row in counts.items():
                    winner=min(row,key=lambda w:(-row[w],str(w)))
                    support=sum(row.values());confidence=row[winner]/support
                    if support>=2 and confidence>=0.8:
                        buckets[key]={'winner':winner,'support':support,'confidence':confidence}
                if len(buckets)<4:
                    continue
                score=accuracy*coverage+0.5*gain
                candidate=(score,identifier,left,right,buckets,accuracy,coverage,gain)
                if best is None or candidate[:4]>best[:4]:
                    best=candidate
        if best is None:
            return {'status':'macro_program_rejected','candidates_evaluated':evaluated}
        score,identifier,left,right,buckets,accuracy,coverage,gain=best
        view={'kind':'macro_program','primitive':identifier,'starts':[left,right],
              'buckets':buckets,'accuracy':accuracy,'coverage':coverage,
              'gain_over_majority':gain,'score':score,'tasks':len(tasks),
              'candidates_evaluated':evaluated,
              'sources':list(self.meta_primitives[identifier]['sources'])}
        self.invented_views[family]=view
        return {'status':'macro_program_invented','family':family,**deepcopy(view)}

    def _invent_aggregate_view_from_tasks(self, family: str, tasks: list[dict],
                                          *, only_existing: bool = False) -> dict:
        """Interpret the acquired fold learner and attach operator provenance."""
        if not self.enable_meta_operator_invention or len(tasks)<24:
            return {'status':'aggregate_program_pending'}
        width=len(tasks[0]['features'])
        if any(len(task['features'])!=width for task in tasks):
            return {'status':'aggregate_program_incompatible_features'}
        existing=self.invented_views.get(family) if only_existing else None
        if only_existing and (not isinstance(existing,dict) or
                              existing.get('kind')!='aggregate_program' or
                              (existing.get('operator_dependency') and
                               existing['operator_dependency'] not in self.meta_operators)):
            return {'status':'aggregate_program_not_retained'}
        preferred=[row['reduce'] for _,row in sorted(self.meta_operators.items())]
        result=learner_dsl.fit(learner_dsl.AGGREGATE_LEARNER,tasks,
                               preferred_reducers=preferred,existing=existing)
        evaluated=result['candidates_evaluated']
        if not only_existing:
            self.aggregate_candidates_evaluated[family]=(
                self.aggregate_candidates_evaluated.get(family,0)+evaluated)
        if result['status']!='fitted':
            return {'status':'aggregate_program_rejected','candidates_evaluated':evaluated,
                    'reason':result['status']}
        base=result['view'];spec=base['spec']
        identifier=meta_operators.operator_key(spec)
        sources=self.meta_operators.get(identifier,{}).get('sources',())
        dependency=(existing.get('operator_dependency') if only_existing else
                    (identifier if any(src!=family for src in sources) else None))
        view={'kind':'aggregate_program','spec':deepcopy(spec),'cut':base['cut'],
              'buckets':base['buckets'],'operator':identifier,
              'operator_dependency':dependency,'accuracy':base['accuracy'],
              'coverage':base['coverage'],'gain_over_majority':base['gain_over_majority'],
              'tasks':len(tasks),'candidates_evaluated':(
                  existing.get('candidates_evaluated',0) if only_existing else evaluated),
              'mechanism':'typed_fold_synthesis'}
        self.invented_views[family]=view
        return {'status':'aggregate_program_invented','family':family,
                'retained':only_existing,**deepcopy(view)}

    @classmethod
    def _program_temporal_transfer(cls, tasks: list[dict], predicates) -> dict:
        """Check that a composed view transfers across chronological blocks.

        Leave-one-task-out alone can accidentally reward a nuisance feature that
        merely identifies an early/late regime.  A representation intended for
        continual learning must also transfer from earlier independent episodes
        to later ones (and vice versa).  This validation uses only already
        observed outcomes; it does not peek at future answers during deployment.
        """
        n=len(tasks)
        if n<12:
            return {'ok':False,'reason':'insufficient_temporal_support'}
        cut=n//2
        # Non-overlapping forward/reverse halves are intentionally stricter than
        # leave-one-out: a nuisance feature that merely marks the acquisition
        # epoch cannot learn its unseen branch from the held-out half.
        splits=((tasks[:cut],tasks[cut:]),(tasks[cut:],tasks[:cut]))
        reports=[]
        for train,test in splits:
            counts={}
            for task in train:
                key='|'.join(str(cls._predicate_value(task['features'],p)) for p in predicates)
                row=counts.setdefault(key,{})
                w=task['winner']; row[w]=row.get(w,0)+1
            covered=correct=0
            for task in test:
                key='|'.join(str(cls._predicate_value(task['features'],p)) for p in predicates)
                row=counts.get(key)
                if not row:
                    continue
                pred=min(row,key=lambda w:(-row[w],str(w)))
                covered+=1; correct+=int(pred==task['winner'])
            coverage=covered/max(1,len(test)); accuracy=correct/max(1,covered)
            reports.append({'coverage':coverage,'accuracy':accuracy,'train':len(train),'test':len(test)})
        ok=all(r['coverage']>=0.80 and r['accuracy']>=0.95 for r in reports)
        return {'ok':ok,'splits':reports,'reason':None if ok else 'temporal_transfer_failed'}

    def _invent_meta_program_from_tasks(self, fam: str, tasks: list[dict], *, max_program_size: int = 3, force: bool = False) -> dict:
        """Synthesize the smallest validated conditional meta-program.

        V6.9 was deliberately limited to exactly two predicates.  V7.0 keeps
        that search unchanged as the first stage, then (only if no pair is
        sufficient) permits a bounded third predicate.  This matters for
        interactions such as three-way parity where every single predicate and
        every pair is individually non-predictive.  There is still no XOR (or
        other benchmark-specific) primitive: the learned object is a truth-table
        partition over generic structural predicates produced by the existing
        meta-DSL.

        Complexity is controlled in three ways: smallest valid program wins,
        the deeper stage sees only a bounded deterministic predicate vocabulary,
        and the score penalizes both program size and fitted thresholds.
        Temporal transfer and leave-one-task-out validation remain mandatory.
        """
        if len(tasks)<8:
            return {'status':'meta_program_pending','family':fam,'tasks':len(tasks)}
        max_k=max(2,min(3,int(max_program_size)))

        # Revalidate a promoted program cheaply before launching another search.
        # This prevents repeated combinatorial work during stationary learning,
        # while contradictory evidence can still withdraw a stale program.
        existing=self.invented_views.get(fam)
        if (isinstance(existing,dict) and existing.get('kind')=='feature_program'
                and len(existing.get('predicates',()))<=max_k):
            predicates=existing.get('predicates',())
            buckets=existing.get('buckets',{}) or {}
            covered=correct=0
            try:
                for task in tasks:
                    key='|'.join(str(self._predicate_value(task['features'],p)) for p in predicates)
                    row=buckets.get(key)
                    if not isinstance(row,dict):
                        continue
                    covered+=1; correct+=int(str(row.get('winner'))==str(task['winner']))
                coverage=covered/max(1,len(tasks)); accuracy=correct/max(1,covered)
                temporal=self._program_temporal_transfer(tasks,predicates)
            except (ValueError,TypeError,IndexError):
                coverage=accuracy=0.0; temporal={'ok':False}
            if coverage>=0.70 and accuracy>=0.85 and temporal.get('ok'):
                counts={}
                for task in tasks:
                    key='|'.join(str(self._predicate_value(task['features'],p))
                                 for p in predicates)
                    row=counts.setdefault(key,{})
                    winner=task['winner'];row[winner]=row.get(winner,0)+1
                compact={}
                for key,row in counts.items():
                    winner=min(row,key=lambda w:(-row[w],str(w)))
                    support=sum(row.values());confidence=row[winner]/support
                    if support>=2 and confidence>=0.8:
                        compact[key]={'winner':winner,'support':support,
                                      'confidence':confidence}
                retained=deepcopy(existing)
                retained['tasks']=len(tasks)
                retained['buckets']=compact
                self.invented_views[fam]=retained
                return {'status':'meta_program_invented','family':fam,'retained':True,**retained}
            self.invented_views.pop(fam,None)

        checkpoints=self.program_search_checkpoints.setdefault(fam,{'pair':0,'deep':0})
        # Preserve the V6.9 pair search over the full bounded vocabulary.  Only
        # the deeper stage is narrowed to keep C(P,3) tractable on CPU.
        predicates=self._program_predicate_candidates(tasks,limit=128)
        if len(predicates)<2:
            return {'status':'meta_program_rejected','family':fam,'reason':'insufficient_predicates'}
        global_mode=self._mode_winner(tasks)
        truth_cols=[[self._predicate_value(t['features'],p) for t in tasks] for p in predicates]

        def search_size(k: int):
            pred_indices=range(len(predicates)) if k==2 else range(min(len(predicates),32))
            candidates=[]
            for idxs in combinations(pred_indices,k):
                bucket_counts={}; keys=[]
                for row_idx,task in enumerate(tasks):
                    key='|'.join(str(truth_cols[j][row_idx]) for j in idxs); keys.append(key)
                    counts=bucket_counts.setdefault(key,{})
                    w=task['winner']; counts[w]=counts.get(w,0)+1
                # A deeper program must actually create a richer joint partition;
                # otherwise a smaller representation is preferable.
                if len(bucket_counts)<max(3,k+1):
                    continue
                covered=correct=baseline_correct=0
                for target,key in zip(tasks,keys):
                    counts=bucket_counts[key]
                    available={w:(n-(1 if w==target['winner'] else 0)) for w,n in counts.items()}
                    available={w:n for w,n in available.items() if n>0}
                    if not available:
                        continue
                    pred=min(available,key=lambda w:(-available[w],str(w)))
                    covered+=1; correct+=int(pred==target['winner'])
                    baseline_correct+=int(global_mode==target['winner'])
                if covered<max(8,int(0.65*len(tasks))):
                    continue
                accuracy=correct/covered; coverage=covered/len(tasks)
                baseline=baseline_correct/covered if covered else 0.0
                gain=accuracy-baseline
                if accuracy<0.90 or coverage<0.70 or gain<0.15:
                    continue
                chosen=tuple(predicates[j] for j in idxs)
                temporal=self._program_temporal_transfer(tasks,chosen)
                if not temporal.get('ok'):
                    continue
                fitted=sum(1 for p in chosen if p['atom'].get('op')!='cmp')
                # For k=2 this is exactly the old 0.045 structural penalty.
                score=(accuracy*coverage)+(0.5*gain)-(0.0225*k)-(0.012*fitted)
                candidates.append((score,accuracy,coverage,gain,idxs,bucket_counts,temporal))
            return candidates

        # Minimal-description preference: never promote a deeper program when a
        # shallower one already satisfies the same strict validation gates.
        candidates=[]; program_size=None
        for k in range(2,max_k+1):
            key='pair' if k==2 else 'deep'
            min_new=4 if k==2 else 8
            min_tasks=8 if k==2 else 24
            last=int(checkpoints.get(key,0))
            if not force and (len(tasks)<min_tasks or (last and len(tasks)-last<min_new)):
                continue
            checkpoints[key]=len(tasks)
            candidates=search_size(k)
            if candidates:
                program_size=k
                break
        if not candidates or program_size is None:
            return {'status':'meta_program_rejected','family':fam,'reason':'no_valid_composed_program',
                    'predicates':len(predicates),'tasks':len(tasks),'max_program_size':max_k}
        candidates.sort(key=lambda x:(-x[0],x[4]))
        score,accuracy,coverage,gain,idxs,bucket_counts,temporal=candidates[0]
        compact={}
        for key,counts in bucket_counts.items():
            support=sum(counts.values())
            winner=min(counts,key=lambda w:(-counts[w],str(w)))
            confidence=counts[winner]/max(1,support)
            if support>=2 and confidence>=0.80:
                compact[key]={'winner':winner,'support':support,'confidence':confidence}
        if len(compact)<max(3,program_size+1):
            return {'status':'meta_program_rejected','family':fam,'reason':'no_stable_program_branches'}
        chosen=[deepcopy(predicates[j]) for j in idxs]
        view={'kind':'feature_program','predicates':chosen,
              'score':score,'accuracy':accuracy,'coverage':coverage,
              'gain_over_majority':gain,'tasks':len(tasks),'buckets':compact,
              'program_size':program_size,'temporal_validation':deepcopy(temporal)}
        self.invented_views[fam]=view
        return {'status':'meta_program_invented','family':fam,**deepcopy(view)}

    def _invent_transform_view_from_tasks(self, fam: str, tasks: list[dict]) -> dict:
        """Search a tiny auditable DSL for a new relational observable.

        This is attempted only after ordinary feature projections fail.  The
        DSL contains pairwise ordering/equality plus small learned scalar
        boundaries over raw values and pairwise differences.  Candidates are
        validated leave-one-task-out using bucket counts computed once per
        transform, so validation is O(atoms*tasks), not quadratic in tasks.
        """
        if not tasks:
            return {'status':'meta_transform_pending','family':fam,'tasks':0}
        dims_total=len(tasks[0]['features'])
        if dims_total<2 or any(len(t['features'])!=dims_total for t in tasks):
            return {'status':'meta_transform_rejected','family':fam,'reason':'incompatible_features'}
        global_mode=self._mode_winner(tasks)
        candidates=[]
        for atom in self._transform_atom_candidates(tasks):
            atoms=(atom,)
            # Precompute transformed buckets and winner counts once.
            bucket_counts={}
            keys=[]
            for task in tasks:
                key=self._transform_key(task['features'],atoms); keys.append(key)
                counts=bucket_counts.setdefault(key,{})
                w=task['winner']; counts[w]=counts.get(w,0)+1
            covered=correct=baseline_correct=0
            for target,key in zip(tasks,keys):
                counts=bucket_counts.get(key,{})
                # Exact LOO: remove only this target's vote from its bucket.
                available={w:(n-(1 if w==target['winner'] else 0)) for w,n in counts.items()}
                available={w:n for w,n in available.items() if n>0}
                if not available:
                    continue
                pred=min(available,key=lambda w:(-available[w],str(w)))
                covered+=1; correct+=int(pred==target['winner'])
                baseline_correct+=int(global_mode==target['winner'])
            if covered<max(6,int(0.5*len(tasks))):
                continue
            accuracy=correct/covered; coverage=covered/len(tasks)
            baseline=baseline_correct/covered if covered else 0.0
            gain=accuracy-baseline
            if accuracy < 0.85 or coverage < 0.60 or gain < 0.10:
                continue
            fitted=1 if atom.get('op')!='cmp' else 0
            score=(accuracy*coverage)+(0.5*gain)-0.02-(0.01*fitted)
            candidates.append((score,accuracy,coverage,gain,atoms,bucket_counts))
        if not candidates:
            return {'status':'meta_transform_rejected','family':fam,'reason':'no_valid_transform_view',
                    'tasks':len(tasks)}
        candidates.sort(key=lambda x:(-x[0],repr(x[4])))
        score,accuracy,coverage,gain,atoms,bucket_counts=candidates[0]
        compact={}
        for key,counts in bucket_counts.items():
            support=sum(counts.values())
            winner=min(counts,key=lambda w:(-counts[w],str(w)))
            confidence=counts[winner]/max(1,support)
            if support>=2 and confidence>=0.75:
                compact[key]={'winner':winner,'support':support,'confidence':confidence}
        if not compact:
            return {'status':'meta_transform_rejected','family':fam,'reason':'no_stable_buckets'}
        view={'kind':'feature_transform','atoms':[dict(a) for a in atoms],
              'score':score,'accuracy':accuracy,'coverage':coverage,
              'gain_over_majority':gain,'tasks':len(tasks),'buckets':compact}
        self.invented_views[fam]=view
        return {'status':'meta_transform_invented','family':fam,**deepcopy(view)}

    @staticmethod
    def _view_key(features, dims) -> str:
        vals=tuple(float(features[i]) for i in dims)
        return ','.join(f'{v:.6g}' for v in vals)

    def _record_history(self, fam: str, vals, strategy: str, *, success: bool, cost: float) -> None:
        rows=self.history.setdefault(fam,[])
        rows.append({'features':list(vals),'strategy':str(strategy),'success':bool(success),
                     'cost':max(0.001,float(cost))})
        if len(rows)>self.max_history_per_family:
            del rows[:-self.max_history_per_family]
        # Synthesis is intentionally periodic, not on every strategy attempt.
        # It is cheap at current bounds and its result is only a routing hint.
        if len(rows)>=16 and len(rows)%4==0:
            limit=self.meta_search_cpu_limit_s
            spent=self.meta_search_cpu_spent_s.get(fam,0.0)
            if limit is not None and spent>=limit:
                if fam not in self.meta_search_exhausted:
                    self.meta_search_exhausted[fam]=len(self._meta_tasks(fam))
                    self.invented_views.pop(fam,None)
                    self.meta_rivals.pop(fam,None)
            else:
                started=process_time()
                try:
                    self.invent_view(fam)
                finally:
                    self.meta_search_cpu_spent_s[fam]=spent+(
                        process_time()-started)
            self._reconcile_meta_primitives()

    def _meta_tasks(self, fam: str) -> list[dict]:
        grouped={}
        for row in self.history.get(fam,()):
            feats=tuple(float(x) for x in row.get('features',()))
            if not feats:
                continue
            sig=self.signature(feats)
            task=grouped.setdefault(sig,{'features':feats,'strategies':{}})
            st=task['strategies'].setdefault(str(row.get('strategy')),{'trials':0,'success':0,'cost':0.0})
            st['trials']+=1; st['success']+=int(bool(row.get('success')))
            st['cost']+=max(0.001,float(row.get('cost',1.0)))
        out=[]
        for sig,task in grouped.items():
            scored=[]
            for strategy,row in task['strategies'].items():
                trials=max(1,int(row['trials'])); rate=float(row['success'])/trials
                avg=float(row['cost'])/trials
                scored.append((-rate,avg,strategy))
            if len(scored)<2:
                continue
            scored.sort(); best=scored[0]
            # Do not manufacture a class label when every strategy failed.
            if -best[0] <= 0.0:
                continue
            out.append({'signature':sig,'features':task['features'],'winner':best[2],
                        'winner_rate':-best[0],'winner_cost':best[1]})
        return out

    @staticmethod
    def _mode_winner(tasks) -> str | None:
        counts={}
        for task in tasks:
            w=task.get('winner')
            if w is not None:
                counts[w]=counts.get(w,0)+1
        if not counts:
            return None
        return min(counts, key=lambda w:(-counts[w],str(w)))

    def _best_projection_view(self, tasks: list[dict], max_dims: int) -> dict | None:
        """Interpret the declarative projection learner."""
        result=learner_dsl.fit(learner_dsl.PROJECTION_LEARNER,tasks,max_dims=max_dims)
        return result.get('view') if result['status']=='fitted' else None

    def _maybe_discover_rival(self, family: str, tasks: list[dict]) -> None:
        """Check a geometrically spaced, bounded alternative to an acquired fold."""
        if not self.enable_meta_rivals:
            return
        view=self.invented_views.get(family)
        if not view or view.get('kind')!='aggregate_program':
            return
        n=len(tasks);width=len(tasks[0]['features'])
        if n<self.meta_rival_retry_after.get(family,0):
            return
        if n<max(64,8*width) or n&(n-1) or n<=self.meta_rival_checkpoints.get(family,0):
            return
        self.meta_rival_checkpoints[family]=n
        alternative=self._best_projection_view(tasks,3)
        if alternative is None or alternative['accuracy']<0.95:
            self.meta_rivals.pop(family,None)
            return
        labels=sorted({task['winner'] for task in tasks})
        for task in tasks:
            primary,_=self._view_order(family,task['features'],labels,view=view)
            rival,_=self._view_order(family,task['features'],labels,view=alternative)
            if primary and rival and primary[0]!=rival[0]:
                self.meta_rivals.pop(family,None)
                return
        self.meta_rivals[family]=[alternative]

    def _candidate_learner_programs(self) -> list[dict]:
        """Combine existing declarative components under a finite grammar."""
        topologies=(('binary_context','binary_context'),
                    ('fold_bool','fold_bool'),
                    ('binary_context','fold_bool'))
        programs=[]
        for topology in topologies:
            program=deepcopy(learner_dsl.PROJECTION_LEARNER)
            program['hypothesis_generator']='product_extractors'
            program['operators']=list(dict.fromkeys(
                [*learner_dsl.PROJECTION_LEARNER['operators'],
                 *learner_dsl.AGGREGATE_LEARNER['operators']]))
            program['constraints']={'min_examples':64,'max_width':16,'max_depth':2,
                                    'components':list(topology),'top_components':4}
            program['verifier']={'kind':'leave_one_out','temporal':'halves',
                                 'min_temporal_coverage':0.65,
                                 'min_temporal_accuracy':0.92}
            program['cost']={'kind':'weighted_fit','accuracy_weight':1.0,
                             'gain_weight':0.5,'dimension_penalty':0.01}
            program['promotion']={'min_covered_count':16,'min_covered_fraction':0.6,
                                  'min_accuracy':0.92,'min_coverage':0.80,
                                  'min_gain':0.20,'min_bucket_support':2,
                                  'min_bucket_confidence':0.85,
                                  'required_buckets':2,
                                  'different_bucket_winners':True}
            program['budget']={'max_candidates':96,'max_tasks':384,
                               'max_cpu_s':10.0}
            learner_dsl.validate(program)
            programs.append(program)
        programs.sort(key=lambda row:(self._learner_key(row) not in self.meta_learners,
                                      topologies.index(tuple(row['constraints']['components']))))
        return programs

    def _synthesize_learner_from_tasks(self, family: str, tasks: list[dict]) -> dict:
        """Search descriptions, then promote only a verified local improvement."""
        if not self.enable_learner_synthesis or len(tasks)<64:
            return {'status':'learner_synthesis_pending'}
        existing=self.invented_views.get(family)
        baseline=(float(existing.get('accuracy',0))*float(existing.get('coverage',0))
                  if isinstance(existing,dict) else 0.0)
        tried=hypotheses=0;search_cpu=verification_cpu=0.0
        preferred=[row['reduce'] for _,row in sorted(self.meta_operators.items())]
        fitted=[]
        for program in self._candidate_learner_programs():
            tried+=1
            result=learner_dsl.fit(program,tasks,preferred_reducers=preferred)
            hypotheses+=result['candidates_evaluated']
            search_cpu+=result.get('search_cpu_s',0.0)
            verification_cpu+=result.get('verification_cpu_s',0.0)
            if result['status']!='fitted':
                continue
            view=result['view']
            if view['accuracy']*view['coverage']<=baseline+0.05:
                continue
            key=self._learner_key(program)
            fitted.append((view['accuracy']*view['coverage'],view['score'],key,view))
            # A previously validated learner can be reused without reopening
            # every cheaper description once it again has strong evidence.
            if (key in self.meta_learners and view['accuracy']>=0.98 and
                    view['coverage']>=0.95):
                break
        row=self.learner_synthesis_counts.setdefault(family,
             {'descriptions':0,'hypotheses':0})
        row['descriptions']+=tried;row['hypotheses']+=hypotheses
        row['search_cpu_s']=row.get('search_cpu_s',0.0)+search_cpu
        row['verification_cpu_s']=row.get('verification_cpu_s',0.0)+verification_cpu
        if fitted:
            fitted.sort(key=lambda item:(-item[0],-item[1],item[2]))
            _,_,key,view=fitted[0]
            sources=self.meta_learners.get(key,{}).get('sources',())
            dependency=key if any(source!=family for source in sources) else None
            view.update(learner_key=key,learner_dependency=dependency,
                        descriptions_tried=tried,
                        structural_hypotheses=hypotheses)
            self.invented_views[family]=view
            if (len(fitted)>1 and fitted[0][0]-fitted[1][0]<=0.01 and
                    fitted[0][2]!=fitted[1][2]):
                rival=deepcopy(fitted[1][3])
                rival['learner_key']=fitted[1][2]
                self.meta_rivals[family]=[rival]
            promotion_started=process_time()
            self._reconcile_meta_learners()
            row['promotion_cpu_s']=row.get('promotion_cpu_s',0.0)+(
                process_time()-promotion_started)
            return {'status':'learner_synthesized','family':family,
                    **deepcopy(view)}
        return {'status':'learner_synthesis_rejected','family':family,
                'descriptions_tried':tried,'structural_hypotheses':hypotheses}

    def invent_view(self, family: str, *, max_dims: int = 3, min_tasks: int = 8) -> dict:
        """Synthesize a compact structural representation from meta-experience.

        Candidate representations are projections onto 1..``max_dims`` existing
        structural observables.  They are evaluated leave-one-task-out.  A view
        is promoted only when it predicts the empirically best strategy much
        better than the global-majority baseline and covers most tasks.  This is
        representation invention in a bounded meta-DSL, not task-answer synthesis.
        """
        fam=str(family).strip().lower(); tasks=self._meta_tasks(fam)
        retry_at=int(self.aggregate_retry_after.get(fam,0))
        if retry_at and len(tasks)<retry_at:
            return {'status':'meta_view_pending','family':fam,
                    'reason':'awaiting_new_evidence','tasks':len(tasks),
                    'retry_at':retry_at}
        if retry_at:
            self.aggregate_retry_after.pop(fam,None)
        if len(tasks)<max(4,int(min_tasks)):
            return {'status':'meta_view_pending','family':fam,'tasks':len(tasks)}
        dims_total=len(tasks[0]['features'])
        if dims_total<2 or any(len(t['features'])!=dims_total for t in tasks):
            return {'status':'meta_view_rejected','family':fam,'reason':'incompatible_features'}
        # A previously learned program has a cheap held-out/temporal recheck.
        # Do it before rescanning all projections and fitted transforms on each
        # new observation batch; contradictory evidence still withdraws it.
        program_checked=None
        existing=self.invented_views.get(fam)
        if isinstance(existing,dict) and existing.get('kind')=='learner_product':
            validation_started=process_time()
            checked=learner_dsl.revalidate_view(existing,tasks)
            row=self.learner_synthesis_counts.setdefault(fam,
                 {'descriptions':0,'hypotheses':0})
            row['revalidation_cpu_s']=row.get('revalidation_cpu_s',0.0)+(
                process_time()-validation_started)
            if checked is not None:
                self.invented_views[fam]=checked
                return {'status':'learner_retained','family':fam,**deepcopy(checked)}
            self.invented_views.pop(fam,None)
            self.meta_rivals.pop(fam,None)
            self.learner_retry_after[fam]=len(tasks)+32
            self._reconcile_meta_learners()
            return {'status':'learner_withdrawn','family':fam,
                    'reason':'new_evidence_failed_validation',
                    'retry_at':self.learner_retry_after[fam]}
        if isinstance(existing,dict) and existing.get('kind')=='feature_program':
            program_checked=self._invent_meta_program_from_tasks(fam,tasks)
            if program_checked.get('retained'):
                return program_checked
        if isinstance(existing,dict) and existing.get('kind')=='aggregate_program':
            checked=self._invent_aggregate_view_from_tasks(
                fam,tasks,only_existing=True)
            if checked.get('retained'):
                self._maybe_discover_rival(fam,tasks)
                return checked
            self.invented_views.pop(fam,None)
            self.meta_rivals.pop(fam,None)
            self.aggregate_retry_after[fam]=len(tasks)+32
            return {'status':'aggregate_program_withdrawn','family':fam,
                    'reason':'new_evidence_failed_validation','tasks':len(tasks),
                    'retry_at':self.aggregate_retry_after[fam]}
        if (self.enable_meta_rivals and self.meta_operators and
                len(tasks)>=24 and
                len(tasks)>=self.meta_rival_retry_after.get(fam,0)):
            aggregate=self._invent_aggregate_view_from_tasks(fam,tasks)
            if aggregate.get('status')=='aggregate_program_invented':
                if (isinstance(existing,dict) and
                        existing.get('kind')=='feature_projection' and
                        existing.get('accuracy',0)>=0.95):
                    self.meta_rivals[fam]=[existing]
                self._maybe_discover_rival(fam,tasks)
                return aggregate
        if (self.enable_learner_synthesis and len(tasks)>=64 and
                len(tasks)&(len(tasks)-1)==0 and
                len(tasks)>self.learner_synthesis_checkpoints.get(fam,0) and
                len(tasks)>=self.learner_retry_after.get(fam,0) and
                (not isinstance(existing,dict) or
                 float(existing.get('accuracy',0))*float(existing.get('coverage',0))<0.90)):
            self.learner_synthesis_checkpoints[fam]=len(tasks)
            synthesized=self._synthesize_learner_from_tasks(fam,tasks)
            if synthesized.get('status')=='learner_synthesized':
                return synthesized
        projection=self._best_projection_view(tasks,max_dims)
        if projection is None:
            macro=self._invent_macro_view_from_tasks(fam,tasks)
            if macro.get('status')=='macro_program_invented':
                return macro
            transformed=self._invent_transform_view_from_tasks(fam,tasks)
            if transformed.get('status')=='meta_transform_invented':
                return transformed
            program=(program_checked if program_checked is not None else
                     self._invent_meta_program_from_tasks(fam,tasks))
            if program.get('status')=='meta_program_invented':
                return program
            aggregate=self._invent_aggregate_view_from_tasks(fam,tasks)
            if aggregate.get('status')=='aggregate_program_invented':
                return aggregate
            if retry_at:
                self.aggregate_retry_after[fam]=len(tasks)+32
            old=self.invented_views.pop(fam,None)
            return {'status':'meta_view_rejected','family':fam,'reason':'no_valid_compact_view_transform_or_program',
                    'transform_reason':transformed.get('reason'),'program_reason':program.get('reason'),
                    'aggregate_reason':aggregate.get('status'),
                    'withdrawn':bool(old),'tasks':len(tasks)}
        self.invented_views[fam]=projection
        return {'status':'meta_view_invented','family':fam,**deepcopy(projection)}

    def _view_order(self, fam: str, vals, default: list[str], *, view=None) -> tuple[list[str] | None,dict | None]:
        view=self.invented_views.get(fam) if view is None else view
        if not isinstance(view,dict):
            return None,None
        kind=str(view.get('kind','feature_projection'))
        detail={'accuracy':view.get('accuracy'),'coverage':view.get('coverage'),
                'gain_over_majority':view.get('gain_over_majority'),'kind':kind}
        if kind=='learner_product':
            if not self.enable_learner_synthesis:
                return None,None
            dependency=view.get('learner_dependency')
            if dependency and dependency not in self.meta_learners:
                return None,None
            key=learner_dsl.evaluate_components(vals,view.get('components'))
            if key is None:
                return None,None
            bucket=(view.get('buckets') or {}).get(key)
            detail['learner_key']=view.get('learner_key')
            detail['learner_dependency']=dependency
        elif kind=='aggregate_program':
            if not self.enable_meta_operator_invention:
                return None,None
            dependency=view.get('operator_dependency')
            if dependency and dependency not in self.meta_operators:
                return None,None
            statistic=meta_operators.evaluate(vals,view.get('spec'))
            if statistic is None:
                return None,None
            bucket=(view.get('buckets') or {}).get(str(int(statistic>float(view['cut']))))
            detail['operator']=view.get('operator')
            detail['operator_dependency']=dependency
            detail['statistic']=statistic
        elif kind=='macro_program':
            primitive=self.meta_primitives.get(view.get('primitive')) if self.enable_meta_primitives else None
            if primitive is None:
                return None,None
            starts=view.get('starts',())
            if len(starts)!=2:
                return None,None
            try:
                values=[self._meta_primitive_value(vals,primitive,int(start))
                        for start in starts]
                if any(value is None for value in values):
                    return None,None
                key='|'.join(str(value) for value in values)
            except (ValueError,TypeError,IndexError):
                return None,None
            bucket=(view.get('buckets') or {}).get(key)
            detail['primitive']=view.get('primitive')
            detail['sources']=list(primitive.get('sources',()))
        elif kind=='feature_transform':
            atoms=view.get('atoms',())
            try:
                key=self._transform_key(vals,atoms)
            except (ValueError,TypeError,IndexError):
                return None,None
            bucket=(view.get('buckets') or {}).get(key)
            detail['atoms']=deepcopy(list(atoms))
        elif kind=='feature_program':
            predicates=view.get('predicates',())
            try:
                bits=[self._predicate_value(vals,p) for p in predicates]
                key='|'.join(str(int(x)) for x in bits)
            except (ValueError,TypeError,IndexError):
                return None,None
            bucket=(view.get('buckets') or {}).get(key)
            detail['predicates']=deepcopy(list(predicates))
            detail['program_size']=int(view.get('program_size',len(predicates)))
        else:
            dims=tuple(int(i) for i in view.get('dims',()))
            if not dims or any(i<0 or i>=len(vals) for i in dims):
                return None,None
            bucket=(view.get('buckets') or {}).get(self._view_key(vals,dims))
            detail['dims']=list(dims)
        if not isinstance(bucket,dict):
            return None,None
        winner=str(bucket.get('winner',''))
        if winner not in default or int(bucket.get('support',0))<2 or float(bucket.get('confidence',0.0))<0.75:
            return None,None
        order=[winner]+[s for s in default if s!=winner]
        detail['bucket']=deepcopy(bucket)
        return order,detail

    @staticmethod
    def _exact_order(table: dict[str,dict], default: list[str]) -> list[str] | None:
        seen=[]
        for strategy in default:
            row=table.get(strategy)
            if not row or int(row.get('trials',0))<=0:
                continue
            trials=max(1,int(row.get('trials',0)))
            rate=int(row.get('success',0))/trials
            avg=float(row.get('cost',0.0))/trials
            # High verified success dominates; cost breaks ties.
            seen.append((-rate,avg,default.index(strategy),strategy))
        if not seen:
            return None
        seen.sort()
        promoted=[x[3] for x in seen]
        promoted.extend(s for s in default if s not in promoted)
        return promoted

    def _budget_order(self, fam: str, sig: str, default: list[str]) -> tuple[list[str] | None,list[dict]]:
        table=self.budgets.get(fam,{}).get(sig,{})
        scored=[]
        for strategy in default:
            row=table.get(strategy)
            if not row or int(row.get('trials',0))<2:
                continue
            priority=float(row.get('priority',0.5)); quality=float(row.get('quality',0.5))
            durability=float(row.get('durability',0.0)); cost=max(0.001,float(row.get('ema_cost',1.0)))
            # Recent priority dominates so genuine regime shifts can overcome a
            # long lifetime average; durability/quality keep one-off noise weak.
            value=(0.64*priority + 0.26*quality + 0.10*durability)/(1.0+0.025*log1p(cost))
            scored.append({'strategy':strategy,'value':value,'priority':priority,
                           'durability':durability,'quality':quality,'ema_cost':cost,
                           'trials':int(row.get('trials',0))})
        if not scored:
            return None,[]
        scored.sort(key=lambda x:(-x['value'],default.index(x['strategy'])))
        promoted=[x['strategy'] for x in scored]
        promoted.extend(s for s in default if s not in promoted)
        return promoted,scored

    def rank(self, family: str, features, strategies, *, min_confidence: float = 0.18) -> dict:
        fam=str(family).strip().lower(); default=list(dict.fromkeys(str(s) for s in strategies))
        vals=self._feature_tuple(features)
        if not default:
            return {'order':[],'used':False,'mode':'empty','scores':[]}
        sig=self.signature(vals)
        budget_order,budget_scores=self._budget_order(fam,sig,default)
        if budget_order is not None:
            return {'order':budget_order,'used':budget_order!=default,'mode':'aikr_budget',
                    'signature':sig,'scores':budget_scores}
        table=self.exact.get(fam,{}).get(sig,{})
        exact=self._exact_order(table,default)
        if exact is not None:
            return {'order':exact,'used':exact!=default,'mode':'exact_class',
                    'signature':sig,'scores':deepcopy(table)}
        view_order,view_detail=self._view_order(fam,vals,default)
        rivals=self.meta_rivals.get(fam,()) if self.enable_meta_rivals else ()
        if rivals:
            rival_order,_=self._view_order(fam,vals,default,view=rivals[0])
            if (view_order is None or rival_order is None or
                    view_order[0]!=rival_order[0]):
                return {'order':default,'used':False,'mode':'ambiguous',
                        'signature':sig,'hypotheses':1+len(rivals),'scores':[]}
        if view_order is not None:
            return {'order':view_order,'used':view_order!=default,'mode':'invented_view',
                    'signature':sig,'view':view_detail,'scores':[]}
        router=self.routers.get(fam)
        if router is None:
            return {'order':default,'used':False,'mode':'default','signature':sig,'scores':[]}
        # RBF router only reorders if every candidate strategy has sufficiently
        # local evidence.  This is deliberately conservative.
        route=router.rank(vals,default,min_confidence=min_confidence)
        if route.get('used'):
            return {**route,'mode':'rbf','signature':sig,'features':list(vals)}
        # Cross-mechanism cold start: evidence may exist for only one of the
        # currently available strategies.  A sufficiently local estimate may be
        # *promoted* to the front, but unknown strategies are never removed or
        # reordered relative to one another.  This can save work while retaining
        # deterministic completeness fallbacks.
        partial=[]
        for strategy in default:
            pred=router.predict(vals,strategy)
            if pred is not None and float(pred.get('confidence',0.0))>=min_confidence:
                partial.append(pred)
        if partial:
            partial.sort(key=lambda p:(p['cost'],-p['confidence'],default.index(p['strategy'])))
            best=partial[0]['strategy']
            promoted=[best]+[s for s in default if s!=best]
            return {'order':promoted,'used':promoted!=default,'mode':'rbf_promote',
                    'signature':sig,'features':list(vals),'scores':partial}
        return {**route,'mode':'default','signature':sig,'features':list(vals)}

    @staticmethod
    def _entropy(n: int) -> float:
        return 0.0 if n<=1 else log2(float(n))

    def select_epistemic_action(self, hypotheses, actions, *, pragmatic_weight: float = 0.0) -> dict:
        """Choose an unlabeled experiment by expected information gain per cost.

        ``hypotheses`` may contain any hashable ids.  Each action is a dict with
        ``groups``: a list of mutually exclusive hypothesis groups representing
        the possible outcomes, ``cost`` (>0), and optional ``pragmatic_value``.
        The method never predicts which outcome will occur and never mutates any
        hypothesis state.  Uniform prior over the supplied version space is used
        deliberately because this is a scheduler, not a truth estimator.
        """
        hyps=list(dict.fromkeys(hypotheses))
        if len(hyps)<2:
            return {'status':'no_epistemic_action','reason':'version_space_not_ambiguous'}
        universe=set(hyps); prior_h=self._entropy(len(hyps)); scored=[]
        for idx,action in enumerate(actions):
            groups=[]; covered=set(); valid=True
            for raw in action.get('groups',()):
                g=[h for h in raw if h in universe and h not in covered]
                if g:
                    groups.append(g); covered.update(g)
            # Unknown/unmodelled outcomes are represented conservatively as one
            # residual group, never silently discarded.
            residual=[h for h in hyps if h not in covered]
            if residual: groups.append(residual)
            if len(groups)<2: continue
            expected_h=0.0
            for g in groups:
                p=len(g)/len(hyps); expected_h += p*self._entropy(len(g))
            info=max(0.0,prior_h-expected_h)
            cost=max(1e-9,float(action.get('cost',1.0)))
            pragmatic=float(action.get('pragmatic_value',0.0))
            value=(info + max(0.0,float(pragmatic_weight))*pragmatic)/cost
            scored.append({'index':idx,'info_gain_bits':info,'expected_entropy_bits':expected_h,
                           'cost':cost,'pragmatic_value':pragmatic,'value_per_cost':value,
                           'label':action.get('label')})
        if not scored:
            return {'status':'no_epistemic_action','reason':'no_discriminating_action'}
        scored.sort(key=lambda x:(-x['value_per_cost'],-x['info_gain_bits'],x['cost'],x['index']))
        best=scored[0]
        return {'status':'epistemic_action','chosen_index':best['index'],
                'prior_entropy_bits':prior_h,'chosen':best,'scores':scored}

    def propose_meta_probe(self, family: str, candidates) -> dict:
        """Choose a real trial that separates observationally equivalent rules.

        A program search keeps one representative per truth partition.  Here we
        reconstruct alternative comparator predicates with the *same* training
        truth column.  Replacing one predicate at a time yields programs that
        fit every observed task equally well, yet can disagree on a new trial.
        The caller supplies feasible feature vectors and their costs; this
        method only selects a trial.  It never supplies or records its outcome.
        """
        fam=str(family).strip().lower()
        view=self.invented_views.get(fam)
        rivals=self.meta_rivals.get(fam,()) if self.enable_meta_rivals else ()
        if isinstance(view,dict) and len(rivals)==1:
            labels=sorted({task['winner'] for task in self._meta_tasks(fam)})
            offered=list(candidates);actions=[];predictions=[]
            for candidate in offered:
                vals=self._feature_tuple(candidate['features'])
                first,_=self._view_order(fam,vals,labels,view=view)
                second,_=self._view_order(fam,vals,labels,view=rivals[0])
                pair=(first[0] if first else None,second[0] if second else None)
                predictions.append(pair)
                groups=([[0],[1]] if all(pair) and pair[0]!=pair[1]
                        else [[0,1]])
                actions.append({'groups':groups,'cost':candidate.get('cost',1.0),
                                'label':candidate.get('label')})
            proposal=self.select_epistemic_action((0,1),actions)
            if proposal.get('status')=='epistemic_action':
                index=proposal['chosen_index']
                self.meta_probe_pending[fam]={
                    'signature':self.signature(offered[index]['features']),
                    'predictions':list(predictions[index])}
            return {**proposal,'ambiguous_hypotheses':2}
        if not isinstance(view,dict) or view.get('kind')!='feature_program':
            return {'status':'no_epistemic_action','reason':'no_learned_program'}
        tasks=self._meta_tasks(fam)
        predicates=view.get('predicates',())
        if not tasks or not predicates:
            return {'status':'no_epistemic_action','reason':'no_observed_tasks'}
        width=len(tasks[0]['features'])
        if any(len(task['features'])!=width for task in tasks):
            return {'status':'no_epistemic_action','reason':'incompatible_features'}

        # Permit a small number of disagreements after the first intervention:
        # one counterexample is evidence against a rule, but does not establish
        # that all other explanations have disappeared.  The bound is structural
        # and shrinks as a fraction of the accumulated independent tasks.
        tolerated=max(2,len(tasks)//16)
        # Parameter-free comparisons are the smallest alternative language.
        # A fitted threshold would introduce a new degree of freedom and make
        # the ambiguity claim stronger than the observations warrant.
        alternatives=[]
        for slot,chosen in enumerate(predicates):
            if chosen.get('atom',{}).get('op')!='cmp':
                continue
            truth=tuple(self._predicate_value(task['features'],chosen)
                        for task in tasks)
            for a,b in combinations(range(width),2):
                atom={'op':'cmp','a':a,'b':b}
                values=tuple(self._transform_atom_value(task['features'],atom)
                             for task in tasks)
                for value in (-1,0,1):
                    candidate={'op':'atom_eq','atom':atom,'value':value}
                    if candidate==chosen:
                        continue
                    column=tuple(int(x==value) for x in values)
                    direct=sum(x!=y for x,y in zip(column,truth))
                    inverse=len(truth)-direct
                    if direct<=tolerated:
                        alternatives.append((slot,candidate,False))
                    elif inverse<=tolerated:
                        alternatives.append((slot,candidate,True))
        if not alternatives:
            return {'status':'no_epistemic_action','reason':'version_space_not_ambiguous'}

        hypotheses=list(range(len(alternatives)+1))
        actions=[]
        offered=list(candidates)
        for action in offered:
            vals=self._feature_tuple(action['features'])
            if len(vals)!=width:
                raise ValueError('La prueba debe tener los mismos rasgos estructurales.')
            bits=[self._predicate_value(vals,p) for p in predicates]
            groups={}
            for hyp in hypotheses:
                trial_bits=list(bits)
                if hyp:
                    slot,predicate,inverted=alternatives[hyp-1]
                    value=self._predicate_value(vals,predicate)
                    trial_bits[slot]=1-value if inverted else value
                key='|'.join(str(bit) for bit in trial_bits)
                bucket=(view.get('buckets') or {}).get(key)
                prediction=(str(bucket['winner']) if isinstance(bucket,dict)
                            and 'winner' in bucket else None)
                groups.setdefault(prediction,[]).append(hyp)
            actions.append({'groups':list(groups.values()),
                            'cost':action.get('cost',1.0),
                            'label':action.get('label')})
        proposal=self.select_epistemic_action(hypotheses,actions)
        return {**proposal,'ambiguous_hypotheses':len(hypotheses)}

    def budget_snapshot(self, family: str, features) -> dict:
        fam=str(family).strip().lower(); sig=self.signature(features)
        return deepcopy(self.budgets.get(fam,{}).get(sig,{}))

    def record_gap(self, family: str, features, attempts, *, reason: str,
                   evidence_request: dict | None = None) -> dict:
        row={'family':str(family).strip().lower(),'features':list(self._feature_tuple(features)),
             'attempts':deepcopy(list(attempts)),'reason':str(reason),
             'evidence_request':deepcopy(evidence_request) if evidence_request else None}
        self.gaps.append(row)
        if len(self.gaps)>self.max_gaps:
            self.gaps=self.gaps[-self.max_gaps:]
        invention=self.invent_view(row['family'])
        return {'status':'meta_representation_gap',**deepcopy(row),'representation_invention':invention}

    def as_dict(self) -> dict:
        return {'version':self.VERSION,'exact':deepcopy(self.exact),
                'routers':{k:v.as_dict() for k,v in self.routers.items()},
                'budgets':deepcopy(self.budgets),'clock':self.clock,
                'observations':self.observations,'gaps':deepcopy(self.gaps),
                'max_gaps':self.max_gaps,'history':deepcopy(self.history),
                'max_history_per_family':self.max_history_per_family,
                'invented_views':deepcopy(self.invented_views),
                'program_search_checkpoints':deepcopy(self.program_search_checkpoints),
                'meta_primitives':deepcopy(self.meta_primitives),
                'enable_meta_primitives':self.enable_meta_primitives,
                'meta_operators':deepcopy(self.meta_operators),
                'enable_meta_operator_invention':self.enable_meta_operator_invention,
                'aggregate_candidates_evaluated':deepcopy(self.aggregate_candidates_evaluated),
                'aggregate_retry_after':deepcopy(self.aggregate_retry_after),
                'enable_meta_rivals':self.enable_meta_rivals,
                'meta_rivals':deepcopy(self.meta_rivals),
                'meta_probe_pending':deepcopy(self.meta_probe_pending),
                'meta_rival_checkpoints':deepcopy(self.meta_rival_checkpoints),
                'meta_rival_retry_after':deepcopy(self.meta_rival_retry_after),
                'enable_learner_synthesis':self.enable_learner_synthesis,
                'learner_synthesis_counts':deepcopy(self.learner_synthesis_counts),
                'learner_synthesis_checkpoints':deepcopy(self.learner_synthesis_checkpoints),
                'learner_retry_after':deepcopy(self.learner_retry_after),
                'meta_search_cpu_limit_s':self.meta_search_cpu_limit_s,
                'meta_search_cpu_spent_s':deepcopy(self.meta_search_cpu_spent_s),
                'meta_search_exhausted':deepcopy(self.meta_search_exhausted)}

    @classmethod
    def from_dict(cls, data: dict | None) -> 'MetaController':
        obj=cls(); data=data or {}
        if not isinstance(data,dict):
            return obj
        version=int(data.get('version',1) or 1)
        if version not in (1,2,3,4,5,6,7,8,9,10,11,12):
            raise ValueError('Estado de MetaController no compatible.')
        obj.exact=deepcopy(data.get('exact',{})) if isinstance(data.get('exact',{}),dict) else {}
        obj.routers={str(k):RBFStrategyRouter.from_dict(v) for k,v in (data.get('routers',{}) or {}).items()}
        obj.budgets=deepcopy(data.get('budgets',{})) if version>=2 and isinstance(data.get('budgets',{}),dict) else {}
        obj.clock=max(0,int(data.get('clock',0) or 0))
        obj.observations=max(0,int(data.get('observations',0) or 0))
        obj.max_gaps=max(16,min(4096,int(data.get('max_gaps',256) or 256)))
        obj.gaps=deepcopy(list(data.get('gaps',[]))[-obj.max_gaps:])
        if version>=3:
            obj.max_history_per_family=max(64,min(4096,int(data.get('max_history_per_family',768) or 768)))
            raw_history=data.get('history',{}) if isinstance(data.get('history',{}),dict) else {}
            obj.history={str(f):deepcopy(list(rows)[-obj.max_history_per_family:])
                         for f,rows in raw_history.items() if isinstance(rows,list)}
            obj.invented_views=deepcopy(data.get('invented_views',{})) if isinstance(data.get('invented_views',{}),dict) else {}
        if version>=6:
            raw=data.get('program_search_checkpoints',{})
            obj.program_search_checkpoints=deepcopy(raw) if isinstance(raw,dict) else {}
        if version>=7:
            obj.enable_meta_primitives=bool(data.get('enable_meta_primitives',True))
        if version>=8:
            obj.enable_meta_operator_invention=bool(data.get('enable_meta_operator_invention',True))
            counts=data.get('aggregate_candidates_evaluated',{})
            obj.aggregate_candidates_evaluated=deepcopy(counts) if isinstance(counts,dict) else {}
        if version>=9:
            retry=data.get('aggregate_retry_after',{})
            obj.aggregate_retry_after=deepcopy(retry) if isinstance(retry,dict) else {}
        if version>=10:
            obj.enable_meta_rivals=bool(data.get('enable_meta_rivals',True))
            for name in ('meta_rivals','meta_probe_pending','meta_rival_checkpoints',
                         'meta_rival_retry_after'):
                raw=data.get(name,{})
                setattr(obj,name,deepcopy(raw) if isinstance(raw,dict) else {})
        if version>=11:
            obj.enable_learner_synthesis=bool(data.get('enable_learner_synthesis',True))
            for name in ('learner_synthesis_counts','learner_synthesis_checkpoints',
                         'learner_retry_after'):
                raw=data.get(name,{})
                setattr(obj,name,deepcopy(raw) if isinstance(raw,dict) else {})
        if version>=12:
            limit=data.get('meta_search_cpu_limit_s')
            obj.meta_search_cpu_limit_s=(float(limit) if type(limit) in (int,float)
                                         and 0<float(limit)<=30 else None)
            for name in ('meta_search_cpu_spent_s','meta_search_exhausted'):
                raw=data.get(name,{})
                setattr(obj,name,deepcopy(raw) if isinstance(raw,dict) else {})
        obj._reconcile_meta_primitives()
        # V1 persistence had no AIKR summaries.  Reconstruct conservative budget
        # rows from aggregate evidence so old checkpoints remain usable.
        if version==1:
            for fam,sigs in obj.exact.items():
                for sig,strategies in sigs.items():
                    for strategy,row in strategies.items():
                        trials=max(0,int(row.get('trials',0))); succ=max(0,int(row.get('success',0)))
                        if trials<=0: continue
                        avg=max(0.001,float(row.get('cost',0.0))/trials)
                        quality=(succ+1.0)/(trials+2.0)
                        obj.budgets.setdefault(fam,{}).setdefault(sig,{})[strategy]={
                            'trials':trials,'successes':succ,'priority':quality,
                            'durability':min(0.995,1.0-exp(-trials/5.0)),
                            'quality':quality,'ema_cost':avg,'last_tick':0,
                        }
        return obj
