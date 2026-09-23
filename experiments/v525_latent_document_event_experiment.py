"""V5.25 frozen experiment: demand-driven latent document events.

A recurrent structural pair may become an event *schema candidate*, but no event
entity is materialized during training.  A demonstrative can later force one
latent event only when exactly one promoted structural candidate is compatible.
The ablation disables event-schema observation while keeping the rest of V5.24+
identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v525_latent_document_event.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


class NoLatentEventBot(Bot):
    def _observe_document_event_schema(self, fact, prior_facts, episode_id, document_source):
        return None


def grammar(bot):
    text='''
ana frobla caja.
bruno frobla carta.
cora frobla libro.
ana tulka puerto.
bruno tulka plaza.
cora tulka parque.
uno activa alarma1.
dos activa alarma2.
tres activa alarma3.
'''
    r=bot.ingest_document_text(text,source='v525_grammar')
    by_surface={p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}
    return r,by_surface


def teach_event_schema(bot):
    rows=[('dora','paquete','norte'),('eva','caja azul','sur'),('luis','archivo','centro')]
    for i,(person,obj,place) in enumerate(rows):
        bot.ingest_document_text(f'{person} frobla {obj}. {person} tulka {place}.',source=f'v525_schema_{i}')


def main():
    before=code_hash()
    bot=Bot(allow_extensional_grounding=False); grammar_report,preds=grammar(bot); teach_event_schema(bot)
    promoted=[s for s in bot.document_event_schema_hypotheses.values() if s.get('promoted')]
    initial_schema_support=promoted[0].get('support') if len(promoted)==1 else None
    pre_materialized=sum(1 for f in bot.kb.facts.values() if f['atom'].pred.startswith('_event_'))
    training_texts={o.get('text') for o in bot.raw_relation_observations if o.get('text')}
    episodic_hits=sum(f'persona{i} frobla objeto{i}' in training_texts for i in range(100))

    positive=0; query_times=[]; event_ids=[]
    for i in range(100):
        t=perf_counter()
        r=bot.ingest_document_text(
            f'persona{i} frobla objeto{i}. persona{i} tulka lugar{i}. Eso activa alarma{i}.',
            source=f'v525_target_{i}')
        query_times.append((perf_counter()-t)*1000)
        row=r['sentence_results'][2]
        ok=(row.get('status')=='document_coreference_resolved'
            and 'latent_document_event_v525' in row.get('references',[{}])[0].get('criteria',[])
            and r.get('document_events_materialized')==1)
        if ok:
            event_id=row['references'][0]['antecedent'];event_ids.append(event_id)
            ok=bot.kb.contains(Atom(preds['{s0} activa {s1}'],(event_id,f'alarma{i}')))
        positive+=bool(ok)

    ablation=NoLatentEventBot(allow_extensional_grounding=False); grammar(ablation)
    for i,(person,obj,place) in enumerate([('dora','paquete','norte'),('eva','caja azul','sur'),('luis','archivo','centro')]):
        ablation.ingest_document_text(f'{person} frobla {obj}. {person} tulka {place}.',source=f'v525_ablation_schema_{i}')
    ablation_unresolved=0
    for i in range(100):
        r=ablation.ingest_document_text(
            f'ap{i} frobla ao{i}. ap{i} tulka al{i}. Eso activa aa{i}.',source=f'v525_ablation_{i}')
        ablation_unresolved += r['sentence_results'][2].get('status')=='document_coreference_unresolved'

    ambiguous=0; ambiguous_materialized=0
    for i in range(50):
        r=bot.ingest_document_text(
            f'x{i} frobla xa{i}. x{i} tulka xl{i}. y{i} frobla ya{i}. y{i} tulka yl{i}. Eso activa za{i}.',
            source=f'v525_ambiguous_{i}')
        ambiguous += r['sentence_results'][4].get('status')=='document_coreference_ambiguous'
        ambiguous_materialized += r.get('document_events_materialized',0)

    after=code_hash()
    report={
        'version':'0.5.25',
        'experiment':'demand_driven_latent_document_event',
        'code_hash_before':before,
        'learned':{
            'grammar_relations_promoted':grammar_report['relations_promoted'],
            'event_schemas_promoted':len(promoted),
            'schema_support_at_freeze':initial_schema_support,
            'event_representation_facts_before_demand':pre_materialized,
            'heldout_event_references_resolved':positive,
            'heldout_event_reference_cases':100,
            'unique_event_ids':len(set(event_ids)),
            'median_document_ms':median(query_times),
        },
        'controls':{
            'ablation_without_event_schema_unresolved':ablation_unresolved,
            'ablation_cases':100,
            'ambiguous_partitions_abstained':ambiguous,
            'ambiguous_cases':50,
            'events_materialized_in_ambiguous_cases':ambiguous_materialized,
            'episodic_exact_text_hits_before_heldout':episodic_hits,
        },
        'code_hash_after':after,
        'code_unchanged_during_evaluation':before==after,
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
