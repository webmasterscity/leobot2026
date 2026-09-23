"""V5.26 frozen experiment: variable-length latent event clusters.

The treatment may induce connected event schemas over 2--4 consecutive explicit
facts and keeps only maximal matches at reference time.  The ablation is the same
code restricted to V5.25 two-fact schemas.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v526_variable_event_cluster.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

class PairOnlyEventBot(Bot):
    @classmethod
    def _document_event_cluster_signature(cls,facts):
        if len(facts)>2:
            return None
        return super()._document_event_cluster_signature(facts)

def grammar(bot):
    text='''
ana frobla caja.
bruno frobla carta.
cora frobla libro.
ana tulka puerto.
bruno tulka plaza.
cora tulka parque.
ana norga lunes.
bruno norga martes.
cora norga miercoles.
uno activa alarma1.
dos activa alarma2.
tres activa alarma3.
'''
    bot.ingest_document_text(text,source='v526_grammar')
    return {p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}

def train(bot):
    rows=[('dora','paquete','norte','jueves'),('eva','caja','sur','viernes'),('luis','archivo','centro','sabado')]
    for i,(p,o,l,t) in enumerate(rows):
        bot.ingest_document_text(f'{p} frobla {o}. {p} tulka {l}. {p} norga {t}.',source=f'v526_train_{i}')

def main():
    before=code_hash(); bot=Bot(allow_extensional_grounding=False);preds=grammar(bot);train(bot)
    promoted=[s for s in bot.document_event_schema_hypotheses.values() if s.get('promoted')]
    triple=[s for s in promoted if len(s['structure']['facts'])==3]
    frozen_support=triple[0].get('support') if len(triple)==1 else None
    successes=0;times=[];member_counts=[]
    for i in range(100):
        t0=perf_counter();r=bot.ingest_document_text(
            f'p{i} frobla o{i}. p{i} tulka l{i}. p{i} norga t{i}. Eso activa a{i}.',
            source=f'v526_target_{i}');times.append((perf_counter()-t0)*1000)
        row=r['sentence_results'][3]
        if row.get('status')=='document_coreference_resolved':
            ref=row['references'][0];ev=ref['antecedent'];event=row['provenance']['materialized_events'][0]
            member_counts.append(len(event['member_fact_ids']))
            successes += ('latent_document_event_v526' in ref.get('criteria',[])
                          and len(event['member_fact_ids'])==3
                          and bot.kb.contains(Atom(preds['{s0} activa {s1}'],(ev,f'a{i}'))))

    control=PairOnlyEventBot(allow_extensional_grounding=False);grammar(control);train(control)
    control_ambiguous=0;control_resolved=0
    for i in range(100):
        r=control.ingest_document_text(
            f'cp{i} frobla co{i}. cp{i} tulka cl{i}. cp{i} norga ct{i}. Eso activa ca{i}.',
            source=f'v526_control_{i}')
        status=r['sentence_results'][3].get('status')
        control_ambiguous += status=='document_coreference_ambiguous'
        control_resolved += status=='document_coreference_resolved'

    ambiguous=0;materialized=0
    for i in range(50):
        r=bot.ingest_document_text(
            f'x{i} frobla xo{i}. x{i} tulka xl{i}. x{i} norga xt{i}. '
            f'y{i} frobla yo{i}. y{i} tulka yl{i}. y{i} norga yt{i}. Eso activa z{i}.',
            source=f'v526_amb_{i}')
        ambiguous += r['sentence_results'][6].get('status')=='document_coreference_ambiguous'
        materialized += r.get('document_events_materialized',0)
    after=code_hash()
    report={
      'version':'0.5.26','experiment':'variable_length_latent_event_cluster',
      'code_hash_before':before,
      'learned':{
        'promoted_event_schemas_at_freeze':len(promoted),
        'promoted_three_fact_schemas_at_freeze':len(triple),
        'three_fact_schema_support_at_freeze':frozen_support,
        'heldout_three_fact_events_resolved':successes,'heldout_cases':100,
        'all_materialized_member_counts_three':all(x==3 for x in member_counts) and len(member_counts)==100,
        'median_document_ms':median(times),
      },
      'controls':{
        'pair_only_ablation_ambiguous':control_ambiguous,
        'pair_only_ablation_resolved':control_resolved,
        'pair_only_cases':100,
        'two_maximal_clusters_abstained':ambiguous,'two_maximal_cases':50,
        'events_materialized_in_ambiguous_cases':materialized,
      },
      'code_hash_after':after,'code_unchanged_during_evaluation':before==after,
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
