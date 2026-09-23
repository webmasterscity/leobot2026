"""Question transformations and conditional rule acquisition.

This bounded learner stores hypotheses on Bot and only promotes executable
rules after independent evidence and structural checks.
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations

from .core import Atom, Rule
from .language import normalize


class ConditionalLearningMixin:
    @staticmethod
    def _construction_shape(construction) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        """Abstract a construction into semantic slots and fixed-token positions."""
        slot_pos={f'{{{slot["name"]}}}':int(slot['path'][1])
                  for slot in construction.slots
                  if len(slot.get('path',()))==2 and slot['path'][0]=='args'
                  and isinstance(slot['path'][1],int)}
        if len(slot_pos)!=len(construction.slots):
            return None
        shape=[]; fixed=[]
        for tok in construction.surface.split():
            if tok in slot_pos:
                shape.append(f'A{slot_pos[tok]}')
            else:
                shape.append(f'F{len(fixed)}'); fixed.append(tok)
        return tuple(shape),tuple(fixed)

    @classmethod
    def _question_transform(cls, assertion, query) -> dict | None:
        """Derive one predicate-independent question transformation hypothesis."""
        af=assertion.frame; qf=query.frame
        if af.get('act')!='assert' or qf.get('act')!='query' or af.get('pred')!=qf.get('pred'):
            return None
        aargs=list(af.get('args',[])); qargs=list(qf.get('args',[]))
        if len(aargs)!=len(qargs) or not (1 <= len(aargs) <= 3):
            return None
        answers=[i for i,v in enumerate(qargs) if isinstance(v,str) and v.startswith('?')]
        if len(answers)!=1:
            return None
        answer_pos=answers[0]
        ashape=cls._construction_shape(assertion)
        qshape=cls._construction_shape(query)
        if ashape is None or qshape is None:
            return None
        aseq,afixed=ashape; qseq,qfixed=qshape
        # Fixed assertion tokens must be unique so references cannot silently pick
        # one occurrence of a repeated word.
        if len(set(afixed))!=len(afixed):
            return None
        fixed_index={tok:i for i,tok in enumerate(afixed)}
        wh={'que','quien','cual','donde','cuando','cuanto','como'}
        out=[]; refs=set()
        qslot={f'{{{slot["name"]}}}':int(slot['path'][1]) for slot in query.slots}
        for tok in query.surface.split():
            if tok in qslot:
                pos=qslot[tok]
                if pos==answer_pos:
                    return None
                out.append(f'A{pos}')
            elif tok in fixed_index:
                idx=fixed_index[tok]; out.append(f'F{idx}'); refs.add(idx)
            elif tok in wh:
                out.append('L:'+tok)
            else:
                return None
        if refs != set(range(len(afixed))):
            return None
        key=json.dumps({'assert_shape':aseq,'answer_pos':answer_pos,'query_shape':out},
                       ensure_ascii=False,separators=(',',':'),sort_keys=True)
        return {'key':key,'assert_shape':list(aseq),'answer_pos':answer_pos,
                'query_shape':out,'literal_wh':[x[2:] for x in out if x.startswith('L:')]}

    def _register_question_transform(self, pred: str, learned_text: str) -> dict | None:
        queries=[c for c in self.language.constructions if c.frame.get('act')=='query'
                 and c.frame.get('pred')==pred and c.parse(learned_text) is not None]
        assertions=[c for c in self.language.constructions if c.frame.get('act')=='assert'
                    and c.frame.get('pred')==pred]
        proposals={}
        for a in assertions:
            for q in queries:
                t=self._question_transform(a,q)
                if t: proposals[t['key']]=t
        if len(proposals)!=1:
            return None
        t=next(iter(proposals.values())); state=self.question_transform_hypotheses.get(t['key'])
        if state is None:
            state={**t,'support_predicates':[],'promoted':False}
            self.question_transform_hypotheses[t['key']]=state
        if pred not in state['support_predicates']:
            state['support_predicates'].append(pred)
        if len(state['support_predicates'])>=2:
            state['promoted']=True
            # A newly promoted transform may benefit relations learned earlier.
            for promotion in list(self.raw_relation_promotions.values()):
                self._apply_question_transforms(promotion)
        self.training_reports.append({'type':'question_transform_support','predicate':pred,
                                      'transform':t['key'],'support':len(state['support_predicates']),
                                      'promoted':state['promoted']})
        return {'transform':t['key'],'support':len(state['support_predicates']),
                'promoted':state['promoted']}

    def _apply_question_transforms(self, promotion: dict) -> int:
        pred=promotion.get('predicate'); arity=int(promotion.get('arity') or 0)
        evidence=promotion.get('evidence') or []
        if not pred or not evidence or arity < 1:
            return 0
        assertions=[c for c in self.language.constructions if c.frame.get('act')=='assert'
                    and c.frame.get('pred')==pred]
        if not assertions:
            return 0
        added=0
        for assertion in assertions:
            shape=self._construction_shape(assertion)
            if shape is None: continue
            aseq,afixed=shape
            for state in self.question_transform_hypotheses.values():
                if not state.get('promoted') or tuple(state.get('assert_shape',()))!=aseq:
                    continue
                answer_pos=int(state['answer_pos'])
                if answer_pos>=arity: continue
                args=list(evidence[0].get('args',[]))
                if len(args)!=arity: continue
                tokens=[]; valid=True
                for part in state.get('query_shape',[]):
                    if part.startswith('A'):
                        pos=int(part[1:])
                        if pos>=len(args): valid=False; break
                        tokens.append(args[pos])
                    elif part.startswith('F'):
                        idx=int(part[1:])
                        if idx>=len(afixed): valid=False; break
                        tokens.append(afixed[idx])
                    elif part.startswith('L:'):
                        tokens.append(part[2:])
                    else:
                        valid=False; break
                if not valid: continue
                frame={'act':'query','pred':pred,'args':list(args)}; frame['args'][answer_pos]='?answer'
                text=' '.join(tokens)
                # Evaluate the generated form as a question.  Before a query
                # construction exists, a broad assertion slot may absorb the WH
                # token (e.g. ``que``) as data; that must not block a learned
                # speech-act transform.
                prior=self._semantic_parse('¿'+text+'?')
                if prior.get('status')=='parsed' and prior.get('frame')==frame:
                    continue
                if prior.get('status')!='unrecognized':
                    continue
                try:
                    changed=self.language.teach(text,frame,'learned_question_transform',[state['key']])
                except ValueError:
                    continue
                added += bool(changed)
                if changed:
                    self.training_reports.append({'type':'question_transform_applied','predicate':pred,
                                                  'transform':state['key'],'example':text})
        return added

    def _hypothetical_raw_surface(self, texts: list[str]) -> dict | None:
        """Find one safe 1--3 role anti-unified surface without asserting facts."""
        unique=[]
        for text in texts:
            norm=normalize(text)
            if norm not in unique:
                unique.append(norm)
        if len(unique) < self.raw_relation_min_support:
            return None
        candidate_surfaces={}
        for a,b in combinations(unique,2):
            proposal=self._raw_relation_pair_surface(a,b,max_slots=self.raw_relation_max_arity)
            if proposal:
                surface,arity=proposal
                candidate_surfaces[surface]=arity
        viable=[]
        for surface,arity in sorted(candidate_surfaces.items()):
            support=[]; unsafe=False
            for text in unique:
                rows=self._raw_relation_match(surface,text,limit=2)
                if len(rows)>1:
                    unsafe=True; break
                if len(rows)==1:
                    support.append((text,rows[0]))
            required=max(self.raw_relation_min_support,arity)
            if unsafe or len(support) < required:
                continue
            role_values=[{args[i] for _,args in support} for i in range(arity)]
            if any(len(values) != len(support) for values in role_values):
                continue
            if len({args for _,args in support}) != len(support):
                continue
            fixed=[t for t in surface.split() if not t.startswith('{s')]
            rank=(len(support),len(fixed),sum(map(len,fixed)))
            viable.append((rank,surface,arity,support))
        if not viable:
            return None
        best_rank=max(v[0] for v in viable)
        best=[v for v in viable if v[0]==best_rank]
        if len(best)!=1:
            return {'status':'ambiguous','candidates':[v[1] for v in best]}
        _,surface,arity,support=best[0]
        return {'status':'ready','surface':surface,'arity':arity,'support':support}

    def _teach_hypothetical_surface(self, proposal: dict, source: str) -> dict:
        """Install a raw clause construction while deliberately adding zero facts."""
        surface=proposal['surface']; arity=int(proposal['arity'])
        pred=self._raw_relation_predicate(surface,arity)
        evidence=[]; changed=False
        for text,args in proposal['support']:
            frame={'act':'assert','pred':pred,'args':list(args)}
            try:
                changed=self.language.teach(text,frame,source,[f'antiunified:{surface}']) or changed
            except ValueError:
                return {'status':'ambiguous','surface':surface,'reason':'alignment_failed'}
            evidence.append({'text':text,'args':list(args),'fact_id':None,'hypothetical':True})
        promotion={'predicate':pred,'surface':surface,'arity':arity,'support':len(evidence),
                   'evidence':evidence,'mechanism':'hypothetical_clause_antiunification_v58',
                   'hypothetical_only':True}
        prior=self.raw_relation_promotions.get(surface)
        if prior is None:
            self.raw_relation_promotions[surface]=promotion
        elif prior.get('predicate') != pred or int(prior.get('arity') or 0) != arity:
            return {'status':'ambiguous','surface':surface,'reason':'promotion_conflict'}
        self.training_reports.append({'type':'hypothetical_raw_surface_promoted',**promotion})
        self._apply_question_transforms(promotion)
        return {'status':'learned','construction_added':bool(changed),**promotion}

    @staticmethod
    def _conditional_split_options(body_text: str, max_options: int = 256) -> list[tuple[str, ...]]:
        """Enumerate evidence candidates for conjunction boundaries.

        Every standalone ``y`` is a *candidate* boundary, never a boundary by fiat.
        We enumerate all subsets that fit the core Rule limit (16 antecedents).  If
        the finite segmentation budget would be exceeded, return no candidates so
        callers abstain instead of treating a truncated search as uniquely safe.
        """
        norm=normalize(body_text); tokens=norm.split()
        boundaries=[i for i,tok in enumerate(tokens) if tok=='y' and 0<i<len(tokens)-1]
        if not boundaries:
            return [(norm,)]
        options=[]
        max_cuts=min(len(boundaries),15)  # Rule supports at most 16 body atoms.
        for cut_count in range(max_cuts+1):
            for cuts in combinations(boundaries,cut_count):
                if len(options)>=max_options:
                    return []
                pieces=[]; start=0; valid=True
                for cut in cuts:
                    piece=' '.join(tokens[start:cut]).strip()
                    if not piece:
                        valid=False; break
                    pieces.append(piece); start=cut+1
                if not valid:
                    continue
                tail=' '.join(tokens[start:]).strip()
                if not tail:
                    continue
                pieces.append(tail)
                if len(pieces)<=16:
                    options.append(tuple(pieces))
        # More than 15 candidate conjunction boundaries cannot be exhaustively
        # represented by a 16-atom rule, therefore the utterance is unsafe here.
        if len(boundaries)>15:
            return []
        return options

    def _conditional_clause_form(self, clause: str) -> tuple[str, bool] | None:
        """Return affirmative surface text plus explicit polarity for a clause.

        In the safe default path, one standalone ``no`` is treated as grammar and
        removed before raw surface induction.  More than one is ambiguous.  The
        legacy extensional-grounding mode preserves its historical lexical path.
        """
        norm=normalize(clause); tokens=norm.split()
        if self.allow_extensional_grounding:
            return norm, False
        positions=[i for i,tok in enumerate(tokens) if tok=='no']
        if not positions:
            return norm, False
        if len(positions)!=1 or len(tokens)<3:
            return None
        i=positions[0]
        affirmative=' '.join(tokens[:i]+tokens[i+1:])
        if len(affirmative.split())<2:
            return None
        return affirmative, True

    @staticmethod
    def _slot_variation_ok(rows: list[tuple], arg_index: int, arity: int) -> bool:
        if not rows:
            return False
        tuples=[r[arg_index] for r in rows]
        return all(len({args[i] for args in tuples})==len(tuples) for i in range(arity))

    @staticmethod
    def _conditional_dependency_connected(body_args: list[tuple[str, ...]],
                                          head_args: tuple[str, ...]) -> bool:
        """Require an evidence-backed variable path from every raw clause to the head.

        When clause meanings are still opaque, a standalone ``y`` can be either
        grammar inside one relation or a conjunction boundary.  Maximizing the
        number of cuts alone over-segments phrases such as ``compra y vende``.
        A safe raw decomposition therefore needs each induced antecedent to join
        the same variable-dependency component as the consequent.  Grounded
        conditionals are not subject to this extra bootstrap restriction because
        their clause meanings are already known independently.
        """
        if not body_args or not head_args:
            return False
        nodes=[set(args) for args in body_args]+[set(head_args)]
        if any(not node for node in nodes):
            return False
        seen={len(nodes)-1}; frontier=[len(nodes)-1]
        while frontier:
            i=frontier.pop()
            for j,node in enumerate(nodes):
                if j in seen:
                    continue
                if nodes[i] & node:
                    seen.add(j); frontier.append(j)
        return len(seen)==len(nodes)

    def _observe_conditional_bootstrap(self, text: str, body_text: str, head_text: str,
                                       source: str = 'conversación') -> dict:
        """Bootstrap opaque clause meanings and polarity from hypothetical rules.

        V5.14 generalizes V5.9's evidence-selected conjunction segmentation to
        multiple antecedents within a finite ambiguity budget, while V5.12 polarity handling
        remains unchanged. Raw surfaces are induced on the affirmative clause form.  A stable standalone
        ``no`` becomes logical polarity and is replayed through V5.10 after the
        base construction is learned.  Hypothetical episodes still add zero facts.
        """
        norm=normalize(text)
        episode={'text':norm,'body':normalize(body_text),'head':normalize(head_text),'source':source}
        if not any(o.get('text')==episode['text'] for o in self.conditional_bootstrap_observations):
            self.conditional_bootstrap_observations.append(episode)
            if len(self.conditional_bootstrap_observations)>96:
                self.conditional_bootstrap_observations=self.conditional_bootstrap_observations[-96:]
        observations=list(self.conditional_bootstrap_observations)

        head_candidates={}
        for a,b in combinations(observations,2):
            fa=self._conditional_clause_form(a['head']); fb=self._conditional_clause_form(b['head'])
            if fa is None or fb is None or fa[1]!=fb[1]:
                continue
            hp=self._raw_relation_pair_surface(fa[0],fb[0],max_slots=self.raw_relation_max_arity)
            if hp:
                head_candidates[(hp[0],hp[1],fa[1])]=(hp[0],hp[1],fa[1])

        families=[]
        potentials=[]
        split_spaces=[self._conditional_split_options(o['body']) for o in observations]
        if any(not opts for opts in split_spaces):
            return {'status':'conditional_bootstrap_ambiguous','support':0,
                    'reason':'conjunction_segmentation_budget_exceeded'}
        body_counts=sorted({len(split) for opts in split_spaces for split in opts})
        for body_count in body_counts:
            body_candidates={}
            for oa,ob in combinations(observations,2):
                opts_a=[x for x in self._conditional_split_options(oa['body']) if len(x)==body_count]
                opts_b=[x for x in self._conditional_split_options(ob['body']) if len(x)==body_count]
                for sa in opts_a:
                    for sb in opts_b:
                        proposals=[]; ok=True
                        for ca,cb in zip(sa,sb):
                            fa=self._conditional_clause_form(ca); fb=self._conditional_clause_form(cb)
                            if fa is None or fb is None or fa[1]!=fb[1]:
                                ok=False; break
                            p=self._raw_relation_pair_surface(fa[0],fb[0],max_slots=self.raw_relation_max_arity)
                            if p is None:
                                ok=False; break
                            proposals.append((p[0],p[1],fa[1]))
                        if ok:
                            key=tuple(proposals); body_candidates[key]=proposals
            for _,proposals in body_candidates.items():
                for hsurf,harity,hnegative in head_candidates.values():
                    rows=[]; unsafe=False
                    for obs in observations:
                        hf=self._conditional_clause_form(obs['head'])
                        if hf is None or hf[1]!=hnegative:
                            continue
                        hm=self._raw_relation_match(hsurf,hf[0],limit=2)
                        if len(hm)>1:
                            unsafe=True; break
                        if len(hm)!=1:
                            continue
                        matches=[]
                        for split in self._conditional_split_options(obs['body']):
                            if len(split)!=body_count:
                                continue
                            body_args=[]; affirmative_clauses=[]; valid=True
                            for clause,(surf,arity,negative) in zip(split,proposals):
                                cf=self._conditional_clause_form(clause)
                                if cf is None or cf[1]!=negative:
                                    valid=False; break
                                m=self._raw_relation_match(surf,cf[0],limit=2)
                                if len(m)!=1:
                                    valid=False; break
                                affirmative_clauses.append(cf[0]); body_args.append(m[0])
                            if valid:
                                matches.append((split,affirmative_clauses,body_args))
                        if len(matches)>1:
                            unsafe=True; break
                        if len(matches)==1:
                            rows.append((obs,matches[0][0],matches[0][1],matches[0][2],hf[0],hm[0]))
                    required=max(self.raw_relation_min_support,body_count,harity,*(arity for _,arity,_ in proposals))
                    if unsafe:
                        continue
                    # Raw conjunction boundaries are underdetermined by the token
                    # ``y`` alone.  Reject decompositions that create an isolated
                    # clause disconnected from the consequent.  This preserves
                    # lexical uses such as ``compra y vende`` while still allowing
                    # evidence-linked chains of three or more antecedents.
                    if body_count>1 and any(
                        not self._conditional_dependency_connected(r[3],r[5])
                        for r in rows
                    ):
                        continue
                    good=True
                    for j,(_,arity,_) in enumerate(proposals):
                        tuples=[r[3][j] for r in rows]
                        if any(len({args[i] for args in tuples})!=len(tuples) for i in range(arity)):
                            good=False; break
                    if not good:
                        continue
                    if any(len({r[5][i] for r in rows})!=len(rows) for i in range(harity)):
                        continue
                    # Horn safety: every consequent role must already be bound by
                    # at least one antecedent role in every supporting episode.
                    # Otherwise repeated hypothetical wording could teach two
                    # opaque surfaces even though no executable relation connects
                    # them, which V5.6 correctly treated as unresolved noise.
                    if any(any(value not in {v for args in r[3] for v in args}
                               for value in r[5]) for r in rows):
                        continue
                    if len({(tuple(r[3]),r[5]) for r in rows})!=len(rows):
                        continue
                    fixed=[]
                    for surf,_,_ in proposals:
                        fixed.extend(t for t in surf.split() if not t.startswith('{s'))
                    fixed.extend(t for t in hsurf.split() if not t.startswith('{s'))
                    rank=(len(rows),body_count,len(fixed),sum(map(len,fixed)))
                    # A richer connected segmentation can require more evidence
                    # solely because it has more antecedents.  Record it before
                    # the support threshold so a prematurely eligible coarser
                    # decomposition cannot win just because it is cheaper.  Two
                    # examples are never enough to block; the ordinary minimum
                    # support must already back the richer structural hypothesis.
                    if len(rows)>=self.raw_relation_min_support:
                        potentials.append((body_count,required,len(rows),rank,proposals,hsurf,harity,hnegative,rows))
                    if len(rows)<required:
                        continue
                    families.append((rank,proposals,hsurf,harity,hnegative,rows))
        max_potential_count=max((p[0] for p in potentials),default=0)
        max_eligible_count=max((len(f[1]) for f in families),default=0)
        if max_potential_count>max_eligible_count:
            richer=[p for p in potentials if p[0]==max_potential_count]
            return {'status':'conditional_unresolved','bootstrap_status':'pending',
                    'support':max(p[2] for p in richer),
                    'required':min(p[1] for p in richer),
                    'candidate_antecedents':max_potential_count,
                    'reason':'richer_connected_segmentation_needs_more_support'}
        if not families:
            current_splits=self._conditional_split_options(body_text)
            has_conjunction=any(len(x)>1 for x in current_splits) if current_splits else True
            return {'status':'conditional_unresolved','bootstrap_status':'pending',
                    'support':min(len(observations),self.raw_relation_min_support-1),
                    'required':self.raw_relation_min_support,
                    'reason':'raw_conjunction_bootstrap_not_yet_safe' if has_conjunction
                             else 'insufficient_hypothetical_support'}
        best_rank=max(f[0] for f in families); best=[f for f in families if f[0]==best_rank]
        if len(best)!=1:
            return {'status':'conditional_bootstrap_ambiguous','support':best_rank[0],
                    'candidates':[{'bodies':[p[0] for p in f[1]],'head':f[2],
                                   'body_negative':[p[2] for p in f[1]],'head_negative':f[4]}
                                  for f in best]}
        _,proposals,hsurf,harity,hnegative,rows=best[0]
        promotion_required=max(self.raw_relation_min_support,len(proposals),harity,*(arity for _,arity,_ in proposals))
        body_reports=[]
        for j,(surf,arity,negative) in enumerate(proposals):
            proposal={'surface':surf,'arity':arity,
                      'support':[(r[2][j],r[3][j]) for r in rows]}
            report=self._teach_hypothetical_surface(proposal,'conditional_hypothesis_v512')
            report['negative']=negative
            body_reports.append(report)
        head_proposal={'surface':hsurf,'arity':harity,'support':[(r[4],r[5]) for r in rows]}
        head_report=self._teach_hypothetical_surface(head_proposal,'conditional_hypothesis_v512')
        head_report['negative']=hnegative
        if any(r.get('status')!='learned' for r in body_reports) or head_report.get('status')!='learned':
            return {'status':'conditional_bootstrap_ambiguous','support':len(rows),
                    'body_reports':body_reports,'head_report':head_report}
        replay=[]
        for obs,_,_,_,_,_ in rows:
            rr=self.observe_conditional_rule(obs['text'],_allow_bootstrap=False,
                                             source=obs.get('source','conversación'))
            replay.append(rr)
        learned=next((r for r in reversed(replay) if r and r.get('status') in
                      ('conditional_rule_learned','conditional_rule_confirmed')),None)
        promotion={'body_surfaces':[r['surface'] for r in body_reports],
                   'head_surface':head_report['surface'],
                   'body_predicates':[r['predicate'] for r in body_reports],
                   'head_predicate':head_report['predicate'],
                   'body_negative':[r['negative'] for r in body_reports],
                   'head_negative':head_report['negative'],
                   'support':len(rows),'episodes':[{'text':r[0]['text'],'source':r[0].get('source','conversación')}
                                                  for r in rows],
                   'rule_id':learned.get('rule_id') if learned else None,
                   'antecedents':len(body_reports)}
        if promotion not in self.conditional_bootstrap_promotions:
            self.conditional_bootstrap_promotions.append(promotion)
        self.training_reports.append({'type':'conditional_bootstrap_promoted',**promotion})
        return {'status':'conditional_bootstrap_learned','support':len(rows),
                'required':promotion_required,'bodies':body_reports,'head':head_report,
                'body':body_reports[0] if len(body_reports)==1 else None,
                'rule':learned,'antecedents':len(body_reports),'facts_added':0}

    def observe_conditional_rule(self, text: str, _allow_bootstrap: bool = True,
                                 source: str = 'conversación') -> dict | None:
        """Learn a bounded Horn rule from repeated grounded Spanish conditionals.

        ``si ... entonces ...`` is a teaching episode, never a pair of facts.
        V5.14 accepts one antecedent or an unambiguously segmentable conjunction of
        grounded antecedents within the finite segmentation budget.  Equality of argument values across antecedents
        defines shared logical variables.  Promotion needs at least three
        independent episodes with the same variable topology and every variable
        must vary across the supporting episodes, preventing silent constants.
        """
        norm = normalize(text)
        if not norm.startswith('si '):
            return None
        rest = norm[3:].strip()
        if rest.count(' entonces ') != 1:
            return {'status':'conditional_malformed','support':0,
                    'reason':'expected_single_entonces'}
        body_text, head_text = (x.strip() for x in rest.split(' entonces ', 1))
        if not body_text or not head_text:
            return {'status':'conditional_malformed','support':0,'reason':'empty_clause'}

        def grounded_assertion(clause: str) -> dict | None:
            parsed=self._semantic_parse(clause)
            frame=parsed.get('frame') or {}
            if parsed.get('status')!='parsed' or frame.get('act')!='assert':
                return None
            args=list(frame.get('args',[]))
            if not (1 <= len(args) <= 8) or any(not isinstance(v,str) or v.startswith('?') for v in args):
                return None
            # A broad slot is allowed to contain many words, but during
            # conditional segmentation it must not silently swallow a standalone
            # conjunction candidate.  If ``y`` is lexical grammar of the learned
            # construction it remains outside the argument values and therefore
            # passes this check.  If it lands inside an argument, the boundary is
            # semantically unresolved and we abstain instead of preferring the
            # greedy parse.
            if any('y' in normalize(v).split() for v in args):
                return None
            return frame

        # Candidate ``y`` boundaries are accepted only when one multi-clause
        # segmentation yields independently grounded assertions.  If no such
        # segmentation exists, the whole antecedent may still be one assertion
        # whose lexical surface legitimately contains ``y``.
        split_options=self._conditional_split_options(body_text)
        if not split_options:
            return {'status':'conditional_ambiguous','support':0,
                    'reason':'conjunction_segmentation_budget_exceeded'}
        conjunctive=[]
        for split in split_options:
            if len(split)<=1:
                continue
            frames=[grounded_assertion(clause) for clause in split]
            if all(frame is not None for frame in frames):
                conjunctive.append(tuple(frames))
        if len(conjunctive)>1:
            return {'status':'conditional_ambiguous','support':0,
                    'reason':'multiple_valid_conjunction_segmentations'}
        if len(conjunctive)==1:
            bodies=list(conjunctive[0])
        else:
            single=grounded_assertion(body_text)
            if single is None:
                if _allow_bootstrap:
                    return self._observe_conditional_bootstrap(norm,body_text,head_text,source=source)
                return {'status':'conditional_unresolved','support':0,
                        'body_status':'unresolved','head_status':self._semantic_parse(head_text).get('status')}
            bodies=[single]
        head=grounded_assertion(head_text)
        if head is None:
            if _allow_bootstrap and len(bodies)==1:
                return self._observe_conditional_bootstrap(norm,body_text,head_text,source=source)
            return {'status':'conditional_unresolved','support':0,
                    'body_status':'parsed','head_status':self._semantic_parse(head_text).get('status')}

        body_args=[list(f.get('args',[])) for f in bodies]
        flat=[v for args in body_args for v in args]
        # Equality topology -> logical variable classes.  The same value appearing
        # in two antecedents becomes the same variable in the induced Horn rule.
        class_by_value={}; body_classes=[]; class_values=[]
        for value in flat:
            if value not in class_by_value:
                class_by_value[value]=len(class_by_value); class_values.append(value)
            body_classes.append(class_by_value[value])
        hargs=list(head.get('args',[])); head_classes=[]
        for value in hargs:
            if value not in class_by_value:
                return {'status':'conditional_alignment_failed','support':0,
                        'reason':'each_consequent_argument_must_come_from_antecedent_variables'}
            head_classes.append(class_by_value[value])

        body_spec=[{'pred':f.get('pred'),'arity':len(args)} for f,args in zip(bodies,body_args)]
        pair={'bodies':body_spec,'head_pred':head.get('pred'),'head_arity':len(hargs)}
        pair_key=json.dumps(pair,ensure_ascii=False,separators=(',',':'),sort_keys=True)
        state=self.conditional_rule_hypotheses.get(pair_key)
        structure={'body_classes':body_classes,'head_classes':head_classes}
        if state is None:
            state={**pair,**structure,
                   # compatibility/diagnostic aliases for the one-body V5.6 case
                   'body_pred':body_spec[0]['pred'] if len(body_spec)==1 else None,
                   'body_arity':body_spec[0]['arity'] if len(body_spec)==1 else None,
                   'mapping':head_classes if len(body_spec)==1 else None,
                   'observations':[],'promoted':False,'conflict':False,'rule_id':None}
            self.conditional_rule_hypotheses[pair_key]=state

        episode_id=json.dumps({'bodies':body_args,'head':hargs},ensure_ascii=False,separators=(',',':'))
        duplicate=any(o.get('episode_id')==episode_id for o in state.get('observations',[]))
        same_structure=(list(state.get('body_classes',[]))==body_classes and
                        list(state.get('head_classes',[]))==head_classes)
        if not same_structure:
            state['conflict']=True; withdrawn=False
            if state.get('promoted') and state.get('rule_id'):
                self.kb.remove_rule(state['rule_id']); state['promoted']=False; withdrawn=True
            state.setdefault('conflicts',[]).append({'text':norm,'body_args':body_args,'head_args':hargs,
                                                       'source':source,**structure})
            return {'status':'conditional_rule_ambiguous','support':len(state.get('observations',[])),
                    'body_classes':list(state.get('body_classes',[])),
                    'head_classes':list(state.get('head_classes',[])),
                    'conflicting_structure':structure,'promoted':False,'withdrawn':withdrawn}
        if not duplicate:
            state.setdefault('observations',[]).append({'episode_id':episode_id,'text':norm,
                                                        'body_args':body_args,'head_args':hargs,
                                                        'class_values':class_values,'source':source})
        support=len(state.get('observations',[])); min_support=max(3,self.raw_relation_min_support,len(bodies))
        variable_count=(max(body_classes)+1) if body_classes else 0
        varying=support>=min_support and all(
            len({o['class_values'][i] for o in state['observations']})>=min_support
            for i in range(variable_count)
        )
        diagnostic={'mapping':head_classes if len(bodies)==1 else None,
                    'body_classes':body_classes,'head_classes':head_classes,
                    'antecedents':len(bodies)}
        if state.get('conflict'):
            return {'status':'conditional_rule_ambiguous','support':support,'promoted':False,
                    'reason':'conflicting_variable_topology',**diagnostic}
        if support<min_support or not varying:
            return {'status':'conditional_rule_pending','support':support,'required':min_support,
                    'promoted':False,'duplicate':duplicate,
                    'reason':'need_independent_varying_examples' if support>=min_support else 'need_more_examples',
                    **diagnostic}

        if not state.get('promoted'):
            variables=tuple(f'?v{i}' for i in range(variable_count)); atoms=[]; cursor=0
            for frame,args in zip(bodies,body_args):
                classes=body_classes[cursor:cursor+len(args)]; cursor+=len(args)
                atoms.append(Atom(frame['pred'],tuple(variables[i] for i in classes)))
            head_atom=Atom(head['pred'],tuple(variables[i] for i in head_classes))
            signature=json.dumps({**pair,**structure},sort_keys=True,separators=(',',':'))
            rid='conditional_'+hashlib.sha256(signature.encode()).hexdigest()[:16]
            evidence=tuple(o['episode_id'] for o in state['observations'][:min_support])
            rule=Rule(rid,head_atom,tuple(atoms),origin='learned',evidence=evidence)
            self.kb.add_rule(rule); state['promoted']=True; state['rule_id']=rid
            self.training_reports.append({'type':'conditional_rule_learned','rule_id':rid,
                                          'body_preds':[x['pred'] for x in body_spec],
                                          'head_pred':head['pred'],'body_classes':body_classes,
                                          'head_classes':head_classes,'support':support,
                                          'sources':[o.get('source','conversación') for o in state['observations'][:min_support]]})
            return {'status':'conditional_rule_learned','support':support,'required':min_support,
                    'promoted':True,'rule_id':rid,'rule':str(rule),**diagnostic}
        return {'status':'conditional_rule_confirmed','support':support,'required':min_support,
                'promoted':True,'rule_id':state.get('rule_id'),'duplicate':duplicate,**diagnostic}

