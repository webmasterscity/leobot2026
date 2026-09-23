"""Document reading, reference decisions, and bounded revision.

These methods operate on the cognitive state owned by Bot. Keeping document
acquisition here lets later changes be reviewed without navigating the dialogue,
numeric, and symbolic learners in bot.py.
"""
from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations

from .core import Atom
from .language import Language, normalize


class DocumentLearningMixin:
    @staticmethod
    def _document_sentences(text: str, max_sentences: int = 5000) -> list[str]:
        """Bounded, non-neural sentence segmentation for document acquisition.

        This is intentionally a transport layer, not a claim of general document
        understanding.  Newlines are hard boundaries; ``.?!`` followed by
        whitespace is a soft boundary.  Empty/oversized fragments are handled by
        the caller rather than executed or silently concatenated.
        """
        if not isinstance(text,str):
            raise TypeError('El documento debe ser texto.')
        if len(text)>20_000_000:
            raise ValueError('El documento excede el límite de 20 MB de texto.')
        chunks=[]
        for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
            line=line.strip()
            if not line:
                continue
            chunks.extend(x.strip() for x in re.split(r'(?<=[.!?])\s+',line) if x.strip())
            if len(chunks)>max_sentences:
                raise ValueError('El documento excede el presupuesto de oraciones.')
        return chunks

    _DOCUMENT_REFERENCE_MARKERS = frozenset({'eso','esto','aquello','ella','ellos','ellas'})

    @staticmethod
    def _document_discourse_prefix(text: str) -> tuple[str | None, str]:
        """Extract a small explicit discourse operator without guessing semantics.

        ``luego/después`` contributes only an ordering edge and ``por eso`` only a
        causal edge between adjacent document facts.  The remaining clause still
        has to be independently parsed/learned; the connective never licenses its
        factual content.
        """
        raw=text.strip()
        patterns=(
            ('after',r'^(?:luego|después|despues)\s*,?\s+(.+)$'),
            ('caused_by_previous',r'^por\s+eso\s*,?\s+(.+)$'),
        )
        for relation,pattern in patterns:
            m=re.match(pattern,raw,flags=re.IGNORECASE|re.DOTALL)
            if m and m.group(1).strip():
                return relation,m.group(1).strip()
        return None,text


    @classmethod
    def _document_reference_positions(cls, args) -> list[int]:
        """Return argument positions occupied by conservative anaphoric markers.

        These are closed-class Spanish discourse forms, not domain vocabulary.
        Articles/clitics such as ``el/la/lo`` are deliberately excluded because a
        broad learned slot can swallow them as ordinary text too easily.
        """
        out=[]
        for i,value in enumerate(args or []):
            if isinstance(value,str) and normalize(value) in cls._DOCUMENT_REFERENCE_MARKERS:
                out.append(i)
        return out

    @classmethod
    def _document_has_reference_marker(cls, text: str) -> bool:
        tokens=set(normalize(text).split())
        return bool(tokens & cls._DOCUMENT_REFERENCE_MARKERS)

    @staticmethod
    def _document_role_key(a_pred: str, a_slot: int, b_pred: str, b_slot: int) -> tuple[str, tuple[str,int], tuple[str,int]]:
        left=(a_pred.lstrip('!'),int(a_slot)); right=(b_pred.lstrip('!'),int(b_slot))
        if right < left: left,right=right,left
        return json.dumps([list(left),list(right)],separators=(',',':')),left,right

    def _observe_document_role_bridges(self, fact: dict, prior_facts: list[dict], episode_id: str, document_source: str) -> None:
        """Accumulate non-circular evidence that two predicate roles can share a referent.

        A support episode must explicitly repeat exactly one concrete entity across
        two facts in the same document.  Promotion requires three independent
        document episodes and three distinct shared entities.  Facts produced by
        coreference resolution are excluded from support.
        """
        if not fact or 'document_coreference_' in str(fact.get('source','')):
            return
        atom=fact.get('atom')
        if atom is None: return
        for prior in prior_facts:
            if not prior or 'document_coreference_' in str(prior.get('source','')):
                continue
            other=prior.get('atom')
            if other is None: continue
            shared=(set(atom.args) & set(other.args)) - self._DOCUMENT_REFERENCE_MARKERS
            if len(shared)!=1:
                continue
            entity=next(iter(shared))
            apos=[i for i,v in enumerate(atom.args) if v==entity]
            bpos=[i for i,v in enumerate(other.args) if v==entity]
            if len(apos)!=1 or len(bpos)!=1:
                continue
            key,left,right=self._document_role_key(atom.pred,apos[0],other.pred,bpos[0])
            if left==right:
                continue
            state=self.document_role_bridge_hypotheses.setdefault(key,{
                'roles':[list(left),list(right)],'observations':[],'promoted':False})
            obs={'episode_id':episode_id,'document_source':str(document_source),'entity':entity,
                 'fact_ids':sorted([fact.get('id'),prior.get('id')])}
            if not any(o.get('episode_id')==episode_id for o in state['observations']):
                state['observations'].append(obs)
                state['observations']=state['observations'][-64:]
            episodes={o.get('episode_id') for o in state['observations']}
            entities={o.get('entity') for o in state['observations']}
            was_promoted=bool(state.get('promoted'))
            if len(episodes)>=3 and len(entities)>=3:
                state['promoted']=True
                state['support']=min(len(episodes),len(entities))
                if not was_promoted:
                    event={'event':'document_role_bridge_promoted','roles':state['roles'],
                           'support':state['support'],'episode_ids':sorted(episodes),
                           'entities':sorted(entities),'mechanism':'explicit_shared_referent_v522'}
                    if hasattr(self.kb,'audit') and event not in self.kb.audit:
                        self.kb.audit.append(event)
                    self.training_reports.append({'type':'document_role_bridge_promoted',**event})

    def _document_bridge_candidates(self, pred: str, slot: int, document_facts: list[dict]) -> dict[str,list[dict]]:
        role=(pred.lstrip('!'),int(slot)); out={}
        for state in self.document_role_bridge_hypotheses.values():
            if not state.get('promoted'):
                continue
            roles=[tuple(x) for x in state.get('roles',[])]
            if len(roles)!=2 or role not in roles:
                continue
            other=roles[1] if roles[0]==role else roles[0]
            for row in document_facts:
                atom=row.get('atom')
                if atom is None or atom.pred.lstrip('!')!=other[0] or other[1]>=len(atom.args):
                    continue
                value=atom.args[other[1]]
                if normalize(value) in self._DOCUMENT_REFERENCE_MARKERS:
                    continue
                out.setdefault(value,[]).append({'fact_id':row.get('id'),'role':list(other),
                                                  'bridge_roles':[list(x) for x in roles],
                                                  'bridge_support':state.get('support',0)})
        return out

    @staticmethod
    def _document_sentence_index(fact: dict) -> int | None:
        """Extract the source sentence index for one document fact."""
        m=re.search(r':oración:(\d+)',str((fact or {}).get('source','')))
        return int(m.group(1)) if m else None

    @classmethod
    def _document_event_cluster_signature(cls, facts: list[dict]) -> dict | None:
        """Canonicalize a connected 2--4 sentence fact cluster.

        Concrete entities are replaced by first-occurrence roles.  Each new fact
        must share at least one already introduced role with the previous cluster,
        so adjacency alone is never sufficient evidence for one event.  The
        bounded 2--4 window is an experimental search budget, not an ontological
        claim about how many statements an event may contain.
        """
        if not 2 <= len(facts) <= 4:
            return None
        atoms=[]; indices=[]
        for fact in facts:
            if not fact or 'document_coreference_' in str(fact.get('source','')):
                return None
            atom=fact.get('atom')
            if atom is None or atom.pred.startswith('_'):
                return None
            idx=cls._document_sentence_index(fact)
            if idx is None:
                return None
            atoms.append(atom); indices.append(idx)
        if any(b != a+1 for a,b in zip(indices,indices[1:])):
            return None
        role_for={}; bindings=[]; encoded=[]; seen_roles=set()
        for position,atom in enumerate(atoms):
            roles=[]
            for value in atom.args:
                if normalize(str(value)) in cls._DOCUMENT_REFERENCE_MARKERS:
                    return None
                if value not in role_for:
                    role_for[value]=len(bindings);bindings.append(value)
                roles.append(role_for[value])
            if position and not (seen_roles & set(roles)):
                return None
            seen_roles.update(roles)
            encoded.append({'pred':atom.pred,'roles':roles})
        structure={'facts':encoded,'role_count':len(bindings)}
        signature=json.dumps(structure,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        schema_id='event_schema_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return {'signature':signature,'schema_id':schema_id,'structure':structure,
                'bindings':list(bindings),'member_fact_ids':[f.get('id') for f in facts],
                'sentence_span':[indices[0],indices[-1]]}

    @classmethod
    def _document_event_pair_signature(cls, first: dict, second: dict) -> dict | None:
        """Compatibility wrapper for the V5.25 two-fact event schema."""
        return cls._document_event_cluster_signature([first,second])

    @classmethod
    def _document_state_pair_signature(cls, first: dict, second: dict) -> dict | None:
        """Canonicalize a non-contiguous pair as a persistent-state hypothesis.

        Unlike event schemas, state evidence must cross at least one sentence and
        preserve exactly one shared carrier entity.  Predicate identity is kept
        at this first stage; the novelty being tested is the representation and
        persistence rule, not unrestricted cross-vocabulary transfer.
        """
        if not first or not second:
            return None
        if 'document_coreference_' in str(first.get('source','')) or 'document_coreference_' in str(second.get('source','')):
            return None
        a=first.get('atom'); b=second.get('atom')
        if a is None or b is None or a.pred.startswith('_') or b.pred.startswith('_'):
            return None
        ia=cls._document_sentence_index(first); ib=cls._document_sentence_index(second)
        if ia is None or ib is None or ib-ia < 2 or ib-ia > 8:
            return None
        shared=[]
        for i,x in enumerate(a.args):
            if normalize(str(x)) in cls._DOCUMENT_REFERENCE_MARKERS:
                return None
            for j,y in enumerate(b.args):
                if x==y:
                    shared.append((x,i,j))
        # Multiple shared values make the persistent carrier underdetermined.
        values={x[0] for x in shared}
        if len(values)!=1:
            return None
        carrier=next(iter(values))
        positions=[(i,j) for value,i,j in shared if value==carrier]
        if len(positions)!=1:
            return None
        ai,bj=positions[0]
        # Persistence is evidence about the *same role* surviving across an
        # interval.  A value that merely flows from object -> subject is ordinary
        # event chaining and must not be relabelled as a state (V5.35 adversarial
        # regression found exactly this false positive in V5.32/V5.34 training).
        if ai != bj:
            return None
        role_for={carrier:0};bindings=[carrier]
        encoded=[]
        for atom in (a,b):
            roles=[]
            for value in atom.args:
                if normalize(str(value)) in cls._DOCUMENT_REFERENCE_MARKERS:
                    return None
                if value not in role_for:
                    role_for[value]=len(bindings);bindings.append(value)
                roles.append(role_for[value])
            encoded.append({'pred':atom.pred,'roles':roles})
        structure={'facts':encoded,'carrier_role':0,'carrier_positions':[ai,bj],
                   'role_count':len(bindings),'non_contiguous':True}
        signature=json.dumps(structure,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        schema_id='state_schema_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return {'signature':signature,'schema_id':schema_id,'structure':structure,
                'bindings':bindings,'carrier':carrier,'member_fact_ids':[first.get('id'),second.get('id')],
                'sentence_span':[ia,ib]}

    def _observe_document_state_schema(self, fact: dict, prior_facts: list[dict],
                                       episode_id: str, document_source: str) -> None:
        """Learn recurring persistent-state structure without asserting a state.

        Promotion needs three content-distinct documents and variation in every
        abstract role.  At least one explicit intervening fact must *not* mention
        the carrier, which distinguishes this hypothesis from a contiguous event.
        """
        if not fact or 'document_coreference_' in str(fact.get('source','')):
            return
        current_index=self._document_sentence_index(fact)
        if current_index is None:
            return
        for first in prior_facts:
            candidate=self._document_state_pair_signature(first,fact)
            if candidate is None:
                continue
            lo,hi=candidate['sentence_span'];carrier=candidate['carrier']
            intervening=[]
            for row in prior_facts:
                idx=self._document_sentence_index(row)
                atom=row.get('atom')
                if idx is None or atom is None or not lo < idx < hi:
                    continue
                intervening.append(row)
            if not intervening or not any(carrier not in row['atom'].args for row in intervening if row.get('atom') is not None):
                continue
            key=candidate['signature']
            state=self.document_state_schema_hypotheses.setdefault(key,{
                'schema_id':candidate['schema_id'],'signature':key,'structure':candidate['structure'],
                'observations':[],'promoted':False})
            if any(o.get('episode_id')==episode_id for o in state['observations']):
                continue
            state['observations'].append({'episode_id':episode_id,'document_source':str(document_source),
                                          'bindings':candidate['bindings'],'carrier':carrier,
                                          'member_fact_ids':candidate['member_fact_ids'],
                                          'sentence_span':candidate['sentence_span']})
            state['observations']=state['observations'][-64:]
            episodes={o.get('episode_id') for o in state['observations']}
            role_count=int((state.get('structure') or {}).get('role_count') or 0)
            role_values=[]
            for i in range(role_count):
                role_values.append({tuple(o.get('bindings') or [])[i]
                                    for o in state['observations'] if len(o.get('bindings') or [])>i})
            was=bool(state.get('promoted'))
            if len(episodes)>=3 and role_count>=1 and all(len(values)>=3 for values in role_values):
                state['promoted']=True;state['support']=len(episodes)
                if not was:
                    event={'event':'document_state_schema_promoted','schema_id':state['schema_id'],
                           'structure':state['structure'],'support':state['support'],
                           'episode_ids':sorted(episodes),'mechanism':'noncontiguous_persistent_state_induction_v535'}
                    if hasattr(self.kb,'audit') and event not in self.kb.audit:
                        self.kb.audit.append(event)
                    self.training_reports.append({'type':'document_state_schema_promoted',**event})

    @staticmethod
    def _document_state_topology(structure: dict) -> dict:
        """Erase lexical predicate identity from one persistent-state schema.

        The abstraction preserves arity, polarity, equality/role geometry, the
        carrier role and its argument positions, and the fact that evidence is
        non-contiguous.  This is intentionally narrower than arbitrary ontology
        invention: V5.37 tests transfer of the *persistence topology* only.
        """
        facts=[];predicate_roles={}
        for row in (structure or {}).get('facts',[]):
            pred=str(row.get('pred',''))
            base=pred.lstrip('!')
            if base not in predicate_roles:
                predicate_roles[base]=len(predicate_roles)
            roles=list(row.get('roles') or [])
            facts.append({'predicate_role':predicate_roles[base],'arity':len(roles),
                          'negative':pred.startswith('!'),'roles':roles})
        return {'facts':facts,
                'carrier_role':int((structure or {}).get('carrier_role',0)),
                'carrier_positions':list((structure or {}).get('carrier_positions') or []),
                'role_count':int((structure or {}).get('role_count') or 0),
                'predicate_count':len(predicate_roles),
                'non_contiguous':bool((structure or {}).get('non_contiguous'))}

    @classmethod
    def _document_state_topology_key(cls, structure: dict) -> tuple[str,str]:
        topology=cls._document_state_topology(structure)
        signature=json.dumps(topology,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        meta_id='state_meta_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return signature,meta_id

    @classmethod
    def _document_state_meta_gate_key(cls, structure: dict, predicate: str, slot: int) -> tuple[str,str]:
        topology_key,_=cls._document_state_topology_key(structure)
        payload={'topology_key':topology_key,'predicate':str(predicate).lstrip('!'),'slot':int(slot)}
        signature=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        gate_id='state_meta_gate_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return signature,gate_id

    def _refresh_document_state_meta(self, structure: dict, predicate: str, slot: int) -> None:
        """Promote persistence topology and consumer gate from independent uses.

        Exact source schemas must be promoted, predicate-disjoint and have at
        least one *exact* downstream use.  Meta uses never enter the exact gate
        store, so transferred successes cannot recursively manufacture support.
        """
        topology_key,meta_id=self._document_state_topology_key(structure)
        compatible=[];consumer=[]
        for exact in self.document_state_schema_hypotheses.values():
            if not exact.get('promoted') or exact.get('contested'):
                continue
            if self._document_state_topology_key(exact.get('structure') or {})[0]!=topology_key:
                continue
            preds=tuple(str(row.get('pred','')).lstrip('!') for row in (exact.get('structure') or {}).get('facts',[]))
            # A source family counts only if at least one exact state was actually
            # used somewhere.  This keeps structural recurrence alone insufficient.
            exact_uses=[]
            matching=[]
            for gate in self.document_state_reference_hypotheses.values():
                if gate.get('schema_id')!=exact.get('schema_id') or not gate.get('uses'):
                    continue
                exact_uses.extend(gate.get('uses') or [])
                if gate.get('predicate')==str(predicate).lstrip('!') and int(gate.get('slot',-1))==int(slot):
                    matching.extend(gate.get('uses') or [])
            if exact_uses:
                compatible.append({'schema_id':exact.get('schema_id'),'predicates':list(preds),
                                   'uses':len(set(exact_uses))})
            if matching:
                consumer.append({'schema_id':exact.get('schema_id'),'predicates':list(preds),
                                 'uses':len(set(matching))})

        def independent(items):
            out=[]
            for item in items:
                pset=set(item.get('predicates') or [])
                if not out or all(pset.isdisjoint(set(other.get('predicates') or [])) for other in out):
                    out.append(item)
            return out

        indep=independent(compatible)
        meta=self.document_state_meta_hypotheses.setdefault(topology_key,{
            'meta_schema_id':meta_id,'topology':self._document_state_topology(structure),
            'source_schemas':[],'support':0,'promoted':False})
        meta['source_schemas']=compatible[-32:]
        was=bool(meta.get('promoted'));meta['support']=len(indep);meta['promoted']=len(indep)>=2
        if meta['promoted'] and not was:
            event={'event':'document_state_meta_promoted','meta_schema_id':meta_id,
                   'topology':meta['topology'],'support':meta['support'],
                   'source_schema_ids':[x['schema_id'] for x in indep],
                   'source_predicate_families':[x['predicates'] for x in indep],
                   'mechanism':'predicate_disjoint_persistent_state_topology_v537'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:self.kb.audit.append(event)
            self.training_reports.append({'type':'document_state_meta_promoted',**event})

        cindep=independent(consumer)
        key,gate_id=self._document_state_meta_gate_key(structure,predicate,slot)
        gate=self.document_state_meta_reference_hypotheses.setdefault(key,{
            'gate_id':gate_id,'topology_key':topology_key,'predicate':str(predicate).lstrip('!'),
            'slot':int(slot),'source_schemas':[],'support':0,'promoted':False})
        gate['source_schemas']=consumer[-32:]
        gwas=bool(gate.get('promoted'));gate['support']=len(cindep);gate['promoted']=len(cindep)>=2
        if gate['promoted'] and not gwas:
            event={'event':'document_state_meta_reference_gate_promoted','gate_id':gate_id,
                   'topology_key':topology_key,'predicate':gate['predicate'],'slot':gate['slot'],
                   'support':gate['support'],'source_schema_ids':[x['schema_id'] for x in cindep],
                   'mechanism':'predicate_disjoint_persistent_state_consumer_gate_v537'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:self.kb.audit.append(event)
            self.training_reports.append({'type':'document_state_meta_reference_gate_promoted',**event})

    def _document_state_candidates(self, document_facts: list[dict]) -> list[dict]:
        """Return exact and meta-transferred persistent-state candidates."""
        promoted={k:s for k,s in self.document_state_schema_hypotheses.items()
                  if s.get('promoted') and not s.get('contested')}
        meta_promoted={k:s for k,s in self.document_state_meta_hypotheses.items()
                       if s.get('promoted')}
        if (not promoted and not meta_promoted) or len(document_facts)<2:
            return []
        rows=sorted((r for r in document_facts if self._document_sentence_index(r) is not None),
                    key=lambda r:self._document_sentence_index(r))
        out=[];seen=set()
        for i,first in enumerate(rows):
            for second in rows[i+1:]:
                candidate=self._document_state_pair_signature(first,second)
                if candidate is None:
                    continue
                lo,hi=candidate['sentence_span'];carrier=candidate['carrier']
                intervening=[r for r in rows if lo < self._document_sentence_index(r) < hi]
                if not intervening or not any(carrier not in r['atom'].args for r in intervening if r.get('atom') is not None):
                    continue
                exact=promoted.get(candidate['signature'])
                topology_key,_=self._document_state_topology_key(candidate['structure'])
                meta=meta_promoted.get(topology_key)
                # Exact evidence dominates a meta-transfer over the same members.
                state=exact or meta
                if state is None:
                    continue
                is_meta=exact is None
                schema_id=(state.get('meta_schema_id') if is_meta else state.get('schema_id'))
                member_ids=tuple(candidate['member_fact_ids']);key=(schema_id,member_ids)
                if key in seen:continue
                seen.add(key)
                digest=hashlib.blake2b((str(schema_id)+'|'+('|'.join(member_ids))).encode('utf8'),digest_size=10).hexdigest()
                content={'schema_id':schema_id,
                         'atoms':[first['atom'].as_dict(),second['atom'].as_dict()],
                         'carrier':carrier}
                content_signature=json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
                out.append({'state_id':'state_'+digest,'schema_id':schema_id,
                            'meta_schema_id':state.get('meta_schema_id') if is_meta else None,
                            'representation_type':'latent_persistent_state',
                            # Keep target lexical structure for audit/materialization;
                            # the matching decision is made on its erased topology.
                            'structure':candidate['structure'],
                            'meta_topology':state.get('topology') if is_meta else None,
                            'member_fact_ids':list(member_ids),'bindings':candidate['bindings'],
                            'carrier':carrier,'sentence_span':candidate['sentence_span'],
                            'support':state.get('support',0),'content_signature':content_signature,
                            'mechanism':'latent_document_state_meta_v537' if is_meta else 'latent_document_state_v535'})
        return out

    @staticmethod
    def _document_state_gate_key(schema_id: str, predicate: str, slot: int) -> tuple[str,str]:
        payload=json.dumps([schema_id,predicate.lstrip('!'),int(slot),'persistent_state'],
                           ensure_ascii=False,separators=(',',':'))
        gate_id='state_gate_'+hashlib.blake2b(payload.encode('utf8'),digest_size=8).hexdigest()
        return payload,gate_id

    def _document_state_reference_support(self, candidate: dict, predicate: str, slot: int) -> int:
        if candidate.get('mechanism')=='latent_document_state_meta_v537':
            key,_=self._document_state_meta_gate_key(candidate.get('structure') or {},predicate,slot)
            state=self.document_state_meta_reference_hypotheses.get(key) or {}
            return int(state.get('support') or 0) if state.get('promoted') else 0
        key,_=self._document_state_gate_key(candidate.get('schema_id',''),predicate,slot)
        return int((self.document_state_reference_hypotheses.get(key) or {}).get('support') or 0)

    def _record_document_state_reference_use(self, candidate: dict, predicate: str, slot: int) -> dict:
        if candidate.get('mechanism')=='latent_document_state_meta_v537':
            # Meta-transferred successes are intentionally non-crediting.  Return
            # the already learned gate for provenance without mutating support.
            key,gate_id=self._document_state_meta_gate_key(candidate.get('structure') or {},predicate,slot)
            return self.document_state_meta_reference_hypotheses.get(key) or {
                'gate_id':gate_id,'promoted':False,'support':0,'meta_transfer_non_crediting':True}
        key,gate_id=self._document_state_gate_key(candidate.get('schema_id',''),predicate,slot)
        state=self.document_state_reference_hypotheses.setdefault(key,{
            'gate_id':gate_id,'schema_id':candidate.get('schema_id'),'predicate':predicate.lstrip('!'),
            'slot':int(slot),'representation_type':'latent_persistent_state','uses':[],
            'support':0,'promoted':False})
        signature=str(candidate.get('content_signature') or '')
        if signature and signature not in state['uses']:
            state['uses'].append(signature);del state['uses'][:-64]
        state['support']=len(set(state.get('uses') or []));was=bool(state.get('promoted'))
        state['promoted']=state['support']>=2
        if state['promoted'] and not was:
            event={'event':'document_state_reference_gate_promoted','gate_id':gate_id,
                   'schema_id':state['schema_id'],'predicate':state['predicate'],'slot':state['slot'],
                   'support':state['support'],'mechanism':'persistent_state_use_gate_v535'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:self.kb.audit.append(event)
            self.training_reports.append({'type':'document_state_reference_gate_promoted',**event})
        self._refresh_document_state_meta(candidate.get('structure') or {},predicate,slot)
        self._refresh_document_latent_strategy(predicate,slot)
        return state

    def _materialize_document_state(self, candidate: dict) -> dict:
        sid=candidate['state_id'];source=f'document_state_v535:{sid}'
        fact_ids=[self.kb.add(Atom('_state_schema',(sid,str(candidate['schema_id']))),source),
                  self.kb.add(Atom('_state_carrier',(sid,str(candidate['carrier']))),source)]
        for member in candidate.get('member_fact_ids') or []:
            fact_ids.append(self.kb.add(Atom('_state_evidence',(sid,str(member))),source))
        event={'event':'document_state_materialized','state_id':sid,'schema_id':candidate['schema_id'],
               'carrier':candidate['carrier'],'member_fact_ids':candidate.get('member_fact_ids',[]),
               'representation_fact_ids':fact_ids,'mechanism':'demand_driven_persistent_state_v535'}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:
            self.kb.audit.append(event)
        return event

    @staticmethod
    def _latent_structure_features(structure: dict) -> dict:
        """Return representation-family-neutral relational features.

        V5.38 deliberately uses a tiny auditable feature language.  It does not
        encode whether the source was an event or a state, predicate names,
        arities or argument positions.  The same calculation is available for
        learned abstract structures and concrete document fact bundles.
        """
        facts=list((structure or {}).get('facts') or [])
        role_sets=[set(row.get('roles') or []) for row in facts]
        shared=set()
        for i,left in enumerate(role_sets):
            for right in role_sets[i+1:]:
                shared.update(left & right)
        # Connectedness through shared abstract roles.
        if not role_sets:
            connected=False
        else:
            seen={0};changed=True
            while changed:
                changed=False
                for i in list(seen):
                    for j in range(len(role_sets)):
                        if j not in seen and role_sets[i] & role_sets[j]:
                            seen.add(j);changed=True
            connected=len(seen)==len(role_sets)
        predicates=[str(row.get('pred','')).lstrip('!') for row in facts]
        return {'fact_count':len(facts),'connected':bool(connected),
                'shared_role_count':len(shared),
                'all_positive':all(not str(row.get('pred','')).startswith('!') for row in facts),
                'predicate_count':len(set(predicates))}

    @staticmethod
    def _latent_concrete_features(rows: list[dict]) -> dict:
        """Concrete counterpart of ``_latent_structure_features`` for facts."""
        atoms=[row.get('atom') for row in rows if row.get('atom') is not None]
        arg_sets=[set(map(str,atom.args)) for atom in atoms]
        shared=set()
        for i,left in enumerate(arg_sets):
            for right in arg_sets[i+1:]:
                shared.update(left & right)
        if not arg_sets:
            connected=False
        else:
            seen={0};changed=True
            while changed:
                changed=False
                for i in list(seen):
                    for j in range(len(arg_sets)):
                        if j not in seen and arg_sets[i] & arg_sets[j]:
                            seen.add(j);changed=True
            connected=len(seen)==len(arg_sets)
        predicates=[str(atom.pred).lstrip('!') for atom in atoms]
        return {'fact_count':len(atoms),'connected':bool(connected),
                'shared_role_count':len(shared),
                'all_positive':all(not str(atom.pred).startswith('!') for atom in atoms),
                'predicate_count':len(set(predicates))}

    @staticmethod
    def _latent_strategy_key(predicate: str, slot: int) -> tuple[str,str]:
        payload=json.dumps([str(predicate).lstrip('!'),int(slot),'latent_representation_strategy'],
                           ensure_ascii=False,separators=(',',':'))
        strategy_id='latent_strategy_'+hashlib.blake2b(payload.encode('utf8'),digest_size=8).hexdigest()
        return payload,strategy_id

    def _refresh_document_latent_strategy(self, predicate: str, slot: int) -> dict:
        """Learn common proposal constraints across different representation types.

        Only exact, downstream-used event/state schemas can teach V5.38.  The
        target generic bundles never enter these stores, so successful transfer
        cannot increase the evidence that licensed the transfer.
        """
        predicate=str(predicate).lstrip('!');slot=int(slot)
        sources=[]
        # Exact event sources.
        for schema in self.document_event_schema_hypotheses.values():
            if not schema.get('promoted') or schema.get('contested'):
                continue
            uses=[u for u in schema.get('reference_uses') or []
                  if str(u.get('predicate')).lstrip('!')==predicate and int(u.get('slot',-1))==slot]
            if not uses:
                continue
            sources.append({'family':'event','schema_id':schema.get('schema_id'),
                            'features':self._latent_structure_features(schema.get('structure') or {}),
                            'uses':len({u.get('event_id') for u in uses if u.get('event_id')})})
        # Exact persistent-state sources.  Meta-transferred state gates do not
        # reside here and therefore cannot count as source evidence.
        for gate in self.document_state_reference_hypotheses.values():
            if str(gate.get('predicate')).lstrip('!')!=predicate or int(gate.get('slot',-1))!=slot:
                continue
            if not gate.get('uses'):
                continue
            schema_id=gate.get('schema_id')
            schema=next((s for s in self.document_state_schema_hypotheses.values()
                         if s.get('schema_id')==schema_id and s.get('promoted') and not s.get('contested')),None)
            if schema is None:
                continue
            sources.append({'family':'state','schema_id':schema_id,
                            'features':self._latent_structure_features(schema.get('structure') or {}),
                            'uses':len(set(gate.get('uses') or []))})

        families=sorted({row['family'] for row in sources})
        key,strategy_id=self._latent_strategy_key(predicate,slot)
        state=self.document_latent_strategy_hypotheses.setdefault(key,{
            'strategy_id':strategy_id,'predicate':predicate,'slot':slot,
            'source_representations':[],'source_families':[],'constraints':{},
            'support':0,'promoted':False,'contested':False,'counterexamples':[]})
        state['source_representations']=sources[-64:]
        state['source_families']=families
        state['support']=len(families)
        constraints={}
        feature_rows=[row.get('features') or {} for row in sources]
        for name in ('fact_count','connected','shared_role_count','all_positive','predicate_count'):
            vals=[row.get(name) for row in feature_rows if name in row]
            if vals and len(vals)==len(feature_rows) and all(v==vals[0] for v in vals):
                constraints[name]=vals[0]
        # Require at least two qualitatively distinct source families and a
        # genuinely relational common core.  This prevents a mere shared consumer
        # verb from licensing arbitrary latent nodes.  A V5.39 counterexample
        # remains contested even if more exact sources appear: no independent
        # recovery criterion has been established for the target bundle.
        was=bool(state.get('promoted'))
        state['constraints']=constraints
        state['promoted']=(len(families)>=2 and constraints.get('connected') is True
                           and int(constraints.get('fact_count') or 0)>=2
                           and int(constraints.get('shared_role_count') or 0)>=1
                           and not state.get('contested'))
        if state['promoted'] and not was:
            event={'event':'document_latent_strategy_promoted','strategy_id':strategy_id,
                   'predicate':predicate,'slot':slot,'support':state['support'],
                   'source_families':families,'constraints':constraints,
                   'mechanism':'cross_type_latent_proposal_strategy_v538'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:self.kb.audit.append(event)
            self.training_reports.append({'type':'document_latent_strategy_promoted',**event})
        return state

    def _document_latent_bundle_candidates(self, document_facts: list[dict],
                                           predicate: str, slot: int,
                                           occupied_member_sets: set[tuple[str,...]] | None = None) -> list[dict]:
        """Propose generic latent bundles from a learned cross-type strategy.

        The generator enumerates only bounded connected combinations whose size
        was learned from source representations.  It never chooses a semantic
        type.  Existing event/state/dependency representations with the same
        members dominate and suppress a redundant generic bundle.
        """
        key,_=self._latent_strategy_key(predicate,slot)
        policy=self.document_latent_strategy_hypotheses.get(key) or {}
        if not policy.get('promoted'):
            return []
        constraints=policy.get('constraints') or {}
        count=int(constraints.get('fact_count') or 0)
        if not 2<=count<=4:
            return []
        occupied=occupied_member_sets or set()
        # Resolver-produced facts are excluded: V5.38 must not train or propose
        # from its own previous decisions.  Keep the bounded recent document span
        # to avoid combinatorial growth on long inputs.
        explicit=[row for row in document_facts[-12:]
                  if row.get('atom') is not None
                  and not str(row.get('atom').pred).startswith('_')
                  and 'document_coreference_' not in str(row.get('source',''))]
        out=[];seen=set()
        for rows in combinations(explicit,count):
            ids=tuple(str(row.get('id')) for row in rows if row.get('id'))
            if len(ids)!=count:
                continue
            if tuple(sorted(ids)) in occupied:
                continue
            features=self._latent_concrete_features(list(rows))
            if any(features.get(name)!=value for name,value in constraints.items()):
                continue
            atoms=[row['atom'].as_dict() for row in rows]
            content={'strategy_id':policy.get('strategy_id'),'atoms':atoms}
            signature=json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
            if signature in seen:
                continue
            seen.add(signature)
            digest=hashlib.blake2b(signature.encode('utf8'),digest_size=10).hexdigest()
            out.append({'bundle_id':'latent_'+digest,'representation_type':'generic_latent_bundle',
                        'strategy_id':policy.get('strategy_id'),'member_fact_ids':list(ids),
                        'content_signature':signature,'features':features,
                        'support':int(policy.get('support') or 0),
                        'mechanism':'latent_document_bundle_meta_v538'})
        return out

    def _materialize_document_latent_bundle(self, candidate: dict) -> dict:
        bid=candidate['bundle_id'];source=f'document_latent_bundle_v538:{bid}'
        fact_ids=[self.kb.add(Atom('_latent_strategy',(bid,str(candidate.get('strategy_id')))),source)]
        for member in candidate.get('member_fact_ids') or []:
            fact_ids.append(self.kb.add(Atom('_latent_member',(bid,str(member))),source))
        event={'event':'document_latent_bundle_materialized','bundle_id':bid,
               'strategy_id':candidate.get('strategy_id'),
               'member_fact_ids':list(candidate.get('member_fact_ids') or []),
               'representation_fact_ids':fact_ids,
               'mechanism':'cross_type_latent_bundle_materialization_v538'}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:self.kb.audit.append(event)
        return event

    def _remove_orphan_document_latent_bundle(self, bundle_id: str) -> list[str]:
        """Remove a generic latent node once no ordinary fact still consumes it."""
        remaining=[f for f in self._facts_referencing_entity(bundle_id)
                   if not f['atom'].pred.startswith('_latent_')]
        if remaining:
            return []
        removed=[]
        for pattern in (Atom('_latent_strategy',(bundle_id,'?strategy')),
                        Atom('_latent_member',(bundle_id,'?member'))):
            for fact in list(self.kb.matches(pattern)):
                if self.kb.remove(fact['id']):removed.append(fact['id'])
        return removed

    def _record_document_latent_bundle_confirmation(self, pending: dict, fact: dict,
                                                    episode_id: str, source: str) -> dict | None:
        """Use a later explicit assertion as counterevidence to a generic bundle.

        This mirrors V5.31's non-circular future confirmation but applies to the
        V5.38 type-agnostic policy.  Resolver-produced facts are excluded.  One
        contradiction withdraws the concrete consumer policy conservatively;
        source event/state knowledge itself is preserved.
        """
        if not fact or 'document_coreference_' in str(fact.get('source','')):
            return None
        atom=fact.get('atom')
        if atom is None or atom.pred!=pending.get('predicate'):
            return None
        slot=int(pending.get('slot',-1));template=list(pending.get('args') or [])
        if len(atom.args)!=len(template) or not 0<=slot<len(template):
            return None
        for i,(actual,expected) in enumerate(zip(atom.args,template)):
            if i==slot:continue
            if str(actual)!=str(expected):return None
        bundle_id=str(pending.get('bundle_id') or '')
        replacement=str(atom.args[slot])
        if not bundle_id or replacement==bundle_id or normalize(replacement) in self._DOCUMENT_REFERENCE_MARKERS:
            return None
        old_id=pending.get('resolved_fact_id');old_fact=self.kb.get_fact(old_id) if old_id else None
        retracted=None;removed=[]
        if old_fact is not None and old_fact['atom'].pred==atom.pred:
            old_args=list(old_fact['atom'].args)
            if 0<=slot<len(old_args) and str(old_args[slot])==bundle_id:
                if self.kb.remove(old_id):
                    retracted=old_id;removed=self._remove_orphan_document_latent_bundle(bundle_id)
        policy=None
        for row in self.document_latent_strategy_hypotheses.values():
            if row.get('strategy_id')==pending.get('strategy_id'):
                policy=row;break
        if policy is None:
            return None
        counter={'episode_id':episode_id,'source':source,'bundle_id':bundle_id,
                 'old_fact_id':old_id,'confirming_fact_id':fact.get('id'),
                 'replacement':replacement,'predicate':atom.pred,'slot':slot}
        rows=policy.setdefault('counterexamples',[])
        if not any(x.get('episode_id')==episode_id and x.get('confirming_fact_id')==fact.get('id') for x in rows):
            rows.append(counter);del rows[:-32]
        policy['contested']=True;policy['promoted']=False
        audit={'event':'document_latent_strategy_counterexample','strategy_id':policy.get('strategy_id'),
               'predicate':policy.get('predicate'),'slot':policy.get('slot'),
               'bundle_id':bundle_id,'replacement':replacement,
               'old_fact_id':old_id,'confirming_fact_id':fact.get('id'),
               'removed_representation_fact_ids':removed,'policy_withdrawn':True,
               'mechanism':'future_explicit_latent_bundle_counterevidence_v539'}
        if hasattr(self.kb,'audit'):self.kb.audit.append(audit)
        self.training_reports.append({'type':'document_latent_strategy_counterexample',**audit})
        return {'retracted_fact_id':retracted,'removed_representation_fact_ids':removed,
                'strategy_id':policy.get('strategy_id'),'policy_withdrawn':True}

    @staticmethod
    def _document_event_topology(structure: dict) -> dict:
        """Erase predicate identity while preserving event-role geometry.

        Predicate names are deliberately removed; arity, polarity and equality
        pattern remain.  This lets V5.27 test whether a representation strategy
        transfers across entirely different learned vocabularies without treating
        all adjacent statements as equivalent.
        """
        facts=[];predicate_roles={}
        for row in (structure or {}).get('facts',[]):
            pred=str(row.get('pred',''))
            base=pred.lstrip('!')
            if base not in predicate_roles:
                predicate_roles[base]=len(predicate_roles)
            roles=list(row.get('roles') or [])
            facts.append({'predicate_role':predicate_roles[base],'arity':len(roles),
                          'negative':pred.startswith('!'),'roles':roles})
        return {'facts':facts,'role_count':int((structure or {}).get('role_count') or 0),
                'predicate_count':len(predicate_roles)}

    @classmethod
    def _document_event_topology_key(cls, structure: dict) -> tuple[str,str]:
        topology=cls._document_event_topology(structure)
        signature=json.dumps(topology,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        meta_id='event_meta_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return signature,meta_id

    def _refresh_document_event_meta(self, structure: dict) -> None:
        """Promote event topology after two predicate-disjoint proven uses.

        Structural recurrence alone does not teach this meta-level rule.  Source
        schemas must each have been materialized because a real document reference
        required the event representation.  At least two source families must use
        disjoint predicate vocabularies, preventing aliases/paraphrases of one
        lexical family from masquerading as cross-domain transfer evidence.
        """
        topology_key,meta_id=self._document_event_topology_key(structure)
        compatible=[]
        for state in self.document_event_schema_hypotheses.values():
            if not state.get('promoted') or state.get('contested') or not state.get('representation_uses'):
                continue
            if self._document_event_topology_key(state.get('structure') or {})[0] != topology_key:
                continue
            preds=tuple(row.get('pred') for row in (state.get('structure') or {}).get('facts',[]))
            compatible.append({'schema_id':state.get('schema_id'),'predicates':list(preds),
                               'uses':len(set(state.get('representation_uses') or []))})
        # Find a predicate-disjoint pair; more families may later add support.
        independent=[]
        for item in compatible:
            pset=set(item['predicates'])
            if not independent:
                independent.append(item);continue
            if all(pset.isdisjoint(set(other['predicates'])) for other in independent):
                independent.append(item)
        state=self.document_event_meta_hypotheses.setdefault(topology_key,{
            'meta_schema_id':meta_id,'topology':self._document_event_topology(structure),
            'source_schemas':[],'promoted':False})
        state['source_schemas']=compatible[-32:]
        was=bool(state.get('promoted'))
        state['support']=len(independent)
        state['promoted']=len(independent)>=2
        if state['promoted'] and not was:
            event={'event':'document_event_meta_promoted','meta_schema_id':meta_id,
                   'topology':state['topology'],'support':state['support'],
                   'source_schema_ids':[x['schema_id'] for x in independent],
                   'source_predicate_families':[x['predicates'] for x in independent],
                   'mechanism':'predicate_disjoint_event_topology_transfer_v527'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_meta_promoted',**event})
        elif was and not state['promoted']:
            event={'event':'document_event_meta_withdrawn','meta_schema_id':meta_id,
                   'topology':state['topology'],'support':state['support'],
                   'remaining_source_schema_ids':[x['schema_id'] for x in independent],
                   'mechanism':'source_schema_counterevidence_v530'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_meta_withdrawn',**event})

    @classmethod
    def _document_event_reference_gate_key(cls, structure: dict, predicate: str, slot: int) -> tuple[str,str]:
        """Identify one topology + downstream consumer role without lexicalizing the event internals."""
        topology_key,_=cls._document_event_topology_key(structure)
        payload={'topology_key':topology_key,'predicate':str(predicate),'slot':int(slot)}
        signature=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        gate_id='event_gate_'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return signature,gate_id

    def _refresh_document_event_reference_gate(self, structure: dict, predicate: str, slot: int) -> dict:
        """Learn where an event representation has been useful from exact-schema uses only.

        A gate requires two predicate-disjoint exact event schemas that were each
        actually materialized in this downstream predicate/slot.  Meta-transferred
        uses never add support, so the gate cannot self-confirm.  Contested exact
        schemas are excluded from support.
        """
        key,gate_id=self._document_event_reference_gate_key(structure,predicate,slot)
        topology_key,_=self._document_event_topology_key(structure)
        compatible=[]
        for state in self.document_event_schema_hypotheses.values():
            if not state.get('promoted') or state.get('contested'):
                continue
            if self._document_event_topology_key(state.get('structure') or {})[0]!=topology_key:
                continue
            uses=[]
            for use in state.get('reference_uses') or []:
                if use.get('predicate')==predicate and int(use.get('slot',-1))==int(slot):
                    uses.append(use)
            if not uses:
                continue
            preds=tuple(row.get('pred') for row in (state.get('structure') or {}).get('facts',[]))
            compatible.append({'schema_id':state.get('schema_id'),'predicates':list(preds),
                               'uses':len({u.get('event_id') for u in uses if u.get('event_id')})})
        independent=[]
        for item in compatible:
            pset=set(item['predicates'])
            if not independent or all(pset.isdisjoint(set(other['predicates'])) for other in independent):
                independent.append(item)
        state=self.document_event_reference_hypotheses.setdefault(key,{
            'gate_id':gate_id,'topology_key':topology_key,'predicate':predicate,'slot':int(slot),
            'source_schemas':[],'promoted':False,'contested':False,'counterexamples':[]})
        state['source_schemas']=compatible[-32:]
        was=bool(state.get('promoted'))
        state['support']=len(independent)
        # A direct correction proves the universal transfer gate unsafe.  Keep the
        # evidence but never silently erase the counterexample by accumulating use.
        state['promoted']=len(independent)>=2 and not state.get('contested')
        if state['promoted'] and not was:
            event={'event':'document_event_reference_gate_promoted','gate_id':gate_id,
                   'topology_key':topology_key,'predicate':predicate,'slot':int(slot),
                   'support':state['support'],'source_schema_ids':[x['schema_id'] for x in independent],
                   'mechanism':'predicate_disjoint_event_consumer_gate_v529'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_reference_gate_promoted',**event})
        elif was and not state['promoted']:
            event={'event':'document_event_reference_gate_withdrawn','gate_id':gate_id,
                   'topology_key':topology_key,'predicate':predicate,'slot':int(slot),
                   'support':state['support'],'contested':bool(state.get('contested')),
                   'mechanism':'counterevidence_or_support_withdrawal_v529'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_reference_gate_withdrawn',**event})
        # Keep a previously created V5.31 choice synchronized with exact-use support.
        if key in self.document_event_choice_hypotheses:
            self._refresh_document_event_choice(structure,predicate,slot)
        return state

    def _refresh_document_event_choice(self, structure: dict, predicate: str, slot: int) -> dict:
        """Score event-vs-independent representations from non-circular evidence.

        V5.31 deliberately uses a margin rather than majority-on-one-example.
        Two independent exact event families are enough only while there is no
        contrary independently confirmed episode.  Once contrary evidence
        appears, the system abstains until either hypothesis leads by >=2
        independent supports.  This makes a single surprise reduce confidence
        before an explicit user correction is required.
        """
        key,gate_id=self._document_event_reference_gate_key(structure,predicate,slot)
        gate=self.document_event_reference_hypotheses.get(key) or {}
        state=self.document_event_choice_hypotheses.setdefault(key,{
            'choice_id':'choice_'+gate_id.removeprefix('event_gate_'),
            'gate_id':gate_id,'topology_key':self._document_event_topology_key(structure)[0],
            'predicate':predicate,'slot':int(slot),'independent_confirmations':[],
            'decision':'abstain'})
        event_support=int(gate.get('support') or 0) if not gate.get('contested') else 0
        confirmations=state.get('independent_confirmations') or []
        independent_support=len({x.get('episode_id') for x in confirmations if x.get('episode_id')})
        old=state.get('decision','abstain')
        if event_support>=2 and event_support>=independent_support+2:
            decision='event'
        elif independent_support>=2 and independent_support>=event_support+2:
            decision='independent'
        else:
            decision='abstain'
        state.update({'event_support':event_support,'independent_support':independent_support,
                      'decision':decision,'gate_contested':bool(gate.get('contested'))})
        if decision!=old:
            event={'event':'document_event_representation_choice_changed',
                   'choice_id':state['choice_id'],'gate_id':gate_id,
                   'predicate':predicate,'slot':int(slot),'old_decision':old,
                   'decision':decision,'event_support':event_support,
                   'independent_support':independent_support,
                   'mechanism':'noncircular_representation_credit_v531'}
            if hasattr(self.kb,'audit'):
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_representation_choice_changed',**event})
        return state

    def _record_document_event_independent_confirmation(self, pending: dict, fact: dict,
                                                        episode_id: str, source: str) -> dict | None:
        """Credit the independent-entity hypothesis from a later explicit fact.

        The confirmation must match the ambiguous predicate and every non-reference
        argument, and its disputed slot must equal the concrete entity candidate.
        Coreference-resolved facts are excluded because they depend on the resolver
        whose hypothesis is being evaluated.
        """
        if not fact or 'document_coreference_' in str(fact.get('source','')):
            return None
        atom=fact.get('atom')
        if atom is None or atom.pred!=pending.get('predicate'):
            return None
        slot=int(pending.get('slot',-1)); template=list(pending.get('args') or [])
        if len(atom.args)!=len(template) or not 0<=slot<len(template):
            return None
        for i,(actual,expected) in enumerate(zip(atom.args,template)):
            if i==slot:
                continue
            if str(actual)!=str(expected):
                return None
        if str(atom.args[slot])!=str(pending.get('entity_candidate')):
            return None
        structure=pending.get('structure') or {}
        key,_=self._document_event_reference_gate_key(structure,atom.pred,slot)
        state=self.document_event_choice_hypotheses.setdefault(key,{
            'choice_id':'choice_'+hashlib.blake2b(key.encode('utf8'),digest_size=8).hexdigest(),
            'topology_key':self._document_event_topology_key(structure)[0],
            'predicate':atom.pred,'slot':slot,'independent_confirmations':[],
            'decision':'abstain'})
        row={'episode_id':episode_id,'source':source,'predicate':atom.pred,'slot':slot,
             'entity':str(atom.args[slot]),'ambiguous_sentence_index':pending.get('sentence_index'),
             'confirming_fact_id':fact.get('id')}
        confirmations=state.setdefault('independent_confirmations',[])
        if not any(x.get('episode_id')==episode_id for x in confirmations):
            confirmations.append(row);del confirmations[:-64]
            event={'event':'document_event_independent_confirmation','choice_id':state.get('choice_id'),
                   **row,'mechanism':'later_explicit_disambiguation_v531'}
            if hasattr(self.kb,'audit'):
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_event_independent_confirmation',**event})
        retracted=None; removed_representation=[]
        old_id=pending.get('resolved_fact_id'); event_id=str(pending.get('event_id') or '')
        old_fact=self.kb.get_fact(old_id) if old_id and hasattr(self.kb,'get_fact') else None
        if old_fact is not None and old_fact['atom'].pred==atom.pred:
            old_args=list(old_fact['atom'].args)
            if 0<=slot<len(old_args) and str(old_args[slot])==event_id:
                if self.kb.remove(old_id):
                    retracted=old_id
                    removed_representation=self._remove_orphan_document_event(event_id)
                    audit={'event':'document_event_representation_auto_revised',
                           'choice_id':state.get('choice_id'),'old_fact_id':old_id,
                           'confirming_fact_id':fact.get('id'),'event_id':event_id,
                           'replacement':str(atom.args[slot]),
                           'removed_representation_fact_ids':removed_representation,
                           'mechanism':'future_explicit_confirmation_v531'}
                    if hasattr(self.kb,'audit'):
                        self.kb.audit.append(audit)
                    self.training_reports.append({'type':'document_event_representation_auto_revised',**audit})
        choice=self._refresh_document_event_choice(structure,atom.pred,slot)
        return {'choice_state':choice,'retracted_fact_id':retracted,
                'removed_representation_fact_ids':removed_representation}

    def _document_event_representation_decision(self, candidate: dict, predicate: str, slot: int) -> str:
        """Return event/independent/abstain for a meta-transferred event candidate."""
        if candidate.get('mechanism')!='latent_document_event_meta_v527':
            return 'event'
        return self._refresh_document_event_choice(candidate.get('structure') or {},predicate,slot).get('decision','abstain')

    def _record_document_event_reference_use(self, candidate: dict, predicate: str, slot: int) -> dict | None:
        """Record one non-circular use of an exact event schema in a downstream role."""
        if candidate.get('mechanism')=='latent_document_event_meta_v527':
            return None
        schema_id=candidate.get('schema_id'); event_id=candidate.get('event_id')
        target=None
        for state in self.document_event_schema_hypotheses.values():
            if state.get('schema_id')==schema_id:
                target=state;break
        if target is None:
            return None
        uses=target.setdefault('reference_uses',[])
        row={'event_id':event_id,'predicate':predicate,'slot':int(slot)}
        if row not in uses:
            uses.append(row);del uses[:-32]
        gate=self._refresh_document_event_reference_gate(target.get('structure') or {},predicate,slot)
        self._refresh_document_latent_strategy(predicate,slot)
        return gate

    def _document_event_reference_gate_allows(self, candidate: dict, predicate: str, slot: int) -> bool:
        """Return whether a meta event may be consumed in this discourse role."""
        if candidate.get('mechanism')!='latent_document_event_meta_v527':
            return True
        key,_=self._document_event_reference_gate_key(candidate.get('structure') or {},predicate,slot)
        state=self.document_event_reference_hypotheses.get(key) or {}
        return bool(state.get('promoted')) and not bool(state.get('contested'))

    def _event_meta_bootstrap_plan(self, left: dict, right: dict, meta: dict) -> dict | None:
        """Test whether two raw document spans instantiate one learned event topology.

        Every sentence position is anti-unified independently, then the extracted
        arguments must satisfy the cross-sentence equality pattern learned at the
        event-meta level.  This is stronger evidence than two unrelated examples
        of each surface and is the only reason V5.28 may use two episodes instead
        of the ordinary raw learner's minimum of three.
        """
        topology=meta.get('topology') or {}; tfacts=list(topology.get('facts') or [])
        lt=list(left.get('texts') or []); rt=list(right.get('texts') or [])
        if not tfacts or len(lt)!=len(tfacts) or len(rt)!=len(tfacts):
            return None
        if any(bool(f.get('negative')) for f in tfacts):
            return None
        rows=[]
        for i,(a,b,trow) in enumerate(zip(lt,rt,tfacts)):
            proposal=self._raw_relation_pair_surface(a,b,max_slots=self.raw_relation_max_arity)
            if proposal is None:
                return None
            surface,arity=proposal
            if arity!=int(trow.get('arity') or 0):
                return None
            ma=self._raw_relation_match(surface,a,limit=2);mb=self._raw_relation_match(surface,b,limit=2)
            if len(ma)!=1 or len(mb)!=1:
                return None
            rows.append({'position':i,'surface':surface,'arity':arity,
                         'left_args':list(ma[0]),'right_args':list(mb[0]),
                         'predicate_role':int(trow.get('predicate_role',i)),
                         'roles':list(trow.get('roles') or [])})
        # Preserve predicate identity equality while allowing completely new names.
        by_pred_role={}
        for row in rows:
            prior=by_pred_role.setdefault(row['predicate_role'],row['surface'])
            if prior!=row['surface']:
                return None
        for a,b in combinations(rows,2):
            if a['predicate_role']!=b['predicate_role'] and a['surface']==b['surface']:
                return None

        def role_bindings(side: str):
            mapping={}
            for row in rows:
                args=row[side+'_args']
                if len(args)!=len(row['roles']):
                    return None
                for role,value in zip(row['roles'],args):
                    if role in mapping and mapping[role]!=value:
                        return None
                    mapping[role]=value
            required=set(range(int(topology.get('role_count') or 0)))
            if set(mapping)!=required:
                return None
            # Keep the evidence maximally diagnostic: different abstract roles
            # may not collapse onto one concrete value in either support episode.
            if len(set(mapping.values()))!=len(mapping):
                return None
            return mapping
        lb=role_bindings('left');rb=role_bindings('right')
        if lb is None or rb is None:
            return None
        if any(lb[i]==rb[i] for i in lb):
            return None
        surfaces=[r['surface'] for r in rows]
        key=json.dumps({'meta_schema_id':meta.get('meta_schema_id'),'surfaces':surfaces},
                       sort_keys=True,separators=(',',':'),ensure_ascii=False)
        return {'key':key,'meta_schema_id':meta.get('meta_schema_id'),'topology':topology,
                'rows':rows,'episode_ids':[left.get('episode_id'),right.get('episode_id')],
                'episodes':[left,right]}

    def _promote_event_meta_bootstrap(self, plan: dict) -> dict:
        """Atomically promote raw relations justified by one unique V5.28 plan."""
        scratch=Language.from_dict(self.language.as_dict())
        prepared=[]
        left,right=plan['episodes']
        for row in plan['rows']:
            surface=row['surface'];arity=row['arity'];pred=self._raw_relation_predicate(surface,arity)
            existing=self.raw_relation_promotions.get(surface)
            if existing and (existing.get('predicate')!=pred or int(existing.get('arity') or 0)!=arity):
                return {'status':'document_event_meta_bootstrap_conflict','surface':surface}
            evidence=[]
            for episode,args in ((left,row['left_args']),(right,row['right_args'])):
                pos=row['position'];text=episode['texts'][pos];src=episode['sources'][pos]
                frame={'act':'assert','pred':pred,'args':list(args)}
                if not existing:
                    try:
                        scratch.teach(text,frame,'event_meta_bootstrap_v528',
                                      [f'meta:{plan["meta_schema_id"]}',f'surface:{surface}'])
                    except ValueError:
                        return {'status':'document_event_meta_bootstrap_conflict','surface':surface,
                                'reason':'language_alignment_failed'}
                evidence.append({'text':normalize(text),'args':list(args),'source':src})
            prepared.append({'surface':surface,'arity':arity,'predicate':pred,
                             'existing':existing,'evidence':evidence})
        learned=[]
        for item in prepared:
            if item['existing']:
                learned.append({'surface':item['surface'],'predicate':item['predicate'],'existing':True})
                continue
            fact_ids=[];changed=False
            for evidence in item['evidence']:
                frame={'act':'assert','pred':item['predicate'],'args':evidence['args']}
                changed=self.language.teach(evidence['text'],frame,'event_meta_bootstrap_v528',
                                            [f'meta:{plan["meta_schema_id"]}',f'surface:{item["surface"]}']) or changed
                fid=self.kb.add(Atom(item['predicate'],tuple(evidence['args'])),
                                f'{evidence["source"]}:event_meta_bootstrap_v528')
                fact_ids.append(fid);evidence['fact_id']=fid
            promotion={'predicate':item['predicate'],'surface':item['surface'],'arity':item['arity'],
                       'support':2,'evidence':item['evidence'],
                       'mechanism':'event_topology_constrained_antiunification_v528',
                       'meta_schema_id':plan['meta_schema_id'],'meta_transferred':True,
                       'event_meta_bootstrapped':True}
            self.raw_relation_promotions[item['surface']]=promotion
            for obs in self.raw_relation_observations:
                if normalize(obs.get('text','')) in {x['text'] for x in item['evidence']}:
                    obs['consumed_by']=item['predicate']
            event={'event':'raw_relation_event_meta_bootstrapped',**promotion}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'raw_relation_event_meta_bootstrapped',**promotion})
            self._apply_question_transforms(promotion)
            learned.append({'surface':item['surface'],'predicate':item['predicate'],
                            'existing':False,'fact_ids':fact_ids,'construction_added':bool(changed)})
        for episode in plan['episodes']:
            episode['consumed_by']=plan['key']
        event={'event':'document_event_meta_bootstrap_promoted','meta_schema_id':plan['meta_schema_id'],
               'episode_ids':plan['episode_ids'],'relations':learned,
               'mechanism':'event_topology_constrained_antiunification_v528'}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:
            self.kb.audit.append(event)
        self.training_reports.append({'type':'document_event_meta_bootstrap_promoted',**event})
        return {'status':'document_event_meta_bootstrap_learned','meta_schema_id':plan['meta_schema_id'],
                'relations':learned,'episode_ids':plan['episode_ids']}

    def _observe_document_event_meta_bootstrap(self, sentences: list[str], results: list[dict],
                                               source: str, episode_id: str) -> dict:
        """Use a proven event topology to bootstrap otherwise under-supported raw relations."""
        metas=[s for s in self.document_event_meta_hypotheses.values() if s.get('promoted')]
        if not metas:
            return {'status':'document_event_meta_bootstrap_inactive'}
        eligible={'raw_relation_pending','raw_relation_duplicate'}
        current=[]
        for meta in metas:
            n=len((meta.get('topology') or {}).get('facts') or [])
            if not 2<=n<=4 or len(sentences)<n:
                continue
            for start in range(0,len(sentences)-n+1):
                rows=results[start:start+n]
                if len(rows)!=n or any(r.get('status') not in eligible for r in rows):
                    continue
                texts=[];sources=[];ok=True
                for offset in range(n):
                    _,semantic=self._document_discourse_prefix(sentences[start+offset])
                    if self._question_like(semantic) or self._document_has_reference_marker(semantic):
                        ok=False;break
                    texts.append(normalize(semantic));sources.append(f'{source}:oración:{start+offset+1}')
                if ok:
                    current.append({'episode_id':f'{episode_id}:{start+1}-{start+n}',
                                    'document_episode_id':episode_id,'document_source':source,
                                    'texts':texts,'sources':sources,'length':n,
                                    'meta_schema_id':meta.get('meta_schema_id'),'consumed_by':None})
        if not current:
            return {'status':'document_event_meta_bootstrap_no_span'}
        added=[]
        for obs in current:
            if not any(o.get('episode_id')==obs['episode_id'] for o in self.document_event_bootstrap_observations):
                self.document_event_bootstrap_observations.append(obs);added.append(obs)
        self.document_event_bootstrap_observations=self.document_event_bootstrap_observations[-64:]
        plans={}
        pending=[o for o in self.document_event_bootstrap_observations if not o.get('consumed_by')]
        meta_by_id={m.get('meta_schema_id'):m for m in metas}
        for right in added:
            meta=meta_by_id.get(right.get('meta_schema_id'))
            if not meta:
                continue
            for left in pending:
                if left is right or left.get('document_episode_id')==right.get('document_episode_id'):
                    continue
                if left.get('meta_schema_id')!=right.get('meta_schema_id') or left.get('length')!=right.get('length'):
                    continue
                plan=self._event_meta_bootstrap_plan(left,right,meta)
                if plan:
                    plans[plan['key']]=plan
        if not plans:
            return {'status':'document_event_meta_bootstrap_pending','episodes_added':len(added)}
        if len(plans)!=1:
            return {'status':'document_event_meta_bootstrap_ambiguous','candidates':sorted(plans)}
        return self._promote_event_meta_bootstrap(next(iter(plans.values())))

    def _observe_document_event_schema(self, fact: dict, prior_facts: list[dict],
                                       episode_id: str, document_source: str) -> None:
        """Accumulate evidence for a structural event schema without creating events.

        Promotion requires the same structural pair in at least three independent
        document contents and every abstract role must vary across those episodes.
        Re-ingesting identical content under another source therefore cannot
        manufacture support, and fixed lexical/entity constants cannot be hidden
        inside an invented role.
        """
        if not fact or 'document_coreference_' in str(fact.get('source','')):
            return
        current_index=self._document_sentence_index(fact)
        if current_index is None:
            return
        explicit_by_index={}
        for row in prior_facts:
            if 'document_coreference_' in str(row.get('source','')):
                continue
            idx=self._document_sentence_index(row)
            if idx is not None:
                explicit_by_index.setdefault(idx,[]).append(row)
        explicit_by_index.setdefault(current_index,[]).append(fact)
        for size in range(2,5):
            start=current_index-size+1
            if start<1:
                continue
            rows=[]; valid=True
            for idx in range(start,current_index+1):
                choices=explicit_by_index.get(idx,[])
                # Multiple explicit facts in one sentence create alternative
                # partitions; do not use them as unsupervised event evidence.
                if len(choices)!=1:
                    valid=False;break
                rows.append(choices[0])
            if not valid:
                continue
            candidate=self._document_event_cluster_signature(rows)
            if candidate is None:
                continue
            key=candidate['signature']
            state=self.document_event_schema_hypotheses.setdefault(key,{
                'schema_id':candidate['schema_id'],'signature':key,
                'structure':candidate['structure'],'observations':[],'promoted':False})
            if any(o.get('episode_id')==episode_id for o in state['observations']):
                continue
            state['observations'].append({
                'episode_id':episode_id,'document_source':str(document_source),
                'bindings':candidate['bindings'],'member_fact_ids':candidate['member_fact_ids'],
                'sentence_span':candidate['sentence_span']})
            state['observations']=state['observations'][-64:]
            observations=state['observations']
            episodes={o.get('episode_id') for o in observations}
            role_count=int((state.get('structure') or {}).get('role_count') or 0)
            role_values=[]
            for i in range(role_count):
                role_values.append({tuple(o.get('bindings') or [])[i]
                                    for o in observations if len(o.get('bindings') or [])>i})
            was=bool(state.get('promoted'))
            if len(episodes)>=3 and role_count>=1 and all(len(values)>=3 for values in role_values):
                state['promoted']=True
                state['support']=len(episodes)
                if not was:
                    mechanism='structural_pair_induction_v525' if size==2 else 'structural_cluster_induction_v526'
                    event={'event':'document_event_schema_promoted','schema_id':state['schema_id'],
                           'structure':state['structure'],'support':state['support'],
                           'episode_ids':sorted(episodes),'mechanism':mechanism}
                    if hasattr(self.kb,'audit') and event not in self.kb.audit:
                        self.kb.audit.append(event)
                    self.training_reports.append({'type':'document_event_schema_promoted',**event})

    def _document_event_candidates(self, document_facts: list[dict], maximal: bool = True) -> list[dict]:
        """Return promoted event-schema matches in the current document.

        Candidates remain hypothetical.  No event node is written here.  This is
        crucial because a document can contain two equally compatible partitions;
        such a case must remain ambiguous rather than polluting memory with two
        invented event entities.
        """
        if len(document_facts)<2:
            return []
        by_index={}
        for fact in document_facts:
            idx=self._document_sentence_index(fact)
            if idx is not None:
                by_index.setdefault(idx,[]).append(fact)
        out=[]; seen=set()
        promoted={k:s for k,s in self.document_event_schema_hypotheses.items()
                  if s.get('promoted') and not s.get('contested')}
        meta_promoted={k:s for k,s in self.document_event_meta_hypotheses.items() if s.get('promoted')}
        if not promoted and not meta_promoted:
            return []
        indices=sorted(by_index)
        for end in indices:
            for size in range(2,5):
                start=end-size+1
                rows=[];valid=True
                for idx in range(start,end+1):
                    choices=by_index.get(idx,[])
                    if len(choices)!=1:
                        valid=False;break
                    rows.append(choices[0])
                if not valid:
                    continue
                candidate=self._document_event_cluster_signature(rows)
                if candidate is None:
                    continue
                member_ids=tuple(candidate['member_fact_ids'])
                if candidate['signature'] in promoted:
                    state=promoted[candidate['signature']]
                    key=(state['schema_id'],member_ids)
                    if key not in seen:
                        seen.add(key)
                        digest=hashlib.blake2b((state['schema_id']+'|'+('|'.join(member_ids))).encode('utf8'),digest_size=10).hexdigest()
                        out.append({'event_id':'event_'+digest,'schema_id':state['schema_id'],
                                    'signature':candidate['signature'],'structure':state['structure'],
                                    'member_fact_ids':list(member_ids),'bindings':candidate['bindings'],
                                    'sentence_span':candidate['sentence_span'],'support':state.get('support',0),
                                    'mechanism':'latent_document_event_v525' if size==2 else 'latent_document_event_v526'})
                topology_key,_=self._document_event_topology_key(candidate['structure'])
                if topology_key in meta_promoted:
                    meta=meta_promoted[topology_key]
                    key=(meta['meta_schema_id'],member_ids)
                    if key not in seen:
                        seen.add(key)
                        digest=hashlib.blake2b((meta['meta_schema_id']+'|'+('|'.join(member_ids))).encode('utf8'),digest_size=10).hexdigest()
                        out.append({'event_id':'event_'+digest,'schema_id':meta['meta_schema_id'],
                                    'signature':candidate['signature'],'structure':candidate['structure'],
                                    'topology':meta['topology'],'member_fact_ids':list(member_ids),
                                    'bindings':candidate['bindings'],'sentence_span':candidate['sentence_span'],
                                    'support':meta.get('support',0),'mechanism':'latent_document_event_meta_v527'})
        # If an exact schema and a meta-schema explain exactly the same member
        # set, the exact learned representation is strictly more specific.  Keep
        # it rather than manufacturing an ambiguity between equivalent scopes.
        by_members={}
        for candidate in out:
            key=tuple(candidate['member_fact_ids'])
            by_members.setdefault(key,[]).append(candidate)
        reduced=[]
        for group in by_members.values():
            exact=[x for x in group if x.get('mechanism')!='latent_document_event_meta_v527']
            reduced.extend(exact if exact else group)
        out=reduced
        if not maximal:
            return out
        return self._maximal_document_event_candidates(out)

    @staticmethod
    def _maximal_document_event_candidates(candidates: list[dict]) -> list[dict]:
        """Keep only candidates that are not strict member-subsets of another.

        This preserves V5.26's conservative fallback.  V5.32 can explicitly bypass
        it when there is independent predictive evidence for competing scopes.
        """
        maximal=[]
        for candidate in candidates:
            members=set(candidate.get('member_fact_ids') or [])
            if any(members < set(other.get('member_fact_ids') or []) for other in candidates):
                continue
            maximal.append(candidate)
        return maximal

    def _document_event_scope_support(self, candidate: dict, predicate: str, slot: int) -> int:
        """Return non-circular downstream-use support for one event scope.

        Exact schemas are credited only by actual prior materializations in this
        consumer role. Meta schemas use the already predicate-disjoint V5.29 gate
        support. Meta-transferred uses therefore cannot boost their own score.
        """
        if candidate.get('mechanism')=='latent_document_event_meta_v527':
            key,_=self._document_event_reference_gate_key(candidate.get('structure') or {},predicate,slot)
            state=self.document_event_reference_hypotheses.get(key) or {}
            if state.get('contested') or not state.get('promoted'):
                return 0
            return int(state.get('support') or 0)
        schema_id=candidate.get('schema_id')
        for state in self.document_event_schema_hypotheses.values():
            if state.get('schema_id')!=schema_id or state.get('contested'):
                continue
            uses={u.get('event_id') for u in (state.get('reference_uses') or [])
                  if u.get('predicate')==predicate and int(u.get('slot',-1))==int(slot) and u.get('event_id')}
            return len(uses)
        return 0

    def _select_document_event_scopes(self, candidates: list[dict], predicate: str, slot: int) -> tuple[list[dict], dict]:
        """Generate and arbitrate competing event scopes from learned utility.

        V5.31 could compare an event with an entity, but event scope itself was
        fixed by V5.26's maximal-cluster heuristic. V5.32 exposes every learned
        compatible scope (for example a two-fact subevent and a three-fact event)
        and compares them using *prior* downstream-use evidence. A candidate must
        lead the runner-up by at least two independent supports; otherwise the
        competing scopes remain visible and force abstention. If predictive
        evidence is insufficient, the historical maximal-cluster policy remains
        the conservative fallback, preserving older exact-schema behavior.
        """
        if not candidates:
            return [],{'status':'no_event_scope'}
        viable=[c for c in candidates if self._document_event_reference_gate_allows(c,predicate,slot)]
        if not viable:
            return [],{'status':'no_licensed_event_scope'}
        meta=[c for c in viable if c.get('mechanism')=='latent_document_event_meta_v527']
        scored=[]
        for c in meta:
            support=self._document_event_scope_support(c,predicate,slot)
            scored.append((support,len(c.get('member_fact_ids') or []),c))
        supported=[row for row in scored if row[0]>0]
        if len(supported)<2:
            selected=self._maximal_document_event_candidates(viable)
            return selected,{'status':'maximal_fallback','candidate_count':len(viable),
                             'selected_count':len(selected)}
        supported.sort(key=lambda row:(-row[0],-row[1],str(row[2].get('schema_id')),
                                        tuple(row[2].get('member_fact_ids') or [])))
        top=supported[0]; runner=supported[1]
        detail=[{'event_id':c.get('event_id'),'schema_id':c.get('schema_id'),
                 'members':list(c.get('member_fact_ids') or []),'support':support,
                 'span':list(c.get('sentence_span') or [])}
                for support,_,c in supported]
        if top[0] >= runner[0] + 2:
            chosen=dict(top[2])
            chosen['scope_selection']={'mechanism':'predictive_scope_competition_v532',
                                       'support':top[0],'runner_up_support':runner[0],
                                       'candidates':detail}
            audit={'event':'document_event_scope_selected','predicate':predicate,'slot':int(slot),
                   'event_id':chosen.get('event_id'),'support':top[0],
                   'runner_up_support':runner[0],'candidates':detail,
                   'mechanism':'predictive_scope_competition_v532'}
            if hasattr(self.kb,'audit') and audit not in self.kb.audit:
                self.kb.audit.append(audit)
            return [chosen],{'status':'scope_selected',**audit}
        # Do not fall back to cluster size once two independently supported scopes
        # are genuinely competing. Keeping both candidates causes the resolver to
        # report ambiguity rather than silently choosing the larger representation.
        competing=[]
        ids={id(row[2]) for row in supported}
        for c in viable:
            if id(c) in ids:
                cc=dict(c); cc['scope_selection']={'mechanism':'predictive_scope_competition_v532',
                                                    'decision':'abstain','candidates':detail}
                competing.append(cc)
        return competing,{'status':'scope_ambiguous','candidates':detail}

    @staticmethod
    def _document_dependency_gate_key(predicate: str, slot: int, link_predicate: str) -> tuple[str,str]:
        payload=json.dumps([predicate.lstrip('!'),int(slot),str(link_predicate)],
                           ensure_ascii=False,separators=(',',':'))
        gate_id='dependency_gate_'+hashlib.blake2b(payload.encode('utf8'),digest_size=8).hexdigest()
        return payload,gate_id

    def _document_dependency_candidates(self, document_facts: list[dict]) -> list[dict]:
        """Generate representation types from explicit safe document-link atoms.

        The generator does not enumerate semantic kinds such as ``causal`` or
        ``temporal``.  It discovers binary predicates already present in the KB
        whose names begin with ``_doc_``. Those atoms are trusted only as discourse
        relations because they were created by the bounded document parser, never
        from arbitrary user predicate names.  Each distinct link predicate defines
        a candidate representation type with its own predictive gate.
        """
        ids={str(row.get('id')) for row in document_facts if row.get('id')}
        if len(ids)<2:
            return []
        arity=getattr(self.kb,'arity',{}) or {}
        link_preds=sorted(p for p,n in arity.items() if str(p).startswith('_doc_') and int(n)==2)
        out=[];seen=set()
        for pred in link_preds:
            for link in self.kb.matches(Atom(pred,('?from','?to'))):
                # Internal-looking names are not a trust boundary. Only links
                # actually emitted by V5.24's bounded discourse parser may define
                # representation types. Dataset/user-injected ``_doc_*`` facts are
                # ignored even if their endpoints happen to be current facts.
                if 'document_discourse_v524' not in str(link.get('source','')):
                    continue
                a,b=link['atom'].args
                if a not in ids or b not in ids:
                    continue
                first=self.kb.get_fact(a);second=self.kb.get_fact(b)
                if first is None or second is None:
                    continue
                content={'link_predicate':pred,'from':first['atom'].as_dict(),'to':second['atom'].as_dict()}
                signature=json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
                key=(pred,signature)
                if key in seen:
                    continue
                seen.add(key)
                digest=hashlib.blake2b(signature.encode('utf8'),digest_size=10).hexdigest()
                out.append({'dependency_id':'dependency_'+digest,'link_predicate':pred,
                            'representation_type':'document_dependency:'+pred,
                            'from_fact_id':a,'to_fact_id':b,'member_fact_ids':[a,b],
                            'content_signature':signature,'link_fact_id':link.get('id'),
                            'mechanism':'latent_document_dependency_v534'})
        return out

    def _document_dependency_reference_support(self, predicate: str, slot: int, link_predicate: str) -> int:
        key,_=self._document_dependency_gate_key(predicate,slot,link_predicate)
        state=self.document_dependency_reference_hypotheses.get(key) or {}
        # Backward-compatible causal evidence from V5.33 participates in the
        # generic V5.34 family even before a save/reload migration.
        if not state and link_predicate=='_doc_causes':
            return self._document_causal_reference_support(predicate,slot)
        return int(state.get('support') or 0)

    def _record_document_dependency_reference_use(self, candidate: dict, predicate: str, slot: int) -> dict:
        link_predicate=str(candidate.get('link_predicate') or '')
        key,gate_id=self._document_dependency_gate_key(predicate,slot,link_predicate)
        state=self.document_dependency_reference_hypotheses.setdefault(key,{
            'gate_id':gate_id,'predicate':predicate.lstrip('!'),'slot':int(slot),
            'link_predicate':link_predicate,
            'representation_type':candidate.get('representation_type'),
            'uses':[],'support':0,'promoted':False})
        signature=str(candidate.get('content_signature') or '')
        if signature and signature not in state['uses']:
            state['uses'].append(signature);del state['uses'][:-64]
        state['support']=len(set(state.get('uses') or []));was=bool(state.get('promoted'))
        state['promoted']=state['support']>=2
        if state['promoted'] and not was:
            event={'event':'document_dependency_reference_gate_promoted','gate_id':gate_id,
                   'predicate':state['predicate'],'slot':state['slot'],
                   'link_predicate':link_predicate,'support':state['support'],
                   'mechanism':'generated_document_dependency_gate_v534'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_dependency_reference_gate_promoted',**event})
        # Mirror causal evidence for V5.33 backward compatibility.
        if link_predicate=='_doc_causes':
            legacy={'causal_id':candidate.get('dependency_id'),
                    'content_signature':candidate.get('content_signature')}
            self._record_document_causal_reference_use(legacy,predicate,slot)
        return state

    def _materialize_document_dependency(self, candidate: dict) -> dict:
        did=candidate['dependency_id'];kind=candidate['link_predicate']
        source=f'document_dependency_v534:{did}'
        fact_ids=[self.kb.add(Atom('_dependency_kind',(did,kind)),source),
                  self.kb.add(Atom('_dependency_from',(did,str(candidate['from_fact_id']))),source),
                  self.kb.add(Atom('_dependency_to',(did,str(candidate['to_fact_id']))),source)]
        event={'event':'document_dependency_materialized','dependency_id':did,
               'link_predicate':kind,'representation_type':candidate.get('representation_type'),
               'from_fact_id':candidate['from_fact_id'],'to_fact_id':candidate['to_fact_id'],
               'representation_fact_ids':fact_ids,
               'mechanism':'generated_explicit_document_dependency_v534'}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:
            self.kb.audit.append(event)
        return event

    @staticmethod
    def _document_causal_gate_key(predicate: str, slot: int) -> tuple[str,str]:
        payload=json.dumps([predicate.lstrip('!'),int(slot),'causal_dependency'],
                           ensure_ascii=False,separators=(',',':'))
        gate_id='causal_gate_'+hashlib.blake2b(payload.encode('utf8'),digest_size=8).hexdigest()
        return payload,gate_id

    def _document_causal_candidates(self, document_facts: list[dict]) -> list[dict]:
        """Return explicit causal-dependency candidates already licensed by text.

        V5.33 does not infer causality from adjacency.  A candidate exists only
        when V5.24 previously stored ``_doc_causes(from_fact,to_fact)`` from an
        explicit ``por eso`` connective and both endpoint facts belong to the
        current document context.  The candidate is still latent until consumed
        by a demonstrative reference.
        """
        ids={str(row.get('id')) for row in document_facts if row.get('id')}
        if len(ids)<2:
            return []
        out=[];seen=set()
        for link in self.kb.matches(Atom('_doc_causes',('?from','?to'))):
            a,b=link['atom'].args
            if a not in ids or b not in ids:
                continue
            first=self.kb.get_fact(a); second=self.kb.get_fact(b)
            if first is None or second is None:
                continue
            content={'from':first['atom'].as_dict(),'to':second['atom'].as_dict()}
            signature=json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
            if signature in seen:
                continue
            seen.add(signature)
            digest=hashlib.blake2b(signature.encode('utf8'),digest_size=10).hexdigest()
            out.append({'causal_id':'causal_'+digest,'from_fact_id':a,'to_fact_id':b,
                        'member_fact_ids':[a,b],'content_signature':signature,
                        'link_fact_id':link.get('id'),'mechanism':'latent_document_causal_v533'})
        return out

    def _document_causal_reference_support(self, predicate: str, slot: int) -> int:
        key,_=self._document_causal_gate_key(predicate,slot)
        state=self.document_causal_reference_hypotheses.get(key) or {}
        return int(state.get('support') or 0)

    def _record_document_causal_reference_use(self, candidate: dict, predicate: str, slot: int) -> dict:
        """Credit one independently evidenced use of a causal representation."""
        key,gate_id=self._document_causal_gate_key(predicate,slot)
        state=self.document_causal_reference_hypotheses.setdefault(key,{
            'gate_id':gate_id,'predicate':predicate.lstrip('!'),'slot':int(slot),
            'representation_type':'causal_dependency','uses':[],'support':0,'promoted':False})
        signature=str(candidate.get('content_signature') or '')
        if signature and signature not in state['uses']:
            state['uses'].append(signature);del state['uses'][:-64]
        state['support']=len(set(state.get('uses') or []))
        was=bool(state.get('promoted')); state['promoted']=state['support']>=2
        if state['promoted'] and not was:
            event={'event':'document_causal_reference_gate_promoted','gate_id':gate_id,
                   'predicate':state['predicate'],'slot':state['slot'],'support':state['support'],
                   'mechanism':'explicit_causal_use_gate_v533'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            self.training_reports.append({'type':'document_causal_reference_gate_promoted',**event})
        return state

    def _select_document_representation_types(self, event_candidates: list[dict],
                                              dependency_candidates: list[dict],
                                              predicate: str, slot: int,
                                              state_candidates: list[dict] | None = None) -> tuple[list[dict],dict]:
        """Compete event scopes with generated explicit dependency types.

        V5.34 scores each distinct ``_doc_*`` dependency kind independently. A
        dependency with no prior predictive evidence may bootstrap only when no
        event/other dependency representation competes. Once several licensed
        types exist, a two-support margin is required; otherwise Leobot abstains.
        """
        state_candidates=list(state_candidates or [])
        if state_candidates:
            # V5.36: a newly invented persistent-state type must compete on the
            # same predictive currency as events/dependencies.  Structural state
            # promotion licenses a unique bootstrap only when no other type is
            # available.  In actual competition the state needs at least two
            # prior, content-distinct downstream uses.
            state_rows=[(self._document_state_reference_support(st,predicate,slot),st)
                        for st in state_candidates]
            if not event_candidates and not dependency_candidates:
                if len(state_candidates)==1:
                    only=state_candidates[0];support=state_rows[0][0]
                    # Exact V5.35 states may bootstrap from their own promoted
                    # schema.  A V5.37 meta transfer must additionally have the
                    # independently learned consumer gate; otherwise topology
                    # alone would be allowed to invent downstream meaning.
                    if only.get('mechanism')!='latent_document_state_meta_v537' or support>=2:
                        return state_candidates,{'status':'state_only','support':support}
                    return state_candidates,{'status':'representation_type_ambiguous',
                                             'state_candidates':1,'reason':'meta_state_consumer_unlicensed'}
                licensed=[(n,st) for n,st in state_rows if n>=2]
                licensed.sort(key=lambda x:(-x[0],str(x[1].get('state_id'))))
                if len(licensed)>=1 and (len(licensed)==1 or licensed[0][0]>=licensed[1][0]+2):
                    chosen=dict(licensed[0][1])
                    chosen['type_selection']={'mechanism':'latent_representation_type_competition_v536',
                                              'decision':'state','support':licensed[0][0],
                                              'runner_up_support':licensed[1][0] if len(licensed)>1 else 0}
                    return [chosen],{'status':'representation_type_selected','decision':'state',
                                     'support':licensed[0][0]}
                return state_candidates,{'status':'representation_type_ambiguous',
                                         'state_candidates':len(state_candidates)}

            rows=[]
            for event in event_candidates:
                rows.append((self._document_event_scope_support(event,predicate,slot),'event',event))
            for dep in dependency_candidates:
                support=self._document_dependency_reference_support(predicate,slot,dep.get('link_predicate',''))
                if support>=2:
                    rows.append((support,dep.get('representation_type') or 'document_dependency',dep))
            for support,st in state_rows:
                if support>=2:
                    rows.append((support,'latent_persistent_state',st))
            # If the new state has not yet earned predictive support, preserve the
            # exact V5.34 decision among pre-existing representation types.
            if not any(kind=='latent_persistent_state' for _,kind,_ in rows):
                return self._select_document_representation_types(event_candidates,dependency_candidates,predicate,slot,[])
            rows.sort(key=lambda x:(-x[0],x[1],str(x[2].get('event_id') or x[2].get('dependency_id') or x[2].get('state_id'))))
            if len(rows)==1:
                chosen=dict(rows[0][2]);chosen['type_selection']={
                    'mechanism':'latent_representation_type_competition_v536','decision':rows[0][1],
                    'support':rows[0][0],'runner_up_support':0,'candidates':[]}
                return [chosen],{'status':'single_representation_type','support':rows[0][0]}
            top,runner=rows[0],rows[1]
            detail=[{'representation_type':kind,'support':support,
                     'id':obj.get('event_id') or obj.get('dependency_id') or obj.get('state_id'),
                     'members':list(obj.get('member_fact_ids') or [])}
                    for support,kind,obj in rows]
            if top[0]>=runner[0]+2:
                chosen=dict(top[2]);meta={'mechanism':'latent_representation_type_competition_v536',
                                          'decision':top[1],'support':top[0],
                                          'runner_up_support':runner[0],'candidates':detail}
                chosen['type_selection']=meta
                audit={'event':'document_representation_type_selected','predicate':predicate,
                       'slot':int(slot),**meta}
                if hasattr(self.kb,'audit') and audit not in self.kb.audit:
                    self.kb.audit.append(audit)
                return [chosen],{'status':'representation_type_selected',**audit}
            competing=[]
            for support,kind,obj in rows:
                copy=dict(obj);copy['type_selection']={
                    'mechanism':'latent_representation_type_competition_v536',
                    'decision':'abstain','support':support,'candidates':detail}
                competing.append(copy)
            return competing,{'status':'representation_type_ambiguous','candidates':detail}

        if not dependency_candidates:
            return event_candidates,{'status':'event_only'}
        # Build dependency rows with prior support. Under-supported kinds remain
        # usable only when they are the sole structural representation.
        dep_rows=[]
        for dep in dependency_candidates:
            support=self._document_dependency_reference_support(
                predicate,slot,dep.get('link_predicate',''))
            dep_rows.append((support,dep))
        if not event_candidates:
            if len(dependency_candidates)==1:
                return dependency_candidates,{'status':'dependency_only','support':dep_rows[0][0]}
            licensed=[(n,d) for n,d in dep_rows if n>=2]
            if len(licensed)==1:
                return [licensed[0][1]],{'status':'dependency_selected','support':licensed[0][0]}
            return dependency_candidates,{'status':'representation_type_ambiguous',
                                          'dependency_candidates':len(dependency_candidates)}
        licensed=[(n,d) for n,d in dep_rows if n>=2]
        if not licensed:
            return event_candidates,{'status':'dependencies_under_supported'}
        # Scope competition already handled event-internal alternatives. Preserve
        # them as separate type hypotheses if more than one survives.
        rows=[]
        for event in event_candidates:
            rows.append((self._document_event_scope_support(event,predicate,slot),'event',event))
        for support,dep in licensed:
            rows.append((support,dep.get('representation_type') or 'document_dependency',dep))
        rows.sort(key=lambda x:(-x[0],x[1],
                                str(x[2].get('event_id') or x[2].get('dependency_id'))))
        if len(rows)<2:
            return [rows[0][2]],{'status':'single_representation_type','support':rows[0][0]}
        top,runner=rows[0],rows[1]
        detail=[{'representation_type':kind,'support':support,
                 'id':obj.get('event_id') or obj.get('dependency_id'),
                 'members':list(obj.get('member_fact_ids') or [])}
                for support,kind,obj in rows]
        if top[0]>=runner[0]+2:
            chosen=dict(top[2]);meta={'mechanism':'generated_representation_type_competition_v534',
                                      'decision':top[1],'support':top[0],
                                      'runner_up_support':runner[0],'candidates':detail}
            chosen['type_selection']=meta
            audit={'event':'document_representation_type_selected','predicate':predicate,
                   'slot':int(slot),**meta}
            if hasattr(self.kb,'audit') and audit not in self.kb.audit:
                self.kb.audit.append(audit)
            return [chosen],{'status':'representation_type_selected',**audit}
        competing=[]
        for support,kind,obj in rows:
            copy=dict(obj);copy['type_selection']={
                'mechanism':'generated_representation_type_competition_v534',
                'decision':'abstain','support':support,'candidates':detail}
            competing.append(copy)
        return competing,{'status':'representation_type_ambiguous','candidates':detail}

    def _materialize_document_causal(self, candidate: dict) -> dict:
        """Persist one selected explicit-causal dependency as its own node type."""
        cid=candidate['causal_id']; source=f'document_causal_v533:{cid}'
        fact_ids=[self.kb.add(Atom('_causal_from',(cid,str(candidate['from_fact_id']))),source),
                  self.kb.add(Atom('_causal_to',(cid,str(candidate['to_fact_id']))),source)]
        event={'event':'document_causal_materialized','causal_id':cid,
               'from_fact_id':candidate['from_fact_id'],'to_fact_id':candidate['to_fact_id'],
               'representation_fact_ids':fact_ids,'mechanism':'demand_driven_explicit_causal_v533'}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:
            self.kb.audit.append(event)
        return event

    def _materialize_document_event(self, candidate: dict) -> dict:
        """Persist one uniquely selected latent event and its auditable structure."""
        event_id=candidate['event_id']; schema_id=candidate['schema_id']
        if candidate.get('mechanism')=='latent_document_event_meta_v527':
            version='v527'
        elif candidate.get('mechanism')=='latent_document_event_v526':
            version='v526'
        else:
            version='v525'
        source=f'document_event_{version}:{event_id}'
        fact_ids=[]
        fact_ids.append(self.kb.add(Atom('_event_schema',(event_id,schema_id)),source))
        for fid in candidate.get('member_fact_ids',[]):
            fact_ids.append(self.kb.add(Atom('_event_member',(event_id,str(fid))),source))
        for index,value in enumerate(candidate.get('bindings',[])):
            fact_ids.append(self.kb.add(Atom('_event_role',(event_id,f'r{index}',str(value))),source))
        mechanism=('demand_driven_event_meta_transfer_v527' if version=='v527' else
                   ('demand_driven_latent_event_v526' if version=='v526' else 'demand_driven_latent_event_v525'))
        event={'event':'document_event_materialized','event_id':event_id,'schema_id':schema_id,
               'member_fact_ids':candidate.get('member_fact_ids',[]),'bindings':candidate.get('bindings',[]),
               'sentence_span':candidate.get('sentence_span',[]),'support':candidate.get('support',0),
               'representation_fact_ids':fact_ids,'mechanism':mechanism}
        if hasattr(self.kb,'audit') and event not in self.kb.audit:
            self.kb.audit.append(event)
        # Only exact schemas can teach the V5.27 meta representation.  Meta-used
        # events are downstream transfer evidence and never bootstrap themselves.
        if version in ('v525','v526'):
            for state in self.document_event_schema_hypotheses.values():
                if state.get('schema_id')!=schema_id:
                    continue
                uses=state.setdefault('representation_uses',[])
                if event_id not in uses:
                    uses.append(event_id);del uses[:-32]
                self._refresh_document_event_meta(state.get('structure') or {})
                break
        return event

    def _resolve_document_coreference(self, frame: dict, document_facts: list[dict]) -> dict:
        """Resolve a bounded document reference from same-role discourse evidence.

        V5.21 intentionally does *not* choose the most recent entity.  For each
        anaphoric argument, a candidate must already have occupied the same
        predicate/argument role in an earlier fact from this document.  One
        distinct candidate licenses resolution; zero means unresolved and two or
        more means genuine ambiguity.  This is narrow but auditable and prevents
        reference words from silently becoming entities or raw-learning support.
        """
        args=list(frame.get('args') or [])
        positions=self._document_reference_positions(args)
        if not positions:
            return {'status':'document_coreference_none','frame':frame}
        pred=frame.get('pred')
        if not isinstance(pred,str) or not pred:
            return {'status':'document_coreference_unresolved','reason':'missing_predicate'}
        base=pred.lstrip('!'); references=[]; resolved=list(args)
        for slot in positions:
            candidates={}
            representation_alternative=None
            for row in document_facts:
                atom=row.get('atom')
                if atom is None or atom.pred.lstrip('!') != base or len(atom.args) != len(args):
                    continue
                value=atom.args[slot]
                if normalize(value) in self._DOCUMENT_REFERENCE_MARKERS:
                    continue
                candidates.setdefault(value,[]).append({'fact_id':row.get('id'),
                                                        'criterion':'same_predicate_same_role',
                                                        'role':[base,slot]})
            for value,evidence in self._document_bridge_candidates(pred,slot,document_facts).items():
                for item in evidence:
                    candidates.setdefault(value,[]).append({'criterion':'learned_role_bridge_v522',**item})
            marker=normalize(str(args[slot]))
            # V5.25: demonstratives may refer to a structurally induced event, but
            # only when a promoted schema yields a unique latent candidate.  The
            # candidate stays hypothetical until the whole assertion is accepted;
            # personal pronouns never enter this branch.
            if marker in {'eso','esto','aquello'}:
                raw_event_candidates=self._document_event_candidates(document_facts,maximal=False)
                selected_event_candidates,scope_selection=self._select_document_event_scopes(
                    raw_event_candidates,pred,slot)
                dependency_candidates=self._document_dependency_candidates(document_facts)
                state_candidates=self._document_state_candidates(document_facts)
                selected_representations,type_selection=self._select_document_representation_types(
                    selected_event_candidates,dependency_candidates,pred,slot,state_candidates)
                # V5.38 is a conservative gap-filler, not a universal rival to
                # already licensed semantic representations.  Only when the
                # established event/state/dependency generators yield nothing may
                # a cross-type learned strategy propose a type-agnostic bundle.
                generic_bundle_candidates=[]
                if not selected_representations:
                    occupied=set()
                    for rep in list(raw_event_candidates)+list(dependency_candidates)+list(state_candidates):
                        mids=tuple(sorted(str(x) for x in (rep.get('member_fact_ids') or []) if x))
                        if mids:occupied.add(mids)
                    generic_bundle_candidates=self._document_latent_bundle_candidates(
                        document_facts,pred,slot,occupied)
                for representation in selected_representations:
                    if representation.get('mechanism') in {'latent_document_state_v535','latent_document_state_meta_v537'}:
                        state_criterion=representation.get('mechanism')
                        candidates.setdefault(representation['state_id'],[]).append({
                            'criterion':state_criterion,'state_candidate':representation,
                            'fact_id':representation.get('member_fact_ids',[])[-1]
                                      if representation.get('member_fact_ids') else None,
                            'schema_id':representation.get('schema_id'),
                            'support':self._document_state_reference_support(representation,pred,slot),
                            'type_selection':representation.get('type_selection') or type_selection})
                        continue
                    if representation.get('mechanism')=='latent_document_dependency_v534':
                        link_pred=representation.get('link_predicate')
                        criterion=('latent_document_causal_v533' if link_pred=='_doc_causes'
                                   else 'latent_document_dependency_v534')
                        candidates.setdefault(representation['dependency_id'],[]).append({
                            'criterion':criterion,'dependency_candidate':representation,
                            'causal_candidate':representation if link_pred=='_doc_causes' else None,
                            'fact_id':representation.get('to_fact_id'),
                            'support':self._document_dependency_reference_support(pred,slot,link_pred),
                            'type_selection':representation.get('type_selection') or type_selection})
                        continue
                    event_candidate=representation
                    candidates.setdefault(event_candidate['event_id'],[]).append({
                        'criterion':event_candidate.get('mechanism','latent_document_event_v525'),
                        'event_candidate':event_candidate,
                        'fact_id':event_candidate.get('member_fact_ids',[])[-1]
                                  if event_candidate.get('member_fact_ids') else None,
                        'schema_id':event_candidate.get('schema_id'),
                        'support':event_candidate.get('support',0),
                        'scope_selection':event_candidate.get('scope_selection') or scope_selection,
                        'type_selection':event_candidate.get('type_selection') or type_selection})
                for bundle in generic_bundle_candidates:
                    candidates.setdefault(bundle['bundle_id'],[]).append({
                        'criterion':'latent_document_bundle_meta_v538',
                        'bundle_candidate':bundle,
                        'fact_id':bundle.get('member_fact_ids',[])[-1] if bundle.get('member_fact_ids') else None,
                        'support':bundle.get('support',0),
                        'strategy_id':bundle.get('strategy_id')})
            # V5.31: when one ordinary entity and one meta-event compete for
            # the same demonstrative slot, consult the independently scored
            # representation hypothesis instead of treating structural transfer as
            # automatically authoritative. Exact event schemas keep their prior
            # behavior because they are not meta-transfer.
            if marker in {'eso','esto','aquello'} and candidates and not any(
                    any(x.get('dependency_candidate') or x.get('causal_candidate') for x in evidence)
                        for evidence in candidates.values()):
                event_keys=[]; entity_keys=[]; event_candidate_by_key={}
                for value,evidence in candidates.items():
                    meta=[x.get('event_candidate') for x in evidence
                          if (x.get('event_candidate') or {}).get('mechanism')=='latent_document_event_meta_v527']
                    if meta:
                        event_keys.append(value);event_candidate_by_key[value]=meta[0]
                    else:
                        entity_keys.append(value)
                if len(event_keys)==1:
                    event_key=event_keys[0]; event_candidate=event_candidate_by_key[event_key]
                    decision=self._document_event_representation_decision(event_candidate,pred,slot)
                    if decision=='event' and len(entity_keys)==1:
                        entity_key=entity_keys[0]
                        representation_alternative={'decision':'event','entity_candidate':entity_key,
                                                    'event_candidate':event_candidate}
                        candidates={event_key:candidates[event_key]}
                    elif decision=='independent' and len(entity_keys)==1:
                        entity_key=entity_keys[0]
                        representation_alternative={'decision':'independent','entity_candidate':entity_key,
                                                    'event_candidate':event_candidate}
                        candidates={entity_key:candidates[entity_key]}
                    elif decision!='event' and not entity_keys:
                        return {'status':'document_coreference_unresolved','predicate':pred,
                                'slot':slot,'marker':marker,'candidates':[],
                                'representation_decision':decision,
                                'event_candidate':event_candidate}
                    elif decision=='abstain' and entity_keys:
                        # Keep both hypotheses visible so callers can retain the
                        # ambiguity and await later independent evidence.
                        pass
            if not candidates:
                return {'status':'document_coreference_unresolved','predicate':pred,
                        'slot':slot,'marker':marker,'candidates':[]}
            if len(candidates) != 1:
                return {'status':'document_coreference_ambiguous','predicate':pred,
                        'slot':slot,'marker':marker,'candidates':sorted(candidates),
                        'candidate_evidence':{k:v for k,v in sorted(candidates.items())}}
            antecedent=next(iter(candidates)); evidence=candidates[antecedent]
            resolved[slot]=antecedent
            criteria=sorted({x.get('criterion') for x in evidence if x.get('criterion')})
            ref_row={'slot':slot,'marker':marker,'antecedent':antecedent,
                     'antecedent_fact_ids':sorted({x.get('fact_id') for x in evidence if x.get('fact_id')}),
                     'criteria':criteria,'evidence':evidence}
            if representation_alternative is not None:
                ref_row['representation_alternative']=representation_alternative
            references.append(ref_row)
        out=dict(frame); out['args']=resolved
        return {'status':'document_coreference_resolved','frame':out,'predicate':pred,
                'args':resolved,'references':references}

    def ingest_document_text(self, text: str, source: str = 'documento',
                             max_sentences: int = 5000,
                             learn_conditionals: bool = False) -> dict:
        """Acquire declarative relational knowledge from bounded continuous text.

        Document content is treated strictly as data.  We do **not** route it
        through ``respond``: quoted paraphrase instructions cannot teach grammar,
        questions are not executed, and conditionals are not promoted on this
        first safe document path.  Grounded assertions are stored directly;
        otherwise the existing raw positive/negative relation learners may use
        repeated declarative sentences as evidence.  Every stored fact keeps a
        per-sentence source string.
        """
        sentences=self._document_sentences(text,max_sentences=max_sentences)
        before=self.kb.stats()['facts']; language_before=len(self.language.examples)
        results=[]; promoted=set(); skipped_questions=0; skipped_conditionals=0
        processed_conditionals=0; learned_rules=set()
        stored_direct=0; stored_schema=0; too_long=0
        coref_resolved=0; coref_ambiguous=0; coref_unresolved=0
        document_links_stored=0; document_links_unresolved=0
        document_events_materialized=0
        document_causal_dependencies_materialized=0
        document_dependencies_materialized=0
        document_states_materialized=0
        document_latent_bundles_materialized=0
        document_facts=[]; document_fact_ids=set()
        pending_event_choices=[]
        pending_latent_bundle_choices=[]
        # Content-derived episode identity prevents the same document from
        # manufacturing independent bridge support merely by changing ``source``.
        document_episode_id=hashlib.blake2b(('\n'.join(sentences)).encode('utf8'),digest_size=12).hexdigest()

        def confirm_pending_event_choices(fact):
            if not fact:
                return
            for pending in list(pending_event_choices):
                outcome=self._record_document_event_independent_confirmation(
                    pending,fact,document_episode_id,source)
                if outcome is not None:
                    pending_event_choices.remove(pending)
                    retracted=outcome.get('retracted_fact_id')
                    if retracted:
                        document_facts[:]=[row for row in document_facts if row.get('id')!=retracted]
                        document_fact_ids.discard(retracted)
            for pending in list(pending_latent_bundle_choices):
                outcome=self._record_document_latent_bundle_confirmation(
                    pending,fact,document_episode_id,source)
                if outcome is not None:
                    pending_latent_bundle_choices.remove(pending)
                    retracted=outcome.get('retracted_fact_id')
                    if retracted:
                        document_facts[:]=[row for row in document_facts if row.get('id')!=retracted]
                        document_fact_ids.discard(retracted)

        def remember_document_facts(ids):
            for fid in ids or []:
                if not fid or fid in document_fact_ids:
                    continue
                fact=self.kb.get_fact(fid) if hasattr(self.kb,'get_fact') else None
                if fact is None or not str(fact.get('source','')).startswith(f'{source}:oración:'):
                    continue
                document_fact_ids.add(fid)
                self._observe_document_role_bridges(fact,document_facts,document_episode_id,source)
                self._observe_document_event_schema(fact,document_facts,document_episode_id,source)
                self._observe_document_state_schema(fact,document_facts,document_episode_id,source)
                document_facts.append(fact)
                confirm_pending_event_choices(fact)

        def store_resolved(frame, sentence, sentence_source, resolution):
            nonlocal document_events_materialized, document_causal_dependencies_materialized, document_dependencies_materialized, document_states_materialized, document_latent_bundles_materialized
            pred=frame['pred']; args=tuple(frame['args'])
            mechanisms=sorted({c for r in resolution['references'] for c in r.get('criteria',[])})
            suffix='document_coreference_v522' if 'learned_role_bridge_v522' in mechanisms else 'document_coreference_v521'
            event_mechanisms={'latent_document_event_v525','latent_document_event_v526','latent_document_event_meta_v527'} & set(mechanisms)
            dependency_mechanisms={'latent_document_causal_v533','latent_document_dependency_v534'} & set(mechanisms)
            causal_mechanisms={'latent_document_causal_v533'} & set(mechanisms)
            state_mechanisms={'latent_document_state_v535','latent_document_state_meta_v537'} & set(mechanisms)
            bundle_mechanisms={'latent_document_bundle_meta_v538'} & set(mechanisms)
            materialized_dependencies=[];materialized_causal=[]
            materialized_states=[]
            materialized_bundles=[]
            if dependency_mechanisms:
                suffix=('document_coreference_causal_v533' if causal_mechanisms and len(dependency_mechanisms)==1
                        else 'document_coreference_dependency_v534')
                seen_dependencies=set()
                for ref in resolution.get('references',[]):
                    for evidence in ref.get('evidence',[]):
                        candidate=evidence.get('dependency_candidate')
                        if not candidate:
                            continue
                        did=candidate.get('dependency_id')
                        if not did or did in seen_dependencies:
                            continue
                        seen_dependencies.add(did)
                        materialized_dependency=self._materialize_document_dependency(candidate)
                        gate=self._record_document_dependency_reference_use(candidate,pred,ref.get('slot',0))
                        materialized_dependency['reference_gate_id']=gate.get('gate_id')
                        materialized_dependency['reference_gate_promoted']=bool(gate.get('promoted'))
                        materialized_dependencies.append(materialized_dependency)
                        if candidate.get('link_predicate')=='_doc_causes':
                            # Preserve the V5.33 observable representation facts as
                            # a compatibility view while V5.34 uses the generic node.
                            legacy={'causal_id':did,'from_fact_id':candidate['from_fact_id'],
                                    'to_fact_id':candidate['to_fact_id']}
                            causal_view=self._materialize_document_causal(legacy)
                            materialized_causal.append(causal_view)
                document_dependencies_materialized+=len(materialized_dependencies)
                document_causal_dependencies_materialized+=len(materialized_causal)
            if state_mechanisms:
                suffix=('document_coreference_state_meta_v537' if 'latent_document_state_meta_v537' in state_mechanisms
                        else 'document_coreference_state_v535')
                seen_states=set()
                for ref in resolution.get('references',[]):
                    for evidence in ref.get('evidence',[]):
                        candidate=evidence.get('state_candidate')
                        if not candidate or candidate.get('state_id') in seen_states:
                            continue
                        seen_states.add(candidate['state_id'])
                        materialized_state=self._materialize_document_state(candidate)
                        gate=self._record_document_state_reference_use(candidate,pred,ref.get('slot',0))
                        materialized_state['reference_gate_id']=gate.get('gate_id')
                        materialized_state['reference_gate_promoted']=bool(gate.get('promoted'))
                        materialized_states.append(materialized_state)
                document_states_materialized+=len(materialized_states)
            if event_mechanisms:
                # Keep ``document_coreference_`` in the provenance token so all
                # existing anti-circular evidence filters continue to exclude a
                # fact whose referent was supplied by the resolver itself.
                if 'latent_document_event_meta_v527' in event_mechanisms:
                    suffix='document_coreference_event_meta_v527'
                elif 'latent_document_event_v526' in event_mechanisms:
                    suffix='document_coreference_event_v526'
                else:
                    suffix='document_coreference_event_v525'
                materialized=[]; seen=set()
                for ref in resolution.get('references',[]):
                    for evidence in ref.get('evidence',[]):
                        candidate=evidence.get('event_candidate')
                        if not candidate or candidate.get('event_id') in seen:
                            continue
                        seen.add(candidate['event_id'])
                        materialized_event=self._materialize_document_event(candidate)
                        gate=self._record_document_event_reference_use(candidate,pred,ref.get('slot',0))
                        if gate is not None:
                            materialized_event['reference_gate_id']=gate.get('gate_id')
                            materialized_event['reference_gate_promoted']=bool(gate.get('promoted'))
                        materialized.append(materialized_event)
                document_events_materialized+=len(materialized)
            if bundle_mechanisms:
                suffix='document_coreference_latent_bundle_v538'
                seen_bundles=set()
                for ref in resolution.get('references',[]):
                    for evidence in ref.get('evidence',[]):
                        candidate=evidence.get('bundle_candidate')
                        if not candidate or candidate.get('bundle_id') in seen_bundles:
                            continue
                        seen_bundles.add(candidate['bundle_id'])
                        materialized_bundles.append(self._materialize_document_latent_bundle(candidate))
                document_latent_bundles_materialized+=len(materialized_bundles)
            provenance=f'{sentence_source}:{suffix}'
            fid=self.kb.add(Atom(pred,args),provenance)
            remember_document_facts([fid])
            event={'event':'document_coreference_resolved','fact_id':fid,'text':sentence,
                   'normalized_text':normalize(sentence),'predicate':pred,
                   'resolved_args':list(args),'references':resolution['references'],
                   'source':sentence_source,'mechanism':'+'.join(mechanisms) or suffix}
            if event_mechanisms:
                event['materialized_events']=materialized
            if dependency_mechanisms:
                event['materialized_document_dependencies']=materialized_dependencies
            if causal_mechanisms:
                event['materialized_causal_dependencies']=materialized_causal
            if state_mechanisms:
                event['materialized_states']=materialized_states
            if bundle_mechanisms:
                event['materialized_latent_bundles']=materialized_bundles
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            return fid,event

        def prior_sentence_fact_ids(sentence_index):
            if sentence_index < 1:
                return []
            prefix=f'{source}:oración:{sentence_index}'
            return [row.get('id') for row in document_facts
                    if row.get('id') and str(row.get('source','')).startswith(prefix)]

        def attach_document_link(row, fid, relation, prior_ids, sentence_source):
            nonlocal document_links_stored, document_links_unresolved
            if relation is None:
                return row
            unique=sorted(set(x for x in prior_ids if x))
            if not unique:
                m=re.search(r':oración:(\d+)$',sentence_source)
                if m:
                    unique=sorted(set(prior_sentence_fact_ids(int(m.group(1))-1)))
            if not fid or len(unique)!=1:
                document_links_unresolved+=1
                row['discourse_link']={'status':'document_discourse_unresolved',
                                       'relation':relation,'antecedent_candidates':unique}
                return row
            previous=unique[0]
            pred='_doc_precedes' if relation=='after' else '_doc_causes'
            source_link=f'{sentence_source}:document_discourse_v524'
            link_id=self.kb.add(Atom(pred,(previous,fid)),source_link)
            document_links_stored+=1
            link={'status':'document_discourse_link_stored','relation':relation,
                  'predicate':pred,'from_fact':previous,'to_fact':fid,'id':link_id}
            row['discourse_link']=link
            event={'event':'document_discourse_link_stored',**link,'source':sentence_source,
                   'mechanism':'explicit_discourse_connective_v524'}
            if hasattr(self.kb,'audit') and event not in self.kb.audit:
                self.kb.audit.append(event)
            return row

        def remember_selected_event_choice(frame, resolution, sentence_index, fact_id):
            for ref in resolution.get('references') or []:
                alt=ref.get('representation_alternative') or {}
                if alt.get('decision')!='event':
                    continue
                candidate=alt.get('event_candidate') or {}
                if candidate.get('mechanism')!='latent_document_event_meta_v527':
                    continue
                slot=int(ref.get('slot',-1))
                if not 0<=slot<len(frame.get('args') or []):
                    continue
                row={'sentence_index':sentence_index,'predicate':frame.get('pred'),'slot':slot,
                     'args':list(frame.get('args') or []),'entity_candidate':alt.get('entity_candidate'),
                     'event_id':ref.get('antecedent'),'structure':candidate.get('structure') or {},
                     'schema_id':candidate.get('schema_id'),'resolved_fact_id':fact_id}
                signature=json.dumps({k:row[k] for k in ('sentence_index','predicate','slot','args','entity_candidate','event_id')},
                                     sort_keys=True,ensure_ascii=False,separators=(',',':'))
                if not any(x.get('_signature')==signature for x in pending_event_choices):
                    row['_signature']=signature;pending_event_choices.append(row)

        def remember_selected_latent_bundle(frame, resolution, sentence_index, fact_id):
            for ref in resolution.get('references') or []:
                candidates=[e.get('bundle_candidate') for e in ref.get('evidence',[]) if e.get('bundle_candidate')]
                if len(candidates)!=1:
                    continue
                candidate=candidates[0];slot=int(ref.get('slot',-1))
                if not 0<=slot<len(frame.get('args') or []):
                    continue
                row={'sentence_index':sentence_index,'predicate':frame.get('pred'),'slot':slot,
                     'args':list(resolution.get('args') or []),'bundle_id':ref.get('antecedent'),
                     'strategy_id':candidate.get('strategy_id'),'resolved_fact_id':fact_id}
                signature=json.dumps({k:row[k] for k in ('sentence_index','predicate','slot','args','bundle_id','strategy_id')},
                                     sort_keys=True,ensure_ascii=False,separators=(',',':'))
                if not any(x.get('_signature')==signature for x in pending_latent_bundle_choices):
                    row['_signature']=signature;pending_latent_bundle_choices.append(row)

        def remember_ambiguous_event_choice(frame, resolution, sentence_index):
            if resolution.get('status')!='document_coreference_ambiguous':
                return
            slot=int(resolution.get('slot',-1)); marker=resolution.get('marker')
            if marker not in {'eso','esto','aquello'} or not 0<=slot<len(frame.get('args') or []):
                return
            evidence=resolution.get('candidate_evidence') or {}
            meta=[]; entities=[]
            for value,rows in evidence.items():
                found=[r.get('event_candidate') for r in rows
                       if (r.get('event_candidate') or {}).get('mechanism')=='latent_document_event_meta_v527']
                if found:
                    meta.append((value,found[0]))
                else:
                    entities.append(value)
            if len(meta)!=1 or len(entities)!=1:
                return
            value,candidate=meta[0]
            decision=self._document_event_representation_decision(candidate,frame.get('pred'),slot)
            if decision!='abstain':
                return
            row={'sentence_index':sentence_index,'predicate':frame.get('pred'),'slot':slot,
                 'args':list(frame.get('args') or []),'entity_candidate':entities[0],
                 'event_id':value,'structure':candidate.get('structure') or {},
                 'schema_id':candidate.get('schema_id')}
            signature=json.dumps({k:row[k] for k in ('sentence_index','predicate','slot','args','entity_candidate','event_id')},
                                 sort_keys=True,ensure_ascii=False,separators=(',',':'))
            if not any(x.get('_signature')==signature for x in pending_event_choices):
                row['_signature']=signature;pending_event_choices.append(row)

        for i,sentence in enumerate(sentences,1):
            sentence_source=f'{source}:oración:{i}'
            discourse_relation,semantic_sentence=self._document_discourse_prefix(sentence)
            prior_fact_ids=prior_sentence_fact_ids(i-1) if discourse_relation else []
            if len(sentence)>2048:
                too_long+=1; results.append({'index':i,'status':'document_sentence_too_long'}); continue
            norm=normalize(semantic_sentence)
            if self._question_like(semantic_sentence):
                skipped_questions+=1; results.append({'index':i,'status':'document_question_skipped'}); continue
            if norm.startswith('si ') and ' entonces ' in norm:
                if not learn_conditionals:
                    skipped_conditionals+=1; results.append({'index':i,'status':'document_conditional_skipped'}); continue
                conditional=self.observe_conditional_rule(semantic_sentence,source=sentence_source)
                processed_conditionals+=1
                row={'index':i,**(conditional or {'status':'document_conditional_unresolved'})}
                results.append(row)
                rid=row.get('rule_id') or ((row.get('rule') or {}).get('rule_id') if isinstance(row.get('rule'),dict) else None)
                if rid and row.get('status') in ('conditional_rule_learned','conditional_rule_confirmed','conditional_bootstrap_learned'):
                    learned_rules.add(rid)
                continue

            parsed=self._semantic_parse(semantic_sentence)
            if parsed.get('status')=='parsed' and (parsed.get('frame') or {}).get('act')=='assert':
                frame=parsed['frame']; resolution=self._resolve_document_coreference(frame,document_facts)
                if resolution.get('status')=='document_coreference_resolved':
                    fid,event=store_resolved(resolution['frame'],sentence,sentence_source,resolution)
                    remember_selected_event_choice(frame,resolution,i,fid)
                    remember_selected_latent_bundle(frame,resolution,i,fid)
                    stored_direct+=1; coref_resolved+=1
                    row={'index':i,'status':'document_coreference_resolved','id':fid,
                         'predicate':resolution['predicate'],'args':resolution['args'],
                         'references':resolution['references'],'provenance':event}
                    results.append(attach_document_link(row,fid,discourse_relation,prior_fact_ids,sentence_source))
                    continue
                if resolution.get('status')=='document_coreference_ambiguous':
                    remember_ambiguous_event_choice(frame,resolution,i)
                    coref_ambiguous+=1; results.append({'index':i,**resolution}); continue
                if resolution.get('status')=='document_coreference_unresolved':
                    coref_unresolved+=1; results.append({'index':i,**resolution}); continue
                fid=self.kb.add(Atom(frame['pred'],tuple(frame['args'])),sentence_source)
                remember_document_facts([fid])
                stored_direct+=1
                row={'index':i,'status':'document_fact_stored','id':fid}
                results.append(attach_document_link(row,fid,discourse_relation,prior_fact_ids,sentence_source))
                continue

            # Reuse an already acquired open schema without modifying discourse
            # focus; a document sentence is not a conversational turn.  Resolve
            # reference markers before storing a schema fact so they cannot become
            # accidental entity values.
            schema_match=self.schemas.parse_learned_surface(semantic_sentence)
            if schema_match.get('status')=='schema_surface_matched':
                schema_pred=schema_match['target'] if schema_match.get('positive',True) else '!'+schema_match['target']
                schema_frame={'act':'assert','pred':schema_pred,'args':list(schema_match['args'])}
                resolution=self._resolve_document_coreference(schema_frame,document_facts)
                if resolution.get('status')=='document_coreference_resolved':
                    fid,event=store_resolved(resolution['frame'],sentence,sentence_source,resolution)
                    remember_selected_event_choice(schema_frame,resolution,i,fid)
                    remember_selected_latent_bundle(schema_frame,resolution,i,fid)
                    stored_schema+=1; coref_resolved+=1
                    row={'index':i,'status':'document_coreference_resolved','id':fid,
                         'predicate':resolution['predicate'],'args':resolution['args'],
                         'references':resolution['references'],'schema_surface':schema_match.get('surface'),
                         'provenance':event}
                    results.append(attach_document_link(row,fid,discourse_relation,prior_fact_ids,sentence_source))
                    continue
                if resolution.get('status')=='document_coreference_ambiguous':
                    remember_ambiguous_event_choice(schema_frame,resolution,i)
                    coref_ambiguous+=1; results.append({'index':i,**resolution}); continue
                if resolution.get('status')=='document_coreference_unresolved':
                    coref_unresolved+=1; results.append({'index':i,**resolution}); continue
            acquired=self.schemas.acquire_assertion(semantic_sentence,source=sentence_source,require_novel=True)
            if acquired.get('status')=='schema_fact_stored':
                remember_document_facts([acquired.get('id')])
                stored_schema+=1
                row={'index':i,**acquired}
                results.append(attach_document_link(row,acquired.get('id'),discourse_relation,prior_fact_ids,sentence_source)); continue
            if acquired.get('status')=='schema_surface_ambiguous':
                results.append({'index':i,**acquired}); continue

            # Unknown anaphoric wording is not evidence for a new opaque relation.
            # Otherwise repeated ``eso/esto/...`` tokens can be promoted as if they
            # were ordinary entities, contaminating both grammar and facts.
            if self._document_has_reference_marker(semantic_sentence):
                coref_unresolved+=1
                results.append({'index':i,'status':'document_coreference_unresolved',
                                'reason':'reference_without_grounded_assertion','candidates':[]})
                continue

            negative=self.observe_raw_negative_relation(semantic_sentence,source=sentence_source)
            if negative.get('status') not in ('raw_negative_relation_ignored',):
                remember_document_facts(negative.get('fact_ids',[]))
                current=next((fid for fid in negative.get('fact_ids',[])
                              if (self.kb.get_fact(fid) or {}).get('source','').startswith(sentence_source)),None)
                row={'index':i,**negative}
                results.append(attach_document_link(row,current,discourse_relation,prior_fact_ids,sentence_source))
                if negative.get('status')=='raw_negative_relation_learned':
                    promoted.add(negative.get('predicate'))
                continue
            meta=self.observe_meta_raw_relation(semantic_sentence,source=sentence_source)
            if meta.get('status')=='raw_relation_meta_transferred':
                remember_document_facts([meta.get('fact_id')])
                row={'index':i,**meta}
                results.append(attach_document_link(row,meta.get('fact_id'),discourse_relation,prior_fact_ids,sentence_source)); promoted.add(meta.get('predicate')); continue
            raw=self.observe_raw_relation(semantic_sentence,source=sentence_source)
            remember_document_facts(raw.get('fact_ids',[]))
            current=next((fid for fid in raw.get('fact_ids',[])
                          if (self.kb.get_fact(fid) or {}).get('source','').startswith(sentence_source)),None)
            row={'index':i,**raw}
            results.append(attach_document_link(row,current,discourse_relation,prior_fact_ids,sentence_source))
            if raw.get('status')=='raw_relation_learned':
                promoted.add(raw.get('predicate'))

        event_meta_bootstrap=self._observe_document_event_meta_bootstrap(
            sentences,results,source,document_episode_id)
        if event_meta_bootstrap.get('status')=='document_event_meta_bootstrap_learned':
            for rel in event_meta_bootstrap.get('relations',[]):
                if not rel.get('existing') and rel.get('predicate'):
                    promoted.add(rel['predicate'])
        after=self.kb.stats()['facts']
        report={'status':'document_ingested','source':source,'sentences':len(sentences),
                'facts_added':after-before,'stored_direct':stored_direct,
                'stored_via_schema':stored_schema,'relations_promoted':len(promoted),
                'promoted_predicates':sorted(x for x in promoted if x),
                'questions_skipped':skipped_questions,'conditionals_skipped':skipped_conditionals,
                'conditionals_processed':processed_conditionals,'rules_learned':len(learned_rules),
                'learned_rule_ids':sorted(x for x in learned_rules if x),
                'sentences_too_long':too_long,
                'coreferences_resolved':coref_resolved,
                'coreferences_ambiguous':coref_ambiguous,
                'coreferences_unresolved':coref_unresolved,
                'document_links_stored':document_links_stored,
                'document_links_unresolved':document_links_unresolved,
                'document_events_materialized':document_events_materialized,
                'document_dependencies_materialized':document_dependencies_materialized,
                'document_causal_dependencies_materialized':document_causal_dependencies_materialized,
                'document_states_materialized':document_states_materialized,
                'document_latent_bundles_materialized':document_latent_bundles_materialized,
                'document_event_meta_bootstrap':event_meta_bootstrap,
                'document_meta_instructions_executed':0,
                'language_examples_added':len(self.language.examples)-language_before,
                'sentence_results':results}
        self.training_reports.append({k:v for k,v in report.items() if k!='sentence_results'} | {'type':'document_ingestion_v518'})
        return report
