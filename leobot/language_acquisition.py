"""Bounded acquisition of language constructions and opaque relations.

This mixin owns hypotheses learned from raw utterances. Bot keeps the cognitive
state and persistence; document and dialogue paths call these methods.
"""
from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from itertools import combinations, permutations

from .core import Atom
from .language import Language, normalize


class LanguageAcquisitionMixin:
    def _grounding_parse_source(self, parsed: dict) -> tuple[str | None, bool]:
        """Find the unique active grounding on which a parsed fact depends."""
        indices=parsed.get('construction_indices',())
        if not indices:
            return None,False
        examples=self.language.examples
        if any(not isinstance(index,int) or index<0 or index>=len(examples)
               for index in indices):
            return None,True
        selected=[examples[index] for index in indices]
        if any(ex.get('source')!='grounded_induction' for ex in selected):
            return None,False  # independent instruction/source also parses it
        clusters=set()
        for ex in selected:
            matches=[cluster for cluster,state in self.grounding_hypotheses.items()
                     if state.get('promoted') and any(
                         row.get('text')==ex.get('text') and row.get('frame')==ex.get('frame')
                         for row in state.get('promoted_examples',()))]
            if len(matches)!=1:
                return None,True
            clusters.add(matches[0])
        return (next(iter(clusters)),False) if len(clusters)==1 else (None,True)

    @staticmethod
    def _grounding_probe_hypotheses(state: dict) -> list[dict]:
        """Decode only bounded, aligned assertion candidates from a version space."""
        possible=state.get('possible',())
        if not 2 <= len(possible) <= 8:
            return []
        decoded=[]; generic=None
        for key in possible:
            item=json.loads(key)
            semantic=item['semantic']; surface=item['surface']
            arity=semantic.get('arity')
            order=[int(x) for x in re.findall(r'<a(\d+)>',surface)]
            if (semantic.get('act')!='assert' or not isinstance(arity,int)
                    or not 1 <= arity <= 4 or sorted(order)!=list(range(arity))):
                return []
            shape=re.sub(r'<a\d+>','<slot>',surface)
            if generic is not None and shape!=generic:
                return []
            generic=shape
            decoded.append({'key':key,'pred':semantic['pred'],'surface':surface,
                            'arity':arity,'order':order})
        return decoded

    def _grounding_probe_options(self, state: dict, *, max_rows: int = 128,
                                 max_options: int = 256) -> list[dict]:
        """Use indexed facts to find candidate utterances with explicit truth values."""
        hyps=self._grounding_probe_hypotheses(state)
        if not hyps:
            return []
        observed={normalize(obs['text']) for obs in state.get('observations',())}
        seen=set(); options=[]
        for source in hyps:
            variables=tuple(f'?g{i}' for i in range(source['arity']))
            base=Atom(source['pred'],variables)
            for sign in (base,base.opposite()):
                for index,fact in enumerate(self.kb.matches(sign)):
                    if index>=max_rows:
                        break
                    values=tuple(fact['atom'].args[i] for i in source['order'])
                    text=re.sub(r'<a(\d+)>',
                                lambda match:fact['atom'].args[int(match.group(1))],
                                source['surface'])
                    text=normalize(text)
                    if text in observed or text in seen:
                        continue
                    seen.add(text)
                    judgments={}; frames={}; valid=True
                    for hyp in hyps:
                        args=['']*hyp['arity']
                        for slot,value in zip(hyp['order'],values):
                            args[slot]=value
                        atom=Atom(hyp['pred'],tuple(args))
                        positive=self.kb.contains(atom)
                        negative=self.kb.contains(atom.opposite())
                        if positive==negative:
                            valid=False; break
                        frame={'act':'assert','pred':hyp['pred'],'args':args}
                        if self._grounding_signature(text,frame) is None:
                            valid=False; break
                        judgments[hyp['key']]=positive
                        frames[hyp['key']]=frame
                    if valid:
                        options.append({'text':text,'judgments':judgments,'frames':frames,
                                        'cost':max(1,len(text.split()))})
                    if len(options)>=max_options:
                        break
                if len(options)>=max_options:
                    break
            if len(options)>=max_options:
                break
        return sorted(options,key=lambda row:row['text'])

    def propose_grounding_probe(self) -> dict:
        """Ask about one real utterance; do not infer or invent its answer."""
        for cluster,state in sorted(self.grounding_hypotheses.items(),
                                    key=lambda item:(-len(item[1].get('observations',())),item[0])):
            if state.get('conflict') or state.get('promoted'):
                continue
            options=self._grounding_probe_options(state)
            if not options:
                continue
            hyps=state.get('possible',())
            actions=[]
            for option in options:
                groups=[]
                for outcome in (True,False):
                    groups.append([key for key in hyps if option['judgments'][key]==outcome])
                actions.append({'groups':groups,'cost':option['cost'],
                                'label':option['text']})
            selected=self.meta_controller.select_epistemic_action(hyps,actions)
            if selected.get('status')!='epistemic_action':
                continue
            option=options[selected['chosen_index']]
            probe_id=hashlib.sha256((cluster+'\0'+option['text']).encode()).hexdigest()[:20]
            state['pending_probe']={'id':probe_id,'text':option['text'],
                                    'judgments':option['judgments'],
                                    'frames':option['frames'],'answer':None}
            return {'status':'epistemic_action','probe_id':probe_id,
                    'probe_text':option['text'],
                    'question':f'¿Es cierto que {option["text"]}?',
                    'possible':len(hyps),'offered':len(options),
                    'info_gain_bits':selected['chosen']['info_gain_bits'],
                    'value_per_cost':selected['chosen']['value_per_cost']}
        return {'status':'no_epistemic_action','reason':'no_safe_discriminating_probe'}

    def observe_grounding_probe(self, probe_id: str, answer: bool) -> dict:
        """Apply an environment answer to the exact pending language probe."""
        if type(answer) is not bool:
            raise ValueError('La respuesta a la prueba debe ser sí o no.')
        for cluster,state in self.grounding_hypotheses.items():
            pending=state.get('pending_probe') or {}
            if pending.get('id')!=probe_id:
                continue
            if state.get('conflict'):
                return {'status':'grounding_conflict','possible':0}
            previous=pending.get('answer')
            if previous is not None and previous!=answer:
                promoted=state.get('promoted_examples',())
                if promoted:
                    keys={json.dumps({'text':row['text'],'frame':row['frame']},
                                     sort_keys=True,ensure_ascii=False) for row in promoted}
                    remaining=[ex for ex in self.language.examples
                               if ex.get('source')!='grounded_induction' or
                               json.dumps({'text':ex['text'],'frame':ex['frame']},
                                          sort_keys=True,ensure_ascii=False) not in keys]
                    self.language=Language.from_dict({'examples':remaining})
                removed=[]
                for fid in state.get('derived_fact_ids',()):
                    if self.grounding_fact_dependencies.get(fid)!=cluster:
                        continue
                    if self.kb.remove(fid):
                        removed.append(fid)
                    self.grounding_fact_dependencies.pop(fid,None)
                if removed:
                    dropped=set(removed)
                    self.discourse_facts=[fid for fid in self.discourse_facts if fid not in dropped]
                    if self.last_fact in dropped:
                        self.last_fact=None
                state['derived_fact_ids']=[]
                state['promoted_examples']=[]
                state['promoted']=False; state['conflict']=True; state['possible']=[]
                state.setdefault('probe_observations',[]).append(
                    {'id':probe_id,'text':pending['text'],'answer':answer,'contradicts':previous})
                return {'status':'grounding_conflict','possible':0,
                        'withdrawn':len(promoted),'facts_withdrawn':len(removed)}
            if previous is not None:
                return {'status':'grounding_promoted' if state.get('promoted') else 'grounding_pending',
                        'possible':len(state.get('possible',()))}
            for key,frame in pending['frames'].items():
                atom=Atom(frame['pred'],tuple(frame['args']))
                positive=self.kb.contains(atom)
                negative=self.kb.contains(atom.opposite())
                if positive==negative or positive!=pending['judgments'][key]:
                    return {'status':'no_epistemic_action','reason':'background_changed'}
            pending['answer']=answer
            state.setdefault('probe_observations',[]).append(
                {'id':probe_id,'text':pending['text'],'answer':answer})
            state['possible']=[key for key in state['possible']
                               if pending['judgments'][key]==answer]
            if len(state['possible'])!=1 or len(state.get('observations',()))<self.grounding_min_support:
                return {'status':'grounding_pending','possible':len(state['possible'])}
            winner=state['possible'][0]
            language=Language.from_dict(self.language.as_dict())
            added=[]
            try:
                for observation in state['observations']:
                    detail=observation['candidates'].get(winner)
                    if detail is None:
                        continue
                    if language.teach(observation['text'],detail['frame'],
                                      'grounded_induction',detail['evidence']):
                        added.append({'text':observation['text'],'frame':detail['frame']})
            except ValueError:
                state['conflict']=True; state['possible']=[]
                return {'status':'grounding_conflict','possible':0}
            self.language=language
            state['promoted_examples']=added; state['promoted']=True
            return {'status':'grounding_promoted','possible':1,'support':len(state['observations']),
                    'construction_count':len(added),'cluster':cluster}
        return {'status':'no_epistemic_action','reason':'unknown_probe'}

    @staticmethod
    def _question_like(text: str) -> bool:
        norm = normalize(text)
        starts = ('que ', 'cual ', 'donde ', 'cuando ', 'quien ', 'cuanto ', 'como ',
                  'en que ', 'a que ', 'de que ', 'por que ')
        if '?' in text or '¿' in text or any(norm.startswith(x) for x in starts):
            return True
        # Accented interrogative words also mark a question or request when the
        # user omits punctuation. An unaccented relative «que» remains evidence.
        interrogatives = {'qué', 'quién', 'quiénes', 'cuál', 'cuáles', 'dónde',
                          'adónde', 'cuándo', 'cómo', 'cuánto', 'cuánta',
                          'cuántos', 'cuántas'}
        first_words = re.findall(r'[^\W\d_]+', text.casefold())[:4]
        return any(word in interrogatives for word in first_words)

    def _entities_mentioned(self, text: str) -> set[str]:
        """Retrieve known entities by bounded n-grams, never by full KB scan."""
        tokens = normalize(text).split()
        if not tokens or len(tokens) > 48:
            return set()
        candidates = set()
        for width in range(1, min(4, len(tokens)) + 1):
            for i in range(len(tokens) - width + 1):
                candidates.add(' '.join(tokens[i:i+width]))
        if hasattr(self.kb, 'known_entities'):
            return set(self.kb.known_entities(candidates))
        # Compatibility fallback for custom KB implementations.
        return {x for x in candidates if self.kb.predicates_for_entities({x})}

    @staticmethod
    def _grounding_signature(text: str, frame: dict) -> tuple[str, str] | None:
        """Return a delexicalized surface+semantic key for grounded induction.

        Concrete argument values are replaced by markers tied to their semantic
        argument position.  This lets independent entity pairs support the same
        construction while preserving role/order information.
        """
        norm = normalize(text)
        args = list(frame.get('args', []))
        spans = []
        used: set[int] = set()
        for pos, value in enumerate(args):
            if isinstance(value, str) and value.startswith('?'):
                continue
            needle = normalize(str(value))
            hits = [m for m in re.finditer(r'(?<!\w)' + re.escape(needle) + r'(?!\w)', norm)
                    if not used.intersection(range(m.start(), m.end()))]
            if len(hits) != 1:
                return None
            m = hits[0]
            used.update(range(m.start(), m.end()))
            spans.append((m.start(), m.end(), f'<a{pos}>'))
        spans.sort()
        parts=[]; cursor=0
        for a,b,marker in spans:
            parts.extend((norm[cursor:a], marker)); cursor=b
        parts.append(norm[cursor:])
        surface=''.join(parts)
        semantic={'act':frame.get('act'),'pred':frame.get('pred'),'arity':len(args),
                  'unknown':[i for i,v in enumerate(args) if isinstance(v,str) and v.startswith('?')]}
        return surface, json.dumps(semantic,sort_keys=True,ensure_ascii=False,separators=(',',':'))

    def _record_grounding_candidates(self, text: str, choices: list[dict]) -> dict | None:
        """Update a contrastive version space from one grounded episode.

        Each episode may support several semantic hypotheses.  Hypotheses are
        generalized by replacing concrete entities with role markers, then the
        candidate set is intersected across independent episodes with the same
        delexicalized surface.  Promotion occurs only when one hypothesis remains
        and the independent-support threshold has been reached.
        """
        grouped: dict[str, dict[str, dict]] = {}
        all_evidence=set()
        for chosen in choices:
            sig=self._grounding_signature(text, chosen['frame'])
            if sig is None:
                continue
            surface,semantic_json=sig
            generic_surface=re.sub(r'<a\d+>', '<slot>', surface)
            semantic=json.loads(semantic_json)
            cluster=json.dumps({'surface':generic_surface,'act':semantic.get('act')},
                               sort_keys=True,ensure_ascii=False,separators=(',',':'))
            hyp_key=json.dumps({'surface':surface,'semantic':semantic},
                               sort_keys=True,ensure_ascii=False,separators=(',',':'))
            grouped.setdefault(cluster,{})[hyp_key]=chosen
            all_evidence.update(chosen.get('evidence',()))
        if not grouped:
            return None
        episode_id=json.dumps({'text':normalize(text),'evidence':sorted(all_evidence)},
                              sort_keys=True,ensure_ascii=False,separators=(',',':'))
        promoted_any=False; pending=[]
        for cluster,current in grouped.items():
            state=self.grounding_hypotheses.get(cluster)
            if not isinstance(state,dict) or 'possible' not in state:
                state={'possible':sorted(current),'observations':[],'promoted':False,'conflict':False}
                self.grounding_hypotheses[cluster]=state
            if any(o.get('episode_id')==episode_id for o in state.get('observations',[])):
                pending.append(state)
                continue
            previous=set(state.get('possible',[]))
            now=set(current)
            possible=now if not state.get('observations') else previous & now
            observation={'episode_id':episode_id,'text':text,
                         'candidates':{k:{'frame':v['frame'],'evidence':list(v['evidence'])}
                                       for k,v in current.items()}}
            state.setdefault('observations',[]).append(observation)
            state['possible']=sorted(possible)
            if not possible:
                state['conflict']=True
                pending.append(state)
                continue
            if len(possible)==1 and len(state['observations']) >= self.grounding_min_support and not state.get('promoted'):
                winner=next(iter(possible)); changed=False
                supports=[]; added=[]
                for obs in state['observations']:
                    detail=obs['candidates'].get(winner)
                    if detail is None:
                        continue
                    supports.append(detail)
                    try:
                        taught=self.language.teach(obs['text'],detail['frame'],
                                                   'grounded_induction',detail['evidence'])
                        changed=taught or changed
                        if taught:
                            added.append({'text':obs['text'],'frame':detail['frame']})
                    except ValueError:
                        state['conflict']=True
                        return None
                if len(supports) >= self.grounding_min_support:
                    state['promoted']=True; state['promoted_examples']=added; promoted_any=True
                    self.training_reports.append({'type':'language_grounded_promoted','text':text,
                                                  'hypothesis':winner,'support':len(supports),
                                                  'possible_before_promotion':1})
            else:
                pending.append(state)
        if promoted_any:
            parsed=self.language.parse(text)
            if parsed['status']=='parsed':
                parsed['grounded_induction']={'learned':True,'pending':False,
                    'required':self.grounding_min_support,'candidate_count':len(choices),
                    'version_space':True}
                return parsed
        active=[s for s in pending if not s.get('conflict')]
        if active:
            best=min(active,key=lambda st:(len(st.get('possible',[])) or 10**9,-len(st.get('observations',[]))))
            poss=len(best.get('possible',[])); support=len(best.get('observations',[]))
            self.training_reports.append({'type':'language_grounded_pending','text':text,
                                          'support':support,'required':self.grounding_min_support,
                                          'possible':poss,'version_space':True})
            return {'status':'grounding_pending','frame':None,'alternatives':[],
                    'grounded_induction':{'learned':False,'pending':True,'support':support,
                                          'required':self.grounding_min_support,'possible':poss,
                                          'candidate_count':len(choices),'version_space':True}}
        return None

    @staticmethod
    def _raw_relation_pair_surface(left: str, right: str, max_slots: int = 8) -> tuple[str, int] | None:
        """Anti-unify two raw assertions into a bounded 1--8 role surface.

        Only spans that differ become candidate roles; shared tokens remain
        literal anchors.  This does not guess entity boundaries inside an
        unanchored variable span.  A later version-space support test must show
        that every inferred role varies independently across episodes.
        """
        a=tuple(normalize(left).split()); b=tuple(normalize(right).split())
        if not (2 <= len(a) <= 48 and 2 <= len(b) <= 48) or a == b:
            return None
        blocks=[m for m in SequenceMatcher(a=a,b=b,autojunk=False).get_matching_blocks() if m.size]
        if not blocks:
            return None
        parts=[]; ai=bi=0; slot=0; fixed_tokens=[]
        for m in blocks:
            ga=a[ai:m.a]; gb=b[bi:m.b]
            if ga or gb:
                if not ga or not gb or ga == gb:
                    return None
                parts.append(f'{{s{slot}}}'); slot += 1
                if slot > max_slots:
                    return None
            fixed=a[m.a:m.a+m.size]
            parts.extend(fixed); fixed_tokens.extend(fixed)
            ai=m.a+m.size; bi=m.b+m.size
        ga=a[ai:]; gb=b[bi:]
        if ga or gb:
            if not ga or not gb or ga == gb:
                return None
            parts.append(f'{{s{slot}}}'); slot += 1
        if not (1 <= slot <= max_slots):
            return None
        # A relation anchored only by function words is too easy to discover by
        # accident in ordinary Spanish.  This is a language-wide safety bias, not
        # a topic-specific answer table.
        function_words={'a','al','con','de','del','el','la','los','las','en','por','para',
                        'y','o','un','una','unos','unas','se','es','son','que','su','sus'}
        if not any(len(tok) >= 3 and tok not in function_words for tok in fixed_tokens):
            return None
        # V6.2 speech-act bias: for an unknown surface to be treated as a factual
        # assertion candidate, at least one role must precede a content anchor.
        # Bare command-like patterns such as ``resume {x}`` / ``compara {x} y {y}``
        # therefore remain unresolved instead of becoming facts.  This is not a
        # verb list; learned constructions can later license other word orders.
        content_positions=[i for i,tok in enumerate(parts)
                           if not tok.startswith('{s') and len(tok)>=3 and tok not in function_words]
        slot_positions=[i for i,tok in enumerate(parts) if tok.startswith('{s')]
        if min(slot_positions) >= max(content_positions):
            return None
        return ' '.join(parts), slot

    @staticmethod
    def _raw_relation_match(surface: str, text: str, limit: int = 3) -> list[tuple[str, ...]]:
        """Enumerate slot boundaries for a bounded raw anti-unified surface."""
        st=surface.split(); tokens=normalize(text).split(); parts=[]; fixed=[]
        for tok in st:
            m=re.fullmatch(r'\{s(\d+)\}',tok)
            if m:
                if fixed:
                    parts.append(('fixed',tuple(fixed))); fixed=[]
                parts.append(('slot',int(m.group(1))))
            else:
                fixed.append(tok)
        if fixed:
            parts.append(('fixed',tuple(fixed)))
        slot_ids=[v for k,v in parts if k=='slot']
        if not (1 <= len(slot_ids) <= 8) or slot_ids != list(range(len(slot_ids))):
            return []
        suffix_min=[0]*(len(parts)+1)
        for i in range(len(parts)-1,-1,-1):
            kind,value=parts[i]
            suffix_min[i]=suffix_min[i+1] + (1 if kind=='slot' else len(value))
        out=[]; states=0; max_states=4096
        def walk(pi,ti,values):
            nonlocal states
            states += 1
            if states > max_states:
                if len(out) < 2:
                    out[:] = [('__BUDGET__',), ('__BUDGET2__',)]
                return
            if len(out)>=limit:
                return
            if pi==len(parts):
                if ti==len(tokens) and all(i in values for i in slot_ids):
                    row=tuple(values[i] for i in slot_ids)
                    if row not in out: out.append(row)
                return
            kind,value=parts[pi]
            if kind=='fixed':
                n=len(value)
                if tuple(tokens[ti:ti+n])==value:
                    walk(pi+1,ti+n,values)
                return
            max_end=len(tokens)-suffix_min[pi+1]
            for end in range(ti+1,max_end+1):
                values[value]=' '.join(tokens[ti:end])
                walk(pi+1,end,values)
                if len(out)>=limit: break
            values.pop(value,None)
        walk(0,0,{})
        return out

    @staticmethod
    def _raw_relation_predicate(surface: str, arity: int) -> str:
        digest=hashlib.blake2b(surface.encode('utf8'),digest_size=8).hexdigest()
        return f'primitive_{digest}_a{arity}'

    def _raw_lexical_meta_frames(self, min_support: int = 3) -> list[dict]:
        """Infer bounded lexical relation frames from independently promoted surfaces.

        V5.20 transfers *segmentation/topology*, never predicate meaning.  If at
        least ``min_support`` directly induced opaque relations have the same
        slot topology and differ at exactly one informative fixed-token position,
        that position may act as a new opaque relation lexeme.  Meta-transferred
        relations are deliberately excluded from supporting further frames so a
        single learned schema cannot self-amplify into unsupported syntax.
        """
        function_words={'a','al','con','de','del','el','la','los','las','en','por','para',
                        'y','o','un','una','unos','unas','se','es','son','que','su','sus'}
        groups={}
        for promotion in self.raw_relation_promotions.values():
            if promotion.get('meta_transferred') or promotion.get('learned_from_negative_only'):
                continue
            surface=promotion.get('surface'); arity=int(promotion.get('arity') or 0)
            if not isinstance(surface,str) or not (1 <= arity <= 8):
                continue
            tokens=surface.split()
            slots=[t for t in tokens if re.fullmatch(r'\{s\d+\}',t)]
            if slots != [f'{{s{i}}}' for i in range(arity)]:
                continue
            for i,tok in enumerate(tokens):
                if re.fullmatch(r'\{s\d+\}',tok) or tok in function_words or len(tok)<3:
                    continue
                template=list(tokens); template[i]='{rel}'
                key=(arity,tuple(template))
                groups.setdefault(key,[]).append((tok,promotion))
        out=[]
        for (arity,template),rows in groups.items():
            lexemes={lex for lex,_ in rows}; surfaces={r.get('surface') for _,r in rows}
            predicates={r.get('predicate') for _,r in rows}
            if len(lexemes)<min_support or len(surfaces)<min_support or len(predicates)<min_support:
                continue
            out.append({'arity':arity,'template':list(template),'support':len(surfaces),
                        'lexemes':sorted(lexemes),'source_surfaces':sorted(surfaces)})
        return sorted(out,key=lambda x:(-x['support'],x['arity'],x['template']))

    @staticmethod
    def _raw_lexical_meta_match(template: list[str], text: str, arity: int,
                                limit: int = 3) -> list[tuple[str, tuple[str, ...]]]:
        """Enumerate unambiguous ``(relation_lexeme,args)`` analyses for a meta-frame."""
        tokens=normalize(text).split(); parts=[]; fixed=[]
        for tok in template:
            m=re.fullmatch(r'\{s(\d+)\}',tok)
            if m:
                if fixed: parts.append(('fixed',tuple(fixed))); fixed=[]
                parts.append(('slot',int(m.group(1))))
            elif tok=='{rel}':
                if fixed: parts.append(('fixed',tuple(fixed))); fixed=[]
                parts.append(('rel',None))
            else:
                fixed.append(tok)
        if fixed: parts.append(('fixed',tuple(fixed)))
        slot_ids=[v for k,v in parts if k=='slot']
        if slot_ids != list(range(arity)) or sum(k=='rel' for k,_ in parts)!=1:
            return []
        suffix_min=[0]*(len(parts)+1)
        for i in range(len(parts)-1,-1,-1):
            kind,value=parts[i]
            suffix_min[i]=suffix_min[i+1] + (1 if kind in ('slot','rel') else len(value))
        function_words={'a','al','con','de','del','el','la','los','las','en','por','para',
                        'y','o','un','una','unos','unas','se','es','son','que','su','sus'}
        out=[]; states=0; max_states=4096
        def walk(pi,ti,values,rel):
            nonlocal states
            states+=1
            if states>max_states:
                if len(out)<2: out[:]=[('__BUDGET__',()),('__BUDGET2__',())]
                return
            if len(out)>=limit: return
            if pi==len(parts):
                if ti==len(tokens) and rel is not None and all(i in values for i in slot_ids):
                    row=(rel,tuple(values[i] for i in slot_ids))
                    if row not in out: out.append(row)
                return
            kind,value=parts[pi]
            if kind=='fixed':
                n=len(value)
                if tuple(tokens[ti:ti+n])==value: walk(pi+1,ti+n,values,rel)
                return
            if kind=='rel':
                if ti>=len(tokens): return
                lex=tokens[ti]
                if len(lex)>=3 and lex not in function_words:
                    walk(pi+1,ti+1,values,lex)
                return
            max_end=len(tokens)-suffix_min[pi+1]
            for end in range(ti+1,max_end+1):
                values[value]=' '.join(tokens[ti:end]); walk(pi+1,end,values,rel)
                if len(out)>=limit: break
            values.pop(value,None)
        walk(0,0,{},None)
        return out

    def observe_meta_raw_relation(self, text: str, source: str = 'conversación') -> dict:
        """Represent a one-shot opaque relation only when learned syntax makes it unique.

        The relation lexeme gets a fresh deterministic predicate.  No synonymy,
        definition, or truth beyond the asserted sentence is inferred.
        """
        norm=normalize(text)
        if self._question_like(text) or len(norm.split())<2 or len(norm.split())>48:
            return {'status':'raw_meta_relation_ignored'}
        if norm.startswith('no ') or ' no ' in f' {norm} ':
            return {'status':'raw_meta_relation_ignored'}
        candidates=[]
        for frame in self._raw_lexical_meta_frames():
            matches=self._raw_lexical_meta_match(frame['template'],norm,frame['arity'],limit=2)
            if len(matches)!=1:
                continue
            lex,args=matches[0]
            surface=' '.join(lex if tok=='{rel}' else tok for tok in frame['template'])
            if surface in self.raw_relation_promotions:
                continue
            candidates.append((surface,frame['arity'],lex,args,frame))
        # Multiple learned syntactic families explaining the same sentence are an
        # actual ambiguity; do not rank one by recency or vocabulary.
        unique={(s,a,args) for s,a,_,args,_ in candidates}
        if len(unique)!=1:
            return {'status':'raw_meta_relation_ambiguous' if unique else 'raw_meta_relation_unavailable',
                    'candidates':len(unique)}
        surface,arity,lex,args,frame=candidates[0]
        pred=self._raw_relation_predicate(surface,arity)
        semantic={'act':'assert','pred':pred,'args':list(args)}
        try:
            changed=self.language.teach(norm,semantic,'lexical_meta_transfer_v520',
                                        [f'meta_template:{" ".join(frame["template"])}'])
        except ValueError:
            return {'status':'raw_meta_relation_ambiguous','candidates':1,'reason':'alignment_failed'}
        fid=self.kb.add(Atom(pred,args),f'{source}:meta_raw_relation:{pred}')
        evidence=[{'text':norm,'args':list(args),'fact_id':fid}]
        promotion={'predicate':pred,'surface':surface,'arity':arity,'support':1,
                   'evidence':evidence,'mechanism':'lexical_meta_transfer_v520',
                   'meta_transferred':True,'meta_template':frame['template'],
                   'meta_support':frame['support'],'relation_lexeme':lex}
        self.raw_relation_promotions[surface]=promotion
        if hasattr(self.kb,'audit'):
            event={'event':'raw_relation_meta_transferred',**promotion}
            if event not in self.kb.audit: self.kb.audit.append(event)
        self.training_reports.append({'type':'raw_relation_meta_transferred',**promotion})
        question_constructions=self._apply_question_transforms(promotion)
        return {'status':'raw_relation_meta_transferred','predicate':pred,'surface':surface,
                'arity':arity,'support':1,'meta_support':frame['support'],'fact_id':fid,
                'construction_added':bool(changed),'question_constructions':question_constructions,
                'relation_lexeme':lex,'args':list(args),'meta_template':frame['template']}

    def _restore_raw_consumption(self) -> None:
        """Mark raw episodes already explained by a promoted primitive.

        V5.14 and older checkpoints persisted promoted support in the same pending
        observation pool.  Reusing those explained episodes against later wording
        can create a spurious coarse relation (for example ``proyecto {s0}``).
        Consumption is therefore explicit and reconstructed from promotion
        evidence when an older checkpoint is loaded.
        """
        positive={}
        negative={}
        for promotion in self.raw_relation_promotions.values():
            pred=promotion.get('predicate')
            if not pred:
                continue
            is_negative=bool(promotion.get('learned_from_negative_only'))
            for evidence in promotion.get('evidence',[]):
                key=normalize(evidence.get('original_text') if is_negative
                              else evidence.get('text',''))
                if key:
                    (negative if is_negative else positive)[key]=pred
        for obs in self.raw_relation_observations:
            pred=positive.get(normalize(obs.get('text','')))
            if pred and not obs.get('consumed_by'):
                obs['consumed_by']=pred
        for obs in self.raw_negative_relation_observations:
            pred=negative.get(normalize(obs.get('text','')))
            if pred and not obs.get('consumed_by'):
                obs['consumed_by']=pred

    def observe_raw_relation(self, text: str, source: str = 'conversación') -> dict:
        """Discover an opaque 1--8 role relation from repeated raw assertions.

        Promotion requires independent utterances explained unambiguously by one
        most-supported surface.  Every inferred role must vary across all support
        episodes, which prevents a constant phrase from being mislabeled as an
        argument.  The result is intentionally opaque: the mechanism learns a
        stable relational surface and its arguments, not an intensional definition.
        """
        norm=normalize(text)
        if self._question_like(text) or len(norm.split()) < 2 or len(norm.split()) > 48:
            return {'status':'raw_relation_ignored'}
        if norm.startswith('no ') or ' no ' in f' {norm} ' or norm.startswith('/'):
            return {'status':'raw_relation_ignored'}
        if any(o.get('text')==norm for o in self.raw_relation_observations):
            return {'status':'raw_relation_duplicate'}
        self.raw_relation_observations.append({'text':norm,'source':source,'consumed_by':None})
        # Bound unfinished evidence; promoted facts/constructions live elsewhere.
        if len(self.raw_relation_observations) > 96:
            self.raw_relation_observations=self.raw_relation_observations[-96:]
        pending=[o for o in self.raw_relation_observations if not o.get('consumed_by')]
        candidate_surfaces={}
        for a,b in combinations(pending,2):
            proposal=self._raw_relation_pair_surface(a['text'],b['text'],max_slots=self.raw_relation_max_arity)
            if proposal:
                surface,arity=proposal
                if surface not in self.raw_relation_promotions:
                    candidate_surfaces[surface]=arity
        viable=[]
        for surface,arity in sorted(candidate_surfaces.items()):
            support=[]; unsafe=False
            for obs in pending:
                rows=self._raw_relation_match(surface,obs['text'],limit=2)
                if len(rows)>1:
                    unsafe=True; break
                if len(rows)==1:
                    support.append((obs,rows[0]))
            required=max(self.raw_relation_min_support,arity)
            if unsafe or len(support) < required:
                continue
            # Each role must vary independently across all supports; otherwise a
            # fixed phrase was probably swallowed into a slot by pairwise alignment.
            role_values=[{args[i] for _,args in support} for i in range(arity)]
            if any(len(values) != len(support) for values in role_values):
                continue
            # Repeated argument tuples under cosmetic changes are not independent support.
            if len({args for _,args in support}) != len(support):
                continue
            fixed=[t for t in surface.split() if not t.startswith('{s')]
            rank=(len(support),len(fixed),sum(map(len,fixed)))
            viable.append((rank,surface,arity,support))
        if not viable:
            return {'status':'raw_relation_pending','support':1,
                    'required':self.raw_relation_min_support}
        best_rank=max(r for r,_,_,_ in viable)
        best=[x for x in viable if x[0]==best_rank]
        if len(best) != 1:
            return {'status':'raw_relation_ambiguous','candidates':[x[1] for x in best]}
        _,surface,arity,support=best[0]
        pred=self._raw_relation_predicate(surface,arity)
        changed=False; fact_ids=[]; evidence=[]
        for obs,args in support:
            frame={'act':'assert','pred':pred,'args':list(args)}
            try:
                changed=self.language.teach(obs['text'],frame,'raw_relation_induction',
                                            [f'antiunified:{surface}']) or changed
            except ValueError:
                return {'status':'raw_relation_ambiguous','surface':surface,
                        'reason':'alignment_failed'}
            fid=self.kb.add(Atom(pred,args),f'{obs["source"]}:raw_relation:{pred}')
            fact_ids.append(fid); evidence.append({'text':obs['text'],'args':list(args),'fact_id':fid})
        promotion={'predicate':pred,'surface':surface,'arity':arity,'support':len(support),
                   'evidence':evidence,'mechanism':'token_antiunification_v52'}
        for obs,_ in support:
            obs['consumed_by']=pred
        self.raw_relation_promotions[surface]=promotion
        if hasattr(self.kb,'audit'):
            event={'event':'raw_relation_promoted',**promotion}
            if event not in self.kb.audit: self.kb.audit.append(event)
        self.training_reports.append({'type':'raw_relation_promoted',**promotion})
        question_constructions=self._apply_question_transforms(promotion)
        return {'status':'raw_relation_learned','predicate':pred,'surface':surface,
                'arity':arity,'support':len(support),'fact_ids':fact_ids,
                'construction_added':bool(changed),'question_constructions':question_constructions,
                'evidence':evidence}

    def observe_raw_negative_relation(self, text: str, source: str = 'conversación') -> dict:
        """Discover an opaque base relation from repeated explicit negative claims.

        This is deliberately separate from ``observe_raw_relation``: negative
        episodes never support a positive assertion learner.  Exactly one Spanish
        ``no`` token is stripped as grammatical polarity; anti-unification then
        discovers the affirmative surface while all stored evidence is !predicate.
        The legacy extensional-grounding mode keeps its historical behavior.
        """
        if self.allow_extensional_grounding or self._question_like(text):
            return {'status':'raw_negative_relation_ignored'}
        norm=normalize(text); tokens=norm.split()
        positions=[i for i,tok in enumerate(tokens) if tok=='no']
        if len(positions)!=1 or len(tokens)<3 or len(tokens)>49 or norm.startswith('/'):
            return {'status':'raw_negative_relation_ignored'}
        i=positions[0]; affirmative=' '.join(tokens[:i]+tokens[i+1:])
        if len(affirmative.split())<2:
            return {'status':'raw_negative_relation_ignored'}
        if any(o.get('text')==norm for o in self.raw_negative_relation_observations):
            return {'status':'raw_negative_relation_duplicate'}
        self.raw_negative_relation_observations.append({'text':norm,'affirmative':affirmative,'source':source,'consumed_by':None})
        if len(self.raw_negative_relation_observations)>96:
            self.raw_negative_relation_observations=self.raw_negative_relation_observations[-96:]
        pending=[o for o in self.raw_negative_relation_observations if not o.get('consumed_by')]
        candidate_surfaces={}
        for a,b in combinations(pending,2):
            proposal=self._raw_relation_pair_surface(a['affirmative'],b['affirmative'],max_slots=self.raw_relation_max_arity)
            if proposal:
                surface,arity=proposal
                if surface not in self.raw_relation_promotions:
                    candidate_surfaces[surface]=arity
        viable=[]
        for surface,arity in sorted(candidate_surfaces.items()):
            support=[]; unsafe=False
            for obs in pending:
                rows=self._raw_relation_match(surface,obs['affirmative'],limit=2)
                if len(rows)>1:
                    unsafe=True; break
                if len(rows)==1:
                    support.append((obs,rows[0]))
            required=max(self.raw_relation_min_support,arity)
            if unsafe or len(support)<required:
                continue
            role_values=[{args[i] for _,args in support} for i in range(arity)]
            if any(len(values)!=len(support) for values in role_values):
                continue
            if len({args for _,args in support})!=len(support):
                continue
            fixed=[t for t in surface.split() if not t.startswith('{s')]
            rank=(len(support),len(fixed),sum(map(len,fixed)))
            viable.append((rank,surface,arity,support))
        if not viable:
            return {'status':'raw_negative_relation_pending','support':1,
                    'required':self.raw_relation_min_support}
        best_rank=max(r for r,_,_,_ in viable); best=[x for x in viable if x[0]==best_rank]
        if len(best)!=1:
            return {'status':'raw_negative_relation_ambiguous','candidates':[x[1] for x in best]}
        _,surface,arity,support=best[0]
        pred=self._raw_relation_predicate(surface,arity)
        changed=False; fact_ids=[]; evidence=[]
        for obs,args in support:
            frame={'act':'assert','pred':pred,'args':list(args)}
            try:
                changed=self.language.teach(obs['affirmative'],frame,'raw_negative_relation_induction',
                                            [f'negative_antiunified:{surface}']) or changed
            except ValueError:
                return {'status':'raw_negative_relation_ambiguous','surface':surface,
                        'reason':'alignment_failed'}
            fid=self.kb.add(Atom('!'+pred,args),f'{obs["source"]}:raw_negative_relation:{pred}')
            fact_ids.append(fid)
            evidence.append({'text':obs['affirmative'],'original_text':obs['text'],
                             'args':list(args),'fact_id':fid,'positive':False})
        promotion={'predicate':pred,'surface':surface,'arity':arity,'support':len(support),
                   'evidence':evidence,'mechanism':'negative_token_antiunification_v511',
                   'learned_from_negative_only':True}
        for obs,_ in support:
            obs['consumed_by']=pred
        self.raw_relation_promotions[surface]=promotion
        if hasattr(self.kb,'audit'):
            event={'event':'raw_negative_relation_promoted',**promotion}
            if event not in self.kb.audit: self.kb.audit.append(event)
        self.training_reports.append({'type':'raw_negative_relation_promoted',**promotion})
        question_constructions=self._apply_question_transforms(promotion)
        return {'status':'raw_negative_relation_learned','predicate':pred,'surface':surface,
                'arity':arity,'support':len(support),'fact_ids':fact_ids,
                'construction_added':bool(changed),'question_constructions':question_constructions,
                'evidence':evidence}

    def _question_has_relation_anchor(self, text: str, predicate: str) -> bool:
        """Require the question to retain the learned relation's lexical anchors.

        This is intentionally literal.  A new verb cannot be declared equivalent
        to a known predicate merely because the same entities co-occur.
        """
        words=set(normalize(text).split())
        for construction in self.language.constructions:
            if (construction.frame.get('act')!='assert' or
                    construction.frame.get('pred')!=predicate):
                continue
            anchors={token for token in construction.surface.split()
                     if not token.startswith('{s') and len(token)>=4}
            if anchors and anchors.issubset(words):
                return True
        return False

    def _question_preserves_bound_roles(self, text: str, predicate: str,
                                        args: list[str], *, negative: bool) -> bool:
        """Check a fronted question against the known assertion's role order.

        Removing the answer role may also remove its immediately preceding fixed
        word.  A leading known role may move behind the first relation word.
        Every other known role and fixed word must appear in the same order.
        This bounded transformation admits ordinary fronted questions while
        rejecting a question that swaps two named participants.
        """
        question=normalize(text).split()
        if not question or question[0] not in {
                'que','quien','quienes','cual','cuales','donde','cuando',
                'cuanto','cuanta','cuantos','cuantas','como'}:
            return False
        body=question[1:]
        if negative:
            if not body or body[0]!='no':
                return False
            body=body[1:]
        elif body and body[0]=='no':
            return False

        for construction in self.language.constructions:
            if (construction.frame.get('act')!='assert' or
                    construction.frame.get('pred')!=predicate):
                continue
            slots={f'{{{slot["name"]}}}':int(slot['path'][1])
                   for slot in construction.slots
                   if len(slot.get('path',()))==2 and slot['path'][0]=='args'
                   and isinstance(slot['path'][1],int)}
            chunks=[]; missing=[]
            for token in construction.surface.split():
                if token not in slots:
                    chunks.append(('fixed',[token]))
                    continue
                pos=slots[token]
                if pos<0 or pos>=len(args):
                    chunks=[]; break
                if args[pos]=='?answer':
                    missing.append(len(chunks))
                    chunks.append(('missing',[]))
                else:
                    chunks.append(('slot',normalize(args[pos]).split()))
            if len(missing)!=1:
                continue
            for drop_preceding in (False,True):
                omit={missing[0]}
                if drop_preceding:
                    previous=missing[0]-1
                    if previous<0 or chunks[previous][0]!='fixed':
                        continue
                    omit.add(previous)
                kept=[chunk for i,chunk in enumerate(chunks) if i not in omit]
                variants=[kept]
                if len(kept)>=2 and kept[0][0]=='slot' and kept[1][0]=='fixed':
                    variants.append([kept[1],kept[0],*kept[2:]])
                if any([token for _,part in variant for token in part]==body
                       for variant in variants):
                    return True
        return False

    def _try_grounded_language(self, text: str, *, require_surface_anchor: bool = False) -> dict | None:
        """Induce a construction from independently repeated grounded evidence.

        Candidate meanings come only from already-known facts whose concrete
        entities occur in the utterance.  A unique candidate becomes an untrusted
        hypothesis first; it enters the active grammar only after independent
        supports reach ``grounding_min_support``.  Both positive and explicitly
        negative facts are considered.
        """
        entities = self._entities_mentioned(text)
        if not entities or len(entities) > 8:
            return None
        pred_scores = self.kb.predicates_for_entities(entities)
        if not pred_scores:
            return None
        candidates: dict[str, dict] = {}
        checks = 0; max_checks = 768
        question = self._question_like(text)
        ordered_entities = sorted(entities, key=lambda x: (-len(x), x))
        for base_pred, _ in sorted(pred_scores.items(), key=lambda kv: (-kv[1], kv[0])):
            arity = int(getattr(self.kb, 'arity', {}).get(base_pred, 0) or 0)
            if not 1 <= arity <= 4:
                continue
            if (question and require_surface_anchor and
                    not self._question_has_relation_anchor(text,base_pred)):
                continue
            if not question and pred_scores.get(base_pred, 0) < arity:
                continue
            for pred in (base_pred, '!' + base_pred):
                if question and require_surface_anchor:
                    asked_negative='no' in normalize(text).split()
                    if pred.startswith('!') != asked_negative:
                        continue
                if question:
                    bound_count = arity - 1
                    if bound_count > len(ordered_entities):
                        continue
                    bound_rows = [()] if bound_count == 0 else permutations(ordered_entities, bound_count)
                    for bound in bound_rows:
                        for unknown_pos in range(arity):
                            checks += 1
                            if checks > max_checks:
                                return None
                            vals = iter(bound); args=[]
                            for pos in range(arity):
                                args.append('?answer' if pos == unknown_pos else next(vals))
                            if (require_surface_anchor and
                                    not self._question_preserves_bound_roles(
                                        text,base_pred,args,negative=pred.startswith('!'))):
                                continue
                            rows=[]
                            for fact in self.kb.matches(Atom(pred, tuple(args))):
                                rows.append(fact)
                                if len(rows) >= 4:
                                    break
                            if not rows:
                                continue
                            frame={'act':'query','pred':pred,'args':args}
                            key=json.dumps(frame,sort_keys=True,ensure_ascii=False)
                            candidates[key]={'frame':frame,'evidence':[r['id'] for r in rows]}
                else:
                    if arity > len(ordered_entities):
                        continue
                    for args in permutations(ordered_entities, arity):
                        checks += 1
                        if checks > max_checks:
                            return None
                        fact = next(self.kb.matches(Atom(pred, tuple(args))), None)
                        if fact is None:
                            continue
                        frame={'act':'assert','pred':pred,'args':list(args)}
                        key=json.dumps(frame,sort_keys=True,ensure_ascii=False)
                        candidates[key]={'frame':frame,'evidence':[fact['id']]}
        if not candidates:
            return None
        return self._record_grounding_candidates(text, list(candidates.values()))
