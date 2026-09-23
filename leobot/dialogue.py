"""Conversation, corrections, discourse, and response construction.

The public Bot facade owns state; this mixin interprets turns and calls the
learned document, language, procedure, and symbolic mechanisms.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations

from .core import Atom
from .language import normalize
from .procedures import _surface


class DialogueMixin:
    def _semantic_parse(self, text: str) -> dict:
        """Parse an utterance plus safe speech-act and polarity composition.

        V5.10 treats the standalone Spanish token ``no`` as explicit logical
        polarity *only when deleting that token yields one already-grounded
        assertion/query construction*.  This prevents a broad argument slot from
        silently storing values such as ``"ana no"`` when the user intended a
        negation.  Unknown negated wording remains unknown and never becomes raw
        positive support.
        """
        norm=normalize(text); tokens=norm.split()
        parsed=self.language.parse(text)
        no_positions=[i for i,tok in enumerate(tokens) if tok=='no']
        polarity=None
        if (not self.allow_extensional_grounding) and len(no_positions)==1 and len(tokens)>1:
            i=no_positions[0]
            affirmative=' '.join(tokens[:i]+tokens[i+1:])
            base=self.language.parse(affirmative)
            if base.get('status')=='parsed':
                frame=dict(base.get('frame') or {})
                pred=frame.get('pred')
                if frame.get('act') in ('assert','query') and isinstance(pred,str) and pred:
                    frame['pred']=pred[1:] if pred.startswith('!') else '!'+pred
                    parsed={'status':'parsed','frame':frame,'alternatives':[frame],
                            'composed_paraphrase':base.get('composed_paraphrase',False),
                            'polarity_composition':'explicit_no'}
                    polarity='explicit_no'
        elif (not self.allow_extensional_grounding) and len(no_positions)>1:
            # Do not let a permissive slot parser reinterpret repeated negators as
            # entity text.  An explicitly taught fixed construction can be added
            # later if such wording is genuinely intended.
            return {'status':'unrecognized','frame':None,'alternatives':[],
                    'composed_paraphrase':False,'reason':'negation_ambiguous'}

        if (not self.allow_extensional_grounding) and polarity is None and no_positions and parsed.get('status')=='parsed':
            # If ``no`` survived only because a broad slot swallowed it, abstain.
            frame=parsed.get('frame') or {}
            concrete=[normalize(str(v)) for v in frame.get('args',[])
                      if not (isinstance(v,str) and v.startswith('?'))]
            if any('no' in v.split() for v in concrete):
                return {'status':'unrecognized','frame':None,'alternatives':[],
                        'composed_paraphrase':False,'reason':'unresolved_negation'}

        if (self._question_like(text) and parsed.get('status') == 'parsed'
                and (parsed.get('frame') or {}).get('act') == 'assert'):
            starts=('que ','cual ','donde ','cuando ','quien ','cuanto ','como ',
                    'en que ','a que ','de que ','por que ')
            fronted=any(norm.startswith(x) for x in starts)
            if not fronted:
                frame=dict(parsed['frame']); args=list(frame.get('args',[]))
                wh={'que','quien','cual','donde','cuando','cuanto','como'}
                hits=[i for i,v in enumerate(args) if isinstance(v,str) and normalize(v) in wh]
                if len(hits) <= 1:
                    if hits: args[hits[0]]='?answer'
                    frame['act']='query'; frame['args']=args
                    parsed={'status':'parsed','frame':frame,'alternatives':[frame],
                            'composed_paraphrase':parsed.get('composed_paraphrase',False),
                            'speech_act_composition':'assertion_to_query',
                            **({'polarity_composition':polarity} if polarity else {})}
                else:
                    parsed={'status':'unrecognized','frame':None,'alternatives':[],
                            'composed_paraphrase':False,'reason':'speech_act_ambiguous'}
            else:
                parsed={'status':'unrecognized','frame':None,'alternatives':[],
                        'composed_paraphrase':False,'reason':'fronted_wh_requires_query_construction'}
        return parsed

    @staticmethod
    def _event_reference_feedback_instruction(text: str) -> tuple[str,str] | None:
        """Parse an explicit correction of a recent demonstrative reference.

        This is metalinguistic supervision, not semantic guessing.  The target is
        later required to be one of the concrete bindings of the event that was
        actually used, so an arbitrary phrase cannot rewrite unrelated memory.
        """
        cleaned=normalize(re.sub(r'[,;:]+',' ',text)).strip()
        patterns=(
            r'^(?:no\s+)?(eso|esto|aquello)\s+se\s+referia\s+a\s+(.+)$',
            r'^(?:no\s+)?cuando\s+dije\s+(eso|esto|aquello)\s+me\s+referia\s+a\s+(.+)$',
            r'^(?:no\s+)?con\s+(eso|esto|aquello)\s+me\s+referia\s+a\s+(.+)$',
        )
        for pattern in patterns:
            m=re.match(pattern,cleaned)
            if m:
                marker,target=m.groups(); target=target.strip(' .!?')
                if marker and target and len(target)<=512:
                    return marker,target
        return None

    def _facts_referencing_entity(self, value: str) -> list[dict]:
        """Return concrete facts that mention one entity using either KB backend."""
        out={}
        for base,arity in list(getattr(self.kb,'arity',{}).items()):
            if not 1<=int(arity)<=8:
                continue
            for pred in (base,'!'+base):
                for slot in range(int(arity)):
                    args=['?x'+str(i) for i in range(int(arity))];args[slot]=value
                    try:
                        rows=self.kb.matches(Atom(pred,tuple(args)))
                    except ValueError:
                        continue
                    for fact in rows:
                        out[fact['id']]=fact
        return list(out.values())

    def _remove_orphan_document_event(self, event_id: str) -> list[str]:
        """Remove representation facts only when no ordinary fact still uses the event."""
        remaining=[f for f in self._facts_referencing_entity(event_id)
                   if not f['atom'].pred.startswith('_event_')]
        if remaining:
            return []
        removed=[]
        patterns=(Atom('_event_schema',(event_id,'?schema')),
                  Atom('_event_member',(event_id,'?member')),
                  Atom('_event_role',(event_id,'?role','?value')))
        for pattern in patterns:
            for fact in list(self.kb.matches(pattern)):
                if self.kb.remove(fact['id']):
                    removed.append(fact['id'])
        return removed

    def _refresh_event_dependents_after_schema_change(self, structure: dict) -> None:
        """Recompute meta topology and every consumer gate sharing this topology."""
        self._refresh_document_event_meta(structure)
        topology_key,_=self._document_event_topology_key(structure)
        gates=[g for g in self.document_event_reference_hypotheses.values()
               if g.get('topology_key')==topology_key]
        for gate in list(gates):
            self._refresh_document_event_reference_gate(structure,gate.get('predicate'),int(gate.get('slot',0)))

    def teach_event_reference_feedback(self, marker: str, target: str,
                                       source: str='conversación') -> dict:
        """Apply explicit counterevidence to the latest materialized event reference.

        The correction changes the stored downstream fact, retracts an orphaned
        event node, and records why a transferred representation is no longer safe.
        Exact schema counterevidence also withdraws dependent meta-topologies when
        their independent support falls below the original promotion criterion.
        """
        marker=normalize(marker); target_norm=normalize(target)
        chosen=None
        for event in reversed(list(getattr(self.kb,'audit',[]))):
            if event.get('event')!='document_coreference_resolved':
                continue
            fact=self.kb.get_fact(event.get('fact_id')) if hasattr(self.kb,'get_fact') else None
            if fact is None:
                continue
            for ref in event.get('references') or []:
                if normalize(str(ref.get('marker',''))) != marker:
                    continue
                if not any(str(c).startswith('latent_document_event_') for c in ref.get('criteria',[])):
                    continue
                candidates=[e.get('event_candidate') for e in ref.get('evidence',[]) if e.get('event_candidate')]
                if len(candidates)!=1:
                    continue
                chosen=(event,fact,ref,candidates[0]);break
            if chosen:
                break
        if chosen is None:
            return {'status':'event_reference_feedback_unresolved','reason':'no_live_event_reference','marker':marker}
        event,fact,ref,candidate=chosen
        bindings=list(candidate.get('bindings') or [])
        articles={'el','la','los','las','un','una','unos','unas','al'}
        variants={target_norm}
        toks=target_norm.split()
        if toks and toks[0] in articles and len(toks)>1:
            variants.add(' '.join(toks[1:]))
        matches=[value for value in bindings if normalize(str(value)) in variants]
        if len(matches)!=1:
            return {'status':'event_reference_feedback_unresolved','reason':'target_not_unique_event_binding',
                    'marker':marker,'target':target,'event_id':candidate.get('event_id'),
                    'available_bindings':bindings}
        replacement=matches[0]; slot=int(ref.get('slot',-1)); old=fact['atom']
        if not 0<=slot<len(old.args):
            return {'status':'event_reference_feedback_unresolved','reason':'invalid_reference_slot'}
        args=list(old.args); event_id=str(ref.get('antecedent'))
        if args[slot]!=event_id:
            return {'status':'event_reference_feedback_unresolved','reason':'fact_no_longer_uses_event'}
        args[slot]=replacement
        new_id=self.kb.replace(fact['id'],Atom(old.pred,tuple(args)))
        removed_representation=self._remove_orphan_document_event(event_id)

        structure=candidate.get('structure') or {}
        gate_key,_=self._document_event_reference_gate_key(structure,old.pred,slot)
        gate=self.document_event_reference_hypotheses.setdefault(gate_key,{
            'gate_id':self._document_event_reference_gate_key(structure,old.pred,slot)[1],
            'topology_key':self._document_event_topology_key(structure)[0],
            'predicate':old.pred,'slot':slot,'source_schemas':[],'promoted':False,
            'contested':False,'counterexamples':[]})
        counter={'event_id':event_id,'old_fact_id':fact['id'],'new_fact_id':new_id,
                 'marker':marker,'replacement':replacement,'source':source,
                 'schema_id':candidate.get('schema_id')}
        if counter not in gate.setdefault('counterexamples',[]):
            gate['counterexamples'].append(counter);del gate['counterexamples'][:-32]
        gate['contested']=True
        self._refresh_document_event_reference_gate(structure,old.pred,slot)

        exact=candidate.get('mechanism')!='latent_document_event_meta_v527'
        schema_contested=False
        if exact:
            for state in self.document_event_schema_hypotheses.values():
                if state.get('schema_id')!=candidate.get('schema_id'):
                    continue
                state['contested']=True; schema_contested=True
                rows=state.setdefault('counterexamples',[])
                if counter not in rows:
                    rows.append(counter);del rows[:-32]
                self._refresh_event_dependents_after_schema_change(state.get('structure') or {})
                break
        audit={'event':'document_event_reference_corrected','marker':marker,'target':replacement,
               'event_id':event_id,'old_fact_id':fact['id'],'new_fact_id':new_id,
               'removed_representation_fact_ids':removed_representation,
               'gate_id':gate.get('gate_id'),'gate_contested':True,
               'schema_contested':schema_contested,
               'mechanism':'explicit_event_reference_counterevidence_v530','source':source}
        if hasattr(self.kb,'audit'):
            self.kb.audit.append(audit)
        self.training_reports.append({'type':'document_event_reference_corrected',**audit})
        return {'status':'event_reference_corrected','marker':marker,'target':replacement,
                'event_id':event_id,'old_fact_id':fact['id'],'new_fact_id':new_id,
                'removed_representation_fact_ids':removed_representation,
                'gate_id':gate.get('gate_id'),'schema_contested':schema_contested,
                'mechanism':'explicit_event_reference_counterevidence_v530'}

    @staticmethod
    def _paraphrase_instruction(text: str) -> tuple[str, str] | None:
        """Extract an explicit quoted equivalence instruction.

        This is an ordinary metalinguistic interface, not semantic inference: the
        speaker is explicitly supplying equivalence evidence.  Quotes delimit the
        two example utterances so arbitrary text cannot be reinterpreted as code.
        """
        patterns=(
            r'^\s*[«"](.+?)[»"]\s+significa\s+lo\s+mismo\s+que\s+[«"](.+?)[»"]\s*[.!]?\s*$',
            r'^\s*[«"](.+?)[»"]\s+es\s+otra\s+forma\s+de\s+decir\s+[«"](.+?)[»"]\s*[.!]?\s*$',
        )
        for pattern in patterns:
            m=re.match(pattern,text,flags=re.IGNORECASE|re.DOTALL)
            if m:
                left,right=(x.strip() for x in m.groups())
                if left and right and len(left)<=1024 and len(right)<=1024:
                    return left,right
        return None

    def teach_explicit_paraphrase(self, left: str, right: str, source: str = 'conversación') -> dict:
        """Teach one surface from an explicitly declared equivalent utterance.

        Exactly one side must already have an unambiguous semantic frame, unless
        both sides already resolve to the same frame.  The new construction is
        aligned by the existing Language learner, so reordered arguments are
        learned from the concrete example rather than guessed from co-occurrence.
        """
        parsed=[]
        for text in (left,right):
            r=self._semantic_parse(text)
            parsed.append(r if r.get('status')=='parsed' else None)
        if parsed[0] is not None and parsed[1] is not None:
            if parsed[0].get('frame')==parsed[1].get('frame'):
                return {'status':'paraphrase_confirmed','left':left,'right':right,
                        'frame':parsed[0]['frame'],'mechanism':'explicit_equivalence_instruction'}
            return {'status':'paraphrase_conflict','left':left,'right':right,
                    'left_frame':parsed[0].get('frame'),'right_frame':parsed[1].get('frame')}
        if parsed[0] is None and parsed[1] is None:
            return {'status':'paraphrase_unresolved','left':left,'right':right,
                    'reason':'neither_side_has_grounded_frame'}
        known_index=0 if parsed[0] is not None else 1
        new_index=1-known_index
        known=(left,right)[known_index]; new=(left,right)[new_index]
        frame=parsed[known_index]['frame']
        if frame.get('act') not in ('assert','query'):
            return {'status':'paraphrase_unsupported','left':left,'right':right,
                    'reason':'unsupported_speech_act','act':frame.get('act')}
        # Refuse to overwrite an ambiguous or already conflicting surface.
        prior=self._semantic_parse(new)
        if prior.get('status') not in ('unrecognized',):
            return {'status':'paraphrase_conflict','left':left,'right':right,
                    'reason':'new_surface_not_unrecognized','existing':prior}
        try:
            changed=self.language.teach(new,frame,'explicit_paraphrase_instruction',
                                        [f'explicit_equivalence:{known}'])
        except ValueError as exc:
            return {'status':'paraphrase_alignment_failed','left':left,'right':right,
                    'reason':str(exc)}
        check=self._semantic_parse(new)
        if check.get('status')!='parsed' or check.get('frame')!=frame:
            return {'status':'paraphrase_conflict','left':left,'right':right,
                    'reason':'post_teach_not_unique','parsed':check}
        report={'type':'explicit_paraphrase','source':source,'known_text':known,
                'learned_text':new,'frame':frame,'mechanism':'explicit_equivalence_instruction'}
        self.training_reports.append(report)
        meta=self._register_question_transform(frame.get('pred'),new) if frame.get('act')=='query' else None
        return {'status':'paraphrase_learned','left':left,'right':right,
                'known_text':known,'learned_text':new,'frame':frame,
                'construction_added':bool(changed),'mechanism':'explicit_equivalence_instruction',
                'question_transform':meta}

    @staticmethod
    def _token_phrase_hits(tokens: list[str], phrase: tuple[str, ...]) -> list[int]:
        if not phrase or len(phrase)>len(tokens):
            return []
        n=len(phrase)
        return [i for i in range(len(tokens)-n+1) if tuple(tokens[i:i+n])==phrase]

    def _contextual_correction(self, text: str) -> dict | None:
        """Revise discourse facts from explicit, auditable correction evidence.

        V5.16 first tries the strongest evidence available: the text after an
        initial discourse ``no`` is itself parsed as a grounded assertion.  If it
        uniquely identifies a recent fact by predicate and unchanged arguments,
        every changed role (and polarity) is revised together.  If the payload is
        elliptical, grounded construction anchors may identify one or several
        replacement spans; promotion still requires one unique repair.  Nothing in
        this mechanism knows dates, locations, entity types, predicate names or a
        benchmark vocabulary.
        """
        # Internal punctuation is discourse punctuation, not semantic content here.
        cleaned=normalize(re.sub(r'[,;:]+',' ',text))
        tokens=cleaned.split()
        if self._question_like(text) or len(tokens)<2 or tokens[0] != 'no':
            return None
        recent=self._recent_discourse_facts()
        if not recent:
            return {'status':'correction_unresolved','reason':'no_live_previous_fact'}
        payload=tokens[1:]
        if not payload:
            return {'status':'correction_unresolved','reason':'empty_correction'}

        # A second unresolved negator must never be swallowed by a broad slot.
        # If it composes successfully below, polarity is handled explicitly.
        payload_text=' '.join(payload)
        parsed_payload=self._semantic_parse(payload_text)

        def apply_revision(old_fact: dict, new_atom: Atom, mechanism: str,
                           changed_slots: list[int], surface: str | None = None) -> dict:
            old=old_fact['atom']; old_id=old_fact['id']
            if old == new_atom:
                return {'status':'correction_no_change','id':old_id,'predicate':old.pred,
                        'changed_slots':[],'mechanism':mechanism}
            new_id=self.kb.replace(old_id,new_atom)
            self._replace_discourse_fact(old_id,new_id); self.last_result=None
            event={'type':'contextual_correction','old_fact':old_id,'new_fact':new_id,
                   'old_atom':old.as_dict(),'new_atom':new_atom.as_dict(),
                   'changed_slots':list(changed_slots),
                   'polarity_changed':old.pred != new_atom.pred,
                   'surface':surface,'mechanism':mechanism}
            self.training_reports.append(event)
            report={'status':'corrected_contextually','id':new_id,'old_id':old_id,
                    'predicate':new_atom.pred,'old_predicate':old.pred,
                    'changed_slots':list(changed_slots),
                    'polarity_changed':old.pred != new_atom.pred,
                    'mechanism':mechanism}
            if len(changed_slots)==1:
                slot=changed_slots[0]
                report.update({'slot':slot,'old_value':old.args[slot],
                               'new_value':new_atom.args[slot]})
            if surface is not None:
                report['surface']=surface
            return report

        # Strong path: the correction payload is a complete grounded assertion.
        # Match it to recent discourse by semantic predicate plus unchanged roles;
        # do not use mere recency to break an equally plausible semantic tie.
        if parsed_payload.get('status')=='parsed':
            frame=parsed_payload.get('frame') or {}
            if frame.get('act')=='assert':
                args=tuple(frame.get('args',()))
                pred=frame.get('pred')
                if isinstance(pred,str) and args and not any(isinstance(v,str) and v.startswith('?') for v in args):
                    scored=[]
                    for fact in recent:
                        old=fact['atom']
                        if old.pred.lstrip('!') != pred.lstrip('!') or len(old.args)!=len(args):
                            continue
                        equal=sum(a==b for a,b in zip(old.args,args))
                        changed=[i for i,(a,b) in enumerate(zip(old.args,args)) if a!=b]
                        polarity=old.pred!=pred
                        if not changed and not polarity:
                            continue
                        # For multi-role relations, at least one unchanged role is
                        # needed to identify the old proposition.  Unary repairs
                        # are allowed only when one recent fact of that predicate
                        # survives as a candidate.
                        if len(args)>1 and equal<1:
                            continue
                        scored.append((equal,fact,changed,polarity))
                    if scored:
                        best_equal=max(x[0] for x in scored)
                        best=[x for x in scored if x[0]==best_equal]
                        if len(best)!=1:
                            return {'status':'correction_ambiguous','reason':'multiple_grounded_repairs',
                                    'candidates':[{'fact_id':x[1]['id'],'changed_slots':x[2],
                                                   'polarity_changed':x[3]} for x in best]}
                        _,old_fact,changed,_=best[0]
                        return apply_revision(old_fact,Atom(pred,args),'grounded_multi_slot_revision_v516',changed)
        if 'no' in payload:
            return {'status':'correction_unresolved','reason':'unresolved_correction_polarity'}
        if any(tok in ('o','u') for tok in payload):
            return {'status':'correction_ambiguous','reason':'explicit_disjunction'}

        proposals=[]
        for old_fact in recent:
            old=old_fact['atom']
            for construction in self.language.constructions:
                frame=construction.frame
                if frame.get('act')!='assert' or frame.get('pred')!=old.pred:
                    continue
                slot_map={f'{{{slot["name"]}}}':int(slot['path'][1])
                          for slot in construction.slots
                          if len(slot.get('path',()))==2 and slot['path'][0]=='args'
                          and isinstance(slot['path'][1],int)}
                surface=construction.surface.split()
                if not slot_map or any(tok not in surface for tok in slot_map):
                    continue
                for pos,tok in enumerate(surface):
                    if tok not in slot_map:
                        continue
                    slot=slot_map[tok]
                    if not 0 <= slot < len(old.args):
                        continue
                    left=[]; i=pos-1
                    while i>=0 and surface[i] not in slot_map:
                        left.append(surface[i]); i-=1
                    left=list(reversed(left))
                    right=[]; i=pos+1
                    while i<len(surface) and surface[i] not in slot_map:
                        right.append(surface[i]); i+=1

                    left_anchors=[tuple(left[j:]) for j in range(len(left)) if left[j:]]
                    right_anchors=[tuple(right[:j]) for j in range(len(right),0,-1) if right[:j]]
                    candidates=[]
                    for la in left_anchors:
                        for li in self._token_phrase_hits(payload,la):
                            start=li+len(la)
                            for ra in right_anchors:
                                for ri in self._token_phrase_hits(payload,ra):
                                    if ri<=start:
                                        continue
                                    value=' '.join(payload[start:ri]).strip()
                                    if value:
                                        outside=li + (len(payload)-(ri+len(ra)))
                                        candidates.append((value,len(la)+len(ra),sum(map(len,la+ra)),2,outside,
                                                           (start,ri),tuple(range(li,start))+tuple(range(ri,ri+len(ra)))))
                    for la in left_anchors:
                        for li in self._token_phrase_hits(payload,la):
                            start=li+len(la); value=' '.join(payload[start:]).strip()
                            if value:
                                candidates.append((value,len(la),sum(map(len,la)),1,li,
                                                   (start,len(payload)),tuple(range(li,start))))
                    for ra in right_anchors:
                        for ri in self._token_phrase_hits(payload,ra):
                            value=' '.join(payload[:ri]).strip()
                            if value:
                                outside=len(payload)-(ri+len(ra))
                                candidates.append((value,len(ra),sum(map(len,ra)),1,outside,
                                                   (0,ri),tuple(range(ri,ri+len(ra)))))
                    for value,anchor_tokens,anchor_chars,sides,outside,value_span,anchor_idx in candidates:
                        value=normalize(value)
                        if not value or value==normalize(old.args[slot]) or value=='no':
                            continue
                        if value.split()[0]=='no':
                            continue
                        specificity=self.language._specificity(construction)
                        score=(sides,anchor_tokens,anchor_chars,specificity[0],specificity[1],-outside)
                        proposals.append({'fact_id':old_fact['id'],'slot':slot,'value':value,'score':score,
                                          'surface':construction.surface,'value_span':value_span,
                                          'anchor_idx':tuple(anchor_idx)})
        if not proposals:
            return {'status':'correction_unresolved','reason':'no_unique_slot_anchor'}

        # Enumerate compatible repairs per fact.  More than one role may change
        # when different grounded anchors explain non-overlapping payload spans.
        repairs=[]
        by_fact={}
        recency={fact['id']:i for i,fact in enumerate(recent)}
        for proposal in proposals:
            by_fact.setdefault(proposal['fact_id'],[]).append(proposal)
        for fid,rows in by_fact.items():
            # Keep only the strongest evidence for an identical slot/value/span.
            uniq={}
            for p in rows:
                key=(p['slot'],p['value'],p['value_span'])
                if key not in uniq or p['score']>uniq[key]['score']:
                    uniq[key]=p
            rows=list(uniq.values())
            for n in range(1,min(len({p['slot'] for p in rows}),8)+1):
                for combo in combinations(rows,n):
                    slots=[p['slot'] for p in combo]
                    if len(set(slots))!=len(slots):
                        continue
                    ok=True
                    for i,a in enumerate(combo):
                        av=set(range(*a['value_span']))
                        for j,b in enumerate(combo):
                            if i==j: continue
                            bv=set(range(*b['value_span']))
                            if av & bv or av & set(b['anchor_idx']):
                                ok=False; break
                        if not ok: break
                    if not ok:
                        continue
                    explained=set()
                    for p in combo:
                        explained.update(range(*p['value_span'])); explained.update(p['anchor_idx'])
                    outside=len(payload)-len(explained)
                    score=(len(combo),len(explained),sum(p['score'][0] for p in combo),
                           sum(p['score'][1] for p in combo),sum(p['score'][2] for p in combo),
                           -outside,-recency.get(fid,10_000))
                    repair=tuple(sorted((p['slot'],p['value']) for p in combo))
                    repairs.append({'fact_id':fid,'repair':repair,'score':score,
                                    'surface':' | '.join(sorted({p['surface'] for p in combo}))})
        if not repairs:
            return {'status':'correction_unresolved','reason':'no_compatible_slot_repair'}
        best_score=max(r['score'] for r in repairs)
        best={ (r['fact_id'],r['repair']):r for r in repairs if r['score']==best_score }
        if len(best)!=1:
            return {'status':'correction_ambiguous','reason':'multiple_slot_repairs',
                    'candidates':[{'fact_id':fid,'repairs':[{'slot':s,'value':v} for s,v in repair]}
                                  for fid,repair in sorted(best)]}
        (_,repair),proposal=next(iter(best.items()))
        old_fact=next(f for f in recent if f['id']==proposal['fact_id']); old=old_fact['atom']
        args=list(old.args)
        for slot,value in repair:
            args[slot]=value
        return apply_revision(old_fact,Atom(old.pred,tuple(args)),'anchored_multi_slot_revision_v516',
                              [slot for slot,_ in repair],proposal['surface'])

    def _contextual_query(self, text: str) -> dict | None:
        """Resolve a short WH question from the current discourse focus.

        The mechanism never assigns a meaning to ``qué/quién/dónde/...`` by
        itself.  It reuses an already-grounded query construction for the focused
        predicate and takes the construction's existing ``?answer`` position as
        the semantic target.  A cue must occur literally in that construction;
        competing answer positions remain ambiguous.
        """
        if not self._question_like(text):
            return None
        cleaned=normalize(re.sub(r'[,;:]+',' ',text)); cue=cleaned.split()
        if cue and cue[0]=='y':
            cue=cue[1:]
        wh={'que','quien','cual','donde','cuando','cuanto','como'}
        if not cue or len(cue)>4 or len([t for t in cue if t in wh])!=1:
            return None
        recent=self._recent_discourse_facts()
        if not recent:
            return None

        # Bare ellipsis is about the current focus, not any older fact that happens
        # to have a compatible grammar.  A later extension may use explicit
        # referents to select an older fact; this path deliberately does not guess.
        fact=recent[0]; atom=fact['atom']; candidates=[]
        for construction in self.language.constructions:
            frame=construction.frame
            if frame.get('act')!='query' or frame.get('pred')!=atom.pred:
                continue
            fargs=list(frame.get('args',[]))
            unknown=[i for i,v in enumerate(fargs)
                     if isinstance(v,str) and v.startswith('?')]
            if len(unknown)!=1 or len(fargs)!=len(atom.args):
                continue
            surface=construction.surface.split()
            fixed=[tok for tok in surface if not (tok.startswith('{') and tok.endswith('}'))]
            n=len(cue)
            if not any(fixed[i:i+n]==cue for i in range(len(fixed)-n+1)):
                continue
            args=list(atom.args); args[unknown[0]]='?answer'
            candidates.append({'atom':Atom(atom.pred,tuple(args)),'answer_pos':unknown[0],
                               'surface':construction.surface,
                               # The user supplied only the cue.  Extra words in
                               # one stored question construction are not evidence
                               # for preferring its semantic role over another.
                               'score':(len(cue),)})
        if not candidates:
            return None
        best_score=max(c['score'] for c in candidates)
        best=[]
        for c in candidates:
            if c['score']==best_score and c['atom'] not in [x['atom'] for x in best]:
                best.append(c)
        if len(best)!=1:
            return {'status':'contextual_query_ambiguous','reason':'multiple_answer_roles',
                    'candidates':[{'answer_pos':c['answer_pos'],'surface':c['surface']} for c in best]}
        chosen=best[0]; result=self.answer_atom(chosen['atom'])
        result.update({'contextual_ellipsis':True,'discourse_fact':fact['id'],
                       'answer_pos':chosen['answer_pos'],'cue':' '.join(cue),
                       'query_surface':chosen['surface'],
                       'mechanism':'grounded_query_ellipsis_v517'})
        return result

    @staticmethod
    def _split_document(text: str) -> list[str]:
        """Split ordinary multi-sentence input without interpreting its meaning.

        The splitter is deliberately small and deterministic.  It is only activated
        when punctuation actually separates two non-empty spans; a single utterance
        keeps the exact legacy path.
        """
        raw=str(text).strip()
        if not raw:
            return []
        # Terminators inside quotations belong to the quoted utterance (e.g. an
        # explicit paraphrase ``"¿…?" significa lo mismo que "¿…?"``), never to
        # the outer document.
        closing={'"':'"','«':'»','“':'”'}
        parts=[]; start=0; quote=None; i=0
        while i<len(raw):
            ch=raw[i]
            if quote is not None:
                if ch==quote:
                    quote=None
            elif ch in closing:
                quote=closing[ch]
            elif ch in '.!?':
                while i+1<len(raw) and raw[i+1] in '.!?':
                    i+=1
                span=raw[start:i+1].strip()
                if span.strip('.!?¿¡ '):
                    parts.append(span)
                start=i+1
            i+=1
        tail=raw[start:].strip()
        if tail.strip('.!?¿¡ '):
            parts.append(tail)
        return parts if len(parts)>1 else [raw]

    _DISCOURSE_ANAPHORS=frozenset({
        'este','esta','estos','estas','ese','esa','esos','esas',
        'aquel','aquella','aquellos','aquellas','esto','eso','aquello',
        'él','ella','ellos','ellas'
    })

    def _remember_discourse(self, text: str) -> None:
        """Remember concrete referents from an already understood construction.

        A referent stores both its semantic value and a short surface mention.  The
        mention is used only as a candidate substitution on a later anaphor; the
        learned grammar must still license the repaired utterance.
        """
        parsed=self.language.parse(text)
        if parsed.get('status')!='parsed':
            return
        frame=parsed.get('frame') or {}
        args=[v for v in frame.get('args',())
              if isinstance(v,str) and not v.startswith('?')]
        if not args:
            return
        tokens=normalize(text).split()
        additions=[]
        for value in args:
            needle=normalize(value).split()
            if not needle:
                continue
            hits=[]
            width=len(needle)
            for i in range(len(tokens)-width+1):
                if tokens[i:i+width]==needle:
                    hits.append(i)
            if len(hits)!=1:
                continue
            i=hits[0]
            # One lexical anchor immediately before the value is enough to restore
            # learned surfaces such as ``modulo <x>``.  If there is none, the value
            # itself remains a valid candidate.
            start=max(0,i-1)
            surface=' '.join(tokens[start:i+width])
            additions.append({'value':normalize(value),'surface':surface,
                              'source':normalize(text)})
        for row in additions:
            self.discourse_referents=[x for x in self.discourse_referents
                                      if not (x.get('value')==row['value'] and x.get('surface')==row['surface'])]
            self.discourse_referents.append(row)
        if len(self.discourse_referents)>self.discourse_max_referents:
            self.discourse_referents=self.discourse_referents[-self.discourse_max_referents:]

    def _resolve_discourse_surface(self, text: str) -> tuple[str, dict | None]:
        """Resolve a closed-class anaphor only when grammar makes it unique."""
        tokens=normalize(text).split()
        positions=[i for i,t in enumerate(tokens) if t in self._DISCOURSE_ANAPHORS]
        if len(positions)!=1 or not self.discourse_referents:
            return text,None
        pos=positions[0]
        # Recency is applied by *source episode*, not by individual entity.
        # Older compatible entities must not make a perfectly local reference
        # ambiguous.  Within the most recent episode that yields candidates we
        # still require a unique semantic parse.
        grouped=[]; seen_sources=set()
        for ref in reversed(self.discourse_referents):
            src=str(ref.get('source',''))
            if src in seen_sources:
                continue
            seen_sources.add(src); grouped.append(src)
        candidates=[]
        for src in grouped:
            seen=set(); local=[]
            for ref in reversed(self.discourse_referents):
                if str(ref.get('source','')) != src:
                    continue
                surface=str(ref.get('surface') or ref.get('value') or '').strip()
                if not surface:
                    continue
                cand_tokens=tokens[:pos]+surface.split()+tokens[pos+1:]
                candidate=' '.join(cand_tokens)
                parsed=self.language.parse(candidate)
                if parsed.get('status')!='parsed':
                    continue
                frame=parsed.get('frame') or {}
                # The referent may restore a noun anchor (``modulo <x>``) but must
                # not supply the construction itself: at least one fixed token of
                # the licensed construction has to come from the user's utterance.
                # Otherwise a content word that merely looks like a demonstrative
                # (``area este``) would import a predicate from an older sentence.
                arg_tokens=Counter(t for v in frame.get('args',()) if isinstance(v,str)
                                   for t in normalize(v).split())
                fixed=Counter(cand_tokens)-arg_tokens
                if not (fixed-Counter(surface.split())):
                    continue
                key=json.dumps(frame,sort_keys=True,ensure_ascii=False,separators=(',',':'))
                if key in seen:
                    continue
                seen.add(key); local.append((candidate,frame,ref))
            if local:
                candidates=local; break
        if len(candidates)!=1:
            if len(candidates)>1:
                self.training_reports.append({'type':'discourse_reference_ambiguous',
                                              'text':text,'candidates':len(candidates),
                                              'source':candidates[0][2].get('source')})
            return text,None
        candidate,frame,ref=candidates[0]
        trace={'original':text,'resolved':candidate,'referent':ref.get('value'),
               'surface':ref.get('surface'),'frame':frame}
        self.training_reports.append({'type':'discourse_reference_resolved',**trace})
        return candidate,trace

    def respond(self, text: str) -> dict:
        """Process one utterance or a short multi-sentence document."""
        parts=self._split_document(text)
        if not parts:
            return {'text':'No recibí contenido interpretable.','status':'unrecognized'}
        if len(parts)>1:
            rows=[]
            for part in parts:
                rows.append(self.respond(part))
            return {'text':f'Procesé {len(rows)} segmentos del documento en orden.',
                    'status':'document_processed','sentences':rows,
                    'successful':sum(r.get('status') not in ('unrecognized','ambiguous') for r in rows),
                    'total':len(rows)}
        original=parts[0]
        repaired,trace=self._resolve_discourse_surface(original)
        result=self._respond_single(repaired)
        # Only understood/promoted/stored utterances should influence salience.
        if result.get('status') not in ('unrecognized','ambiguous','grounding_pending',
                                        'concept_pending','schema_pending','raw_relation_pending'):
            self._remember_discourse(repaired)
        if trace is not None:
            result=dict(result); result['discourse_resolution']=trace
        return result

    def _respond_learned_goal_plan(self, text: str) -> dict | None:
        """Plan toward a goal only through a learned goal construction (V8.9).

        The goal must be resolved by a construction induced from examples, and
        every entity it mentions must have appeared in an observed state: an
        unseen place is not planned for, it is reported as unknown.
        """
        if self.last_symbolic_state is None or not self.symbolic.operators():
            return None
        resolved = self.symbolic.resolve_goal(text)
        if resolved.get('status') != 'symbolic_goal_resolved':
            return None
        known = self.symbolic_entities | {arg for fact in self.last_symbolic_state for arg in fact[1:]}
        unseen = sorted({arg for fact in resolved['goal'] for arg in fact[1:]} - known)
        if unseen:
            return {'text':'Reconozco la meta, pero no conozco en el estado actual: '+', '.join(unseen)+'. No inventaré un plan.',
                    'status':'symbolic_goal_unknown_entities','unseen':unseen,'goal_pattern':resolved.get('pattern')}
        plan = self.symbolic.plan(self.last_symbolic_state, resolved['goal'], max_steps=8)
        if plan.get('status') != 'plan_found':
            return {'text':'Reconozco la meta, pero no encontré un plan con las acciones aprendidas.',
                    'status':'symbolic_plan_not_found','goal_pattern':resolved.get('pattern')}
        steps = [str(step.get('action')) for step in plan.get('steps', ())]
        plan['resolved_goal'] = resolved['goal']; plan['goal_pattern'] = resolved.get('pattern')
        return {'text':'Plan simbólico aprendido: '+('; '.join(steps) if steps else 'la meta ya se cumple.'),
                'status':'symbolic_plan','plan':plan,'goal_source':'learned_schema'}

    def _respond_learned_procedure(self, text: str) -> dict | None:
        """Run an already promoted numeric procedure named in the utterance (V8.9).

        The numbers in the sentence are its input state, as when it was taught
        («suma uno a 3» with state (3,)).  Unknown surfaces fall through.
        """
        if not any(ch.isdigit() for ch in text):
            return None
        arities = sorted({int(s.get('input_arity', 1)) for s in self.procedures.sessions.values() if s.get('promoted')})
        if not arities:
            return None
        nums = [int(x) for x in re.findall(r'(?<!\w)-?\d+(?!\w)', text)]
        for arity in arities:
            if len(nums) < arity:
                continue
            report = self.procedures.execute(text, tuple(nums[:arity]))
            if report.get('status') == 'corrected_conflict':
                return {'text':'Hay una corrección explícita para este caso; no aplicaré la regla general.',
                        'status':'procedure_corrected_conflict',
                        'procedure':report.get('pattern'),
                        'observed_after':tuple(report['observed_after']),
                        'result':None,'detail':report}
            if report.get('status') in ('executed', 'executed_plan') and report.get('result') is not None:
                values = tuple(report['result'])
                shown = str(values[0]) if len(values) == 1 else ', '.join(map(str, values))
                return {'text':f'Resultado mediante procedimiento aprendido: {shown}',
                        'status':'procedure_executed','procedure':report.get('pattern'),'result':values,'detail':report}
        return None

    def _respond_single(self, text: str) -> dict:
        for learned_route in (self._respond_learned_goal_plan, self._respond_learned_procedure):
            routed = learned_route(text)
            if routed is not None:
                return routed
        procedure_pattern, _ = _surface(text)
        if procedure_pattern in self.procedures.sessions:
            return {'text':'Reconozco la construcción, pero no puedo ejecutar el procedimiento con la evidencia vigente.',
                    'status':'procedure_unresolved','procedure':procedure_pattern}
        conditional=self.observe_conditional_rule(text)
        if conditional is not None:
            messages={
                'conditional_rule_pending':'Registré el ejemplo condicional; aún necesito más ejemplos independientes antes de generalizar una regla.',
                'conditional_rule_learned':'Induje una regla relacional ejecutable a partir de ejemplos condicionales independientes y consistentes.',
                'conditional_rule_confirmed':'El nuevo ejemplo sigue siendo compatible con la regla condicional aprendida.',
                'conditional_rule_ambiguous':'Los ejemplos condicionales implican mapeos de roles incompatibles; no promoveré una regla.',
                'conditional_ambiguous':'El antecedente admite más de una segmentación conjuntiva grounded; no aprenderé una regla ambigua.',
                'conditional_unresolved':'No puedo interpretar de forma grounded una o ambas cláusulas del condicional.',
                'conditional_alignment_failed':'No puedo alinear de forma inequívoca los roles del consecuente con el antecedente.',
                'conditional_unsupported':'Ese condicional todavía queda fuera del mecanismo seguro de aprendizaje.',
                'conditional_malformed':'Reconozco un inicio condicional, pero no tiene una única estructura «si … entonces …».',
                'conditional_bootstrap_pending':'Registré el condicional hipotético; todavía necesito más ejemplos independientes antes de inducir significados de cláusula.',
                'conditional_bootstrap_learned':'Induje construcciones relacionales opacas desde condicionales hipotéticos repetidos y, sin afirmar sus ejemplos como hechos, las usé para aprender la regla.',
                'conditional_bootstrap_ambiguous':'Los condicionales hipotéticos admiten más de una familia de plantillas; no promoveré ninguna.',
            }
            return {'text':messages.get(conditional['status'],'No pude aprender ese condicional.'),**conditional}
        event_feedback=self._event_reference_feedback_instruction(text)
        if event_feedback is not None:
            feedback=self.teach_event_reference_feedback(*event_feedback)
            messages={
                'event_reference_corrected':'Corregí la referencia explícita, retiré la representación eventiva que quedó sin apoyo y registré la contraevidencia.',
                'event_reference_feedback_unresolved':'No puedo aplicar esa corrección a una referencia eventiva reciente de forma inequívoca.',
            }
            return {'text':messages.get(feedback['status'],'No pude aplicar esa corrección de referencia.'),**feedback}
        equivalence=self._paraphrase_instruction(text)
        if equivalence is not None:
            taught=self.teach_explicit_paraphrase(*equivalence)
            messages={
                'paraphrase_learned':'Aprendí la equivalencia explícita y puedo reutilizar la nueva formulación con los mismos roles.',
                'paraphrase_confirmed':'Ambas formulaciones ya representan el mismo significado registrado.',
                'paraphrase_unresolved':'No puedo aprender esa equivalencia todavía porque ninguna de las dos formulaciones tiene un significado grounded.',
                'paraphrase_conflict':'Las formulaciones chocan con significados ya registrados; no modificaré la gramática.',
                'paraphrase_alignment_failed':'La equivalencia fue explícita, pero no pude alinear de forma única sus argumentos.',
                'paraphrase_unsupported':'Ese tipo de acto comunicativo aún no admite equivalencias explícitas.',
            }
            return {'text':messages.get(taught['status'],'No pude registrar esa equivalencia.'),**taught}
        parsed = self._semantic_parse(text)
        if parsed.get('status')=='unrecognized' and self._question_like(text):
            contextual_query=self._contextual_query(text)
            if contextual_query is not None:
                if contextual_query.get('status')=='contextual_query_ambiguous':
                    return {'text':'La pregunta elíptica coincide con más de un rol interrogable del contexto; necesito una formulación más específica.',
                            **contextual_query}
                if contextual_query.get('status')=='contextual_query_unresolved':
                    return {'text':'No hay un referente discursivo suficiente para resolver esa pregunta elíptica.',
                            **contextual_query}
                return contextual_query
        if parsed.get('status')=='unrecognized':
            correction=self._contextual_correction(text)
            if correction is not None:
                messages={
                    'corrected_contextually':'Corrección contextual aplicada sin enseñar una frase específica.',
                    'correction_ambiguous':'La corrección podría modificar más de un rol; no cambiaré el conocimiento.',
                    'correction_unresolved':'Reconozco una posible corrección, pero el contexto no identifica un único rol que cambiar.',
                }
                return {'text':messages.get(correction['status'],'No pude aplicar la corrección.'),**correction}
        if parsed.get('status')=='unrecognized' and parsed.get('reason')=='negation_ambiguous':
            return {'text':'La polaridad de esa frase es ambigua; no registraré conocimiento a partir de ella.',
                    'status':'unrecognized','reason':'negation_ambiguous'}
        # Once a relational surface has been grounded, it can introduce referents
        # that were never in the entity index.  Only assertions with at least one
        # genuinely novel semantic argument take this path; ordinary known-entity
        # examples keep the earlier confirmation/learning behavior.
        if not self._question_like(text):
            acquired=self.acquire_schema_assertion(text,require_novel=True)
            if acquired.get('status')=='schema_fact_stored':
                return {'text':'Dato relacional registrado mediante un esquema aprendido, con procedencia y nuevos referentes explícitos.',
                        **acquired}
            if acquired.get('status')=='schema_surface_ambiguous':
                return {'text':'Reconozco un esquema aprendido, pero los límites de sus referentes son ambiguos; no registraré el dato.',
                        **acquired}

        def resolve_invented() -> dict | None:
            concept = self.query_concept(text)
            if concept.get('status') in ('entailed','contradicted','contested','unknown'):
                messages = {
                    'entailed': 'Sí: puedo deducir esa relación del conocimiento aprendido.',
                    'contradicted': 'Tengo evidencia explícita para la relación contraria.',
                    'contested': 'La evidencia disponible es contradictoria.',
                    'unknown': 'No puedo deducir esa relación con el conocimiento actual.',
                }
                return {'text': messages[concept['status']], **concept}
            schema = self.query_schema(text)
            if schema.get('status') in ('entailed','contradicted','contested','unknown'):
                messages = {
                    'entailed': 'Sí: puedo deducir esa relación del esquema relacional aprendido.',
                    'contradicted': 'Tengo evidencia explícita para la relación contraria.',
                    'contested': 'La evidencia disponible es contradictoria.',
                    'unknown': 'No puedo deducir esa relación con el conocimiento actual.',
                }
                return {'text': messages[schema['status']], **schema}
            return None

        def observe_invented(allow_pending: bool) -> dict | None:
            concept = self.observe_concept_statement(text)
            concept_statuses = {'concept_learned','concept_unresolved','concept_contradictory',
                                'concept_alias_learned','concept_alias_confirmed','concept_alias_withdrawn'}
            if allow_pending:
                concept_statuses.add('concept_pending')
            if concept.get('status') in concept_statuses:
                messages = {
                    'concept_pending': 'Registré el ejemplo como una posible relación nueva, pero aún falta evidencia contrastiva.',
                    'concept_learned': 'Aprendí una hipótesis relacional nueva a partir de los ejemplos y del contexto factual.',
                    'concept_unresolved': 'Registré el concepto, pero todavía no encontré una definición relacional que explique los ejemplos.',
                    'concept_contradictory': 'Los ejemplos de esa relación son contradictorios.',
                    'concept_alias_learned': 'La nueva formulación es compatible de forma única con una relación ya aprendida y quedó vinculada como hipótesis reutilizable.',
                    'concept_alias_confirmed': 'La nueva evidencia sigue siendo compatible con la relación aprendida.',
                    'concept_alias_withdrawn': 'La nueva evidencia contradijo la equivalencia lingüística anterior; retiré ese alias sin borrar la relación original.',
                }
                return {'text': messages[concept['status']], **concept}
            schema = self.observe_schema_statement(text)
            schema_statuses = {'schema_learned','schema_unresolved','schema_contradictory',
                               'schema_alias_learned','schema_confirmed'}
            if allow_pending:
                schema_statuses.add('schema_pending')
            if schema.get('status') in schema_statuses:
                messages = {
                    'schema_pending': 'Registré el ejemplo y sigo comparando qué roles son realmente necesarios.',
                    'schema_learned': 'Aprendí un esquema relacional y deduje su aridad y proyección de roles a partir de evidencia contrastiva.',
                    'schema_unresolved': 'Registré el esquema, pero la evidencia todavía no distingue una estructura relacional válida.',
                    'schema_contradictory': 'Los ejemplos de ese esquema son contradictorios.',
                    'schema_alias_learned': 'Vinculé la nueva formulación con un esquema previo e inferí cómo reordena sus roles.',
                    'schema_confirmed': 'La nueva evidencia sigue siendo compatible con el esquema aprendido.',
                }
                return {'text': messages[schema['status']], **schema}
            return None

        # Learned concept surfaces are more specific than generic grounded-language
        # hypotheses and should get first chance on yes/no questions.
        if parsed['status'] == 'unrecognized' and self._question_like(text):
            resolved = resolve_invented()
            if resolved is not None:
                return resolved

        if self.grounded_language and self.allow_extensional_grounding and parsed['status'] == 'parsed':
            # A broad slot can sometimes absorb words that should have been fixed
            # structure.  When the utterance mentions already-known entities that
            # disappear from the parsed concrete arguments, let grounded evidence
            # challenge the existing construction instead of silently trusting it.
            frame=parsed.get('frame') or {}
            if frame.get('act') in ('assert','query'):
                mentioned=self._entities_mentioned(text)
                concrete={normalize(str(v)) for v in frame.get('args',[])
                          if not (isinstance(v,str) and v.startswith('?'))}
                if mentioned and not mentioned.issubset(concrete):
                    grounded=self._try_grounded_language(text)
                    if grounded is not None:
                        parsed=grounded
        if (parsed['status'] == 'unrecognized' and self.grounded_language and
                (self.allow_extensional_grounding or self._question_like(text))):
            grounded = self._try_grounded_language(
                text, require_surface_anchor=not self.allow_extensional_grounding)
            if grounded is not None:
                parsed = grounded
        # G-27: without extensional grounding an unknown assertion may only open
        # rival meanings (at least two); an answered probe is the sole promoter.
        if (parsed['status'] == 'unrecognized' and self.grounded_language and
                not self.allow_extensional_grounding and not self._question_like(text)):
            collected = self._try_grounded_language(text, collect_only=True)
            if collected is not None:
                parsed = collected

        # Pending generic grounding may coexist with a more specific concept.
        # Only a promoted/revised concept overrides it; pending evidence does not.
        if parsed['status'] == 'grounding_pending' and not self._question_like(text):
            learned = observe_invented(False)
            if learned is not None:
                return learned

        if parsed['status'] != 'parsed' and parsed['status'] != 'grounding_pending':
            if self._question_like(text):
                resolved = resolve_invented()
                if resolved is not None:
                    return resolved
            else:
                learned = observe_invented(True)
                # A contrastively learned/confirmed semantic structure outranks an
                # opaque primitive. Pending or unresolved hypotheses, however, do
                # not block raw evidence collection: otherwise known entities would
                # prevent V4.5 from ever learning a distinct new relation.
                decisive = {
                    'concept_learned','concept_contradictory','concept_alias_learned',
                    'concept_alias_confirmed','concept_alias_withdrawn',
                    'schema_learned','schema_contradictory','schema_alias_learned',
                    'schema_confirmed',
                }
                if learned is not None and learned.get('status') in decisive:
                    return learned
                if parsed.get('status') == 'unrecognized':
                    negative_raw = self.observe_raw_negative_relation(text)
                    if negative_raw.get('status') == 'raw_negative_relation_learned':
                        return {'text':'Induje una relación primitiva opaca desde varias afirmaciones negativas; registré solo evidencia negativa y aprendí la superficie afirmativa correspondiente.', **negative_raw}
                    if negative_raw.get('status') == 'raw_negative_relation_ambiguous':
                        return {'text':'Las afirmaciones negativas admiten más de una plantilla relacional; no promoveré ninguna.', **negative_raw}
                    if negative_raw.get('status') == 'raw_negative_relation_pending' and learned is None:
                        return {'text':f'Registré la negación como evidencia separada; todavía no hay {self.raw_relation_min_support} apoyos independientes para inducir la relación base.', **negative_raw}
                    raw = self.observe_raw_relation(text)
                    if raw.get('status') == 'raw_relation_learned':
                        return {'text':'Induje una relación primitiva opaca a partir de varias afirmaciones no anotadas y registré sus hechos con procedencia.', **raw}
                    if raw.get('status') == 'raw_relation_ambiguous':
                        return {'text':'Veo más de una plantilla relacional compatible; no promoveré ninguna sin más evidencia.', **raw}
                    if raw.get('status') == 'raw_relation_pending' and learned is None:
                        return {'text':f'Registré la afirmación como evidencia lingüística cruda; todavía no hay {self.raw_relation_min_support} apoyos independientes para inducir una relación.', **raw}
                if learned is not None:
                    return learned

        if parsed['status'] != 'parsed':
            if parsed['status'] == 'grounding_pending':
                g=parsed.get('grounded_induction',{})
                return {'text': f'Tengo una hipótesis de significado respaldada por {g.get("support",0)} experiencia(s), pero todavía no la usaré como conocimiento lingüístico hasta reunir {g.get("required",self.grounding_min_support)} apoyos independientes.',
                        'status':'grounding_pending','grounded_induction':g}
            message = ('Esa frase admite varias interpretaciones aprendidas. Necesito una formulación más precisa.'
                       if parsed['status'] == 'ambiguous' else
                       'No sé interpretar esa formulación todavía. Puedes enseñarme una construcción con texto y significado, o usar /consulta.')
            return {'text': message, 'status': parsed['status']}
        frame = parsed['frame']
        action = frame['act']
        if action == 'query':
            return self.answer_atom(Atom(frame['pred'], tuple(frame['args'])))
        if action == 'assert':
            cluster,uncertain=self._grounding_parse_source(parsed)
            if uncertain:
                return {'text':'No puedo atribuir esta afirmación a una interpretación fiable.',
                        'status':'grounding_pending'}
            atom=Atom(frame['pred'],tuple(frame['args']))
            was_new=not any(fact['source']=='conversación'
                            for fact in self.kb.matches(atom))
            fid=self.kb.add(atom,'conversación')
            if cluster is not None and was_new:
                self.grounding_fact_dependencies[fid]=cluster
                self.grounding_hypotheses[cluster].setdefault('derived_fact_ids',[]).append(fid)
            elif cluster is None and fid in self.grounding_fact_dependencies:
                old_cluster=self.grounding_fact_dependencies.pop(fid)
                state=self.grounding_hypotheses.get(old_cluster, {})
                state['derived_fact_ids']=[old for old in state.get('derived_fact_ids',())
                                           if old!=fid]
            self._remember_discourse_fact(fid)
            self.last_result = None
            return {'text': 'Dato registrado con su procedencia.', 'status': 'stored', 'id': self.last_fact}
        if action == 'correct_last':
            if not self.last_fact:
                return {'text': 'No hay un dato anterior inequívoco que pueda corregir.', 'status': 'unknown'}
            old_fact = self.kb.get_fact(self.last_fact) if hasattr(self.kb, 'get_fact') else None
            if old_fact is None:
                return {'text': 'El dato anterior ya no existe.', 'status': 'unknown'}
            old = old_fact['atom']
            args, slot = list(old.args), frame['slot']
            if type(slot) is not int or not 0 <= slot < len(args):
                return {'text': 'La corrección no corresponde al dato anterior.', 'status': 'unrecognized'}
            args[slot] = str(frame['value'])
            old_id=self.last_fact
            new_id=self.kb.replace(old_id, Atom(old.pred, tuple(args)))
            self._replace_discourse_fact(old_id,new_id)
            self.last_result = None
            return {'text': 'Corrección aplicada: ' + self.language.describe(old.pred, tuple(args)) + '.', 'status': 'corrected'}
        if action == 'calculate':
            answer = self.programs.predict(frame['skill'], tuple(frame['values']))
            if answer['status'] == 'hypothesis':
                message = f'Resultado según el procedimiento aprendido: {answer["value"]}. Regla: {answer["programs"][0]}.'
            elif answer['status'] == 'ambiguous':
                message = f'Los procedimientos compatibles discrepan: {answer["alternatives"]}. Necesito otro ejemplo para distinguirlos.'
            elif answer['status'] == 'contradictory_examples':
                message = 'Los ejemplos enseñan resultados contradictorios para la misma entrada.'
            else:
                message = 'No tengo un procedimiento válido para resolver eso dentro del presupuesto actual.'
            return {'text': message, **answer}
        if action == 'explain':
            return self.explain()
        return {'text': 'El acto comunicativo anotado no está implementado.', 'status': 'unrecognized'}
