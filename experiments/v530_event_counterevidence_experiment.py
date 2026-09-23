"""V5.30 frozen experiment: explicit counterevidence retracts unsafe event transfer."""
from __future__ import annotations
import hashlib,json,tempfile
from pathlib import Path
from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v530_event_counterevidence.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def ground(bot):
    names=('frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa')
    lines=[]
    for j,name in enumerate(names):
        lines += [f'a{j}x {name} b{j}x.',f'a{j}y {name} b{j}y.',f'a{j}z {name} b{j}z.']
    bot.ingest_document_text(' '.join(lines),source='v530_grammar')
    return {p['surface'].split()[1]:p['predicate'] for p in bot.raw_relation_promotions.values()}


def train_family(bot,names,prefix):
    p,q,r=names
    for i in range(3):
        bot.ingest_document_text(
            f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
            source=f'{prefix}_schema_{i}')


def use_family(bot,names,prefix):
    p,q,r=names
    return bot.ingest_document_text(
        f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso activa {prefix}alarm.',
        source=f'{prefix}_use')


def prepare():
    b=Bot(allow_extensional_grounding=False);preds=ground(b)
    train_family(b,('frobla','tulka','norga'),'f');use_family(b,('frobla','tulka','norga'),'f')
    train_family(b,('peka','rula','soma'),'g');use_family(b,('peka','rula','soma'),'g')
    return b,preds


def main():
    before=code_hash();base,preds=prepare()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);base_path=td/'base.json';base.save(base_path)
        treatment=Bot.load(base_path)
        r=treatment.ingest_document_text(
            'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='v530_counterexample')
        old=r['sentence_results'][3];event_id=old['references'][0]['antecedent']
        feedback=treatment.respond('No, eso se refería a objeto.')
        corrected=treatment.kb.contains(Atom(preds['activa'],('objeto','sirena')))
        orphan_representation=len([x for x in treatment._facts_referencing_entity(event_id)
                                   if x['atom'].pred.startswith('_event_')])
        state=td/'countered.json';treatment.save(state)
        abstained=0
        for i in range(100):
            trial=Bot.load(state)
            rr=trial.ingest_document_text(
                f'n{i} zeta o{i}. n{i} kora l{i}. n{i} miva t{i}. Eso activa a{i}.',source=f'v530_after_{i}')
            abstained += rr['sentence_results'][3].get('status')=='document_coreference_unresolved'
        # Identical system without the counterexample keeps making the transfer.
        unresolved_control=0;resolved_control=0
        for i in range(100):
            trial=Bot.load(base_path)
            rr=trial.ingest_document_text(
                f'c{i} zeta co{i}. c{i} kora cl{i}. c{i} miva ct{i}. Eso activa ca{i}.',source=f'v530_control_{i}')
            resolved_control += rr['sentence_results'][3].get('status')=='document_coreference_resolved'
            unresolved_control += rr['sentence_results'][3].get('status')=='document_coreference_unresolved'
        # Counterevidence against one exact source schema must invalidate a meta
        # representation that previously depended on exactly two sources.
        exact=Bot.load(base_path)
        er=use_family(exact,('frobla','tulka','norga'),'h')
        exact_before=any(m.get('promoted') for m in exact.document_event_meta_hypotheses.values())
        exact_feedback=exact.respond('No, eso se refería a hobj.')
        exact_after=any(m.get('promoted') for m in exact.document_event_meta_hypotheses.values())
        exact_target=exact.ingest_document_text(
            'zz zeta zo. zz kora zl. zz miva zt. Eso activa za.',source='v530_exact_after')
    after=code_hash()
    report={'version':'0.5.30','experiment':'event_representation_counterevidence_and_retraction',
            'code_hash_before':before,
            'learned':{'feedback_status':feedback.get('status'),'corrected_fact_present':corrected,
                       'orphan_event_representation_facts':orphan_representation,
                       'future_meta_transfers_abstained':abstained,'future_cases':100},
            'controls':{'without_counterevidence_resolved':resolved_control,
                        'without_counterevidence_unresolved':unresolved_control,'control_cases':100,
                        'exact_meta_promoted_before_feedback':exact_before,
                        'exact_feedback_status':exact_feedback.get('status'),
                        'exact_schema_contested':exact_feedback.get('schema_contested'),
                        'exact_meta_promoted_after_feedback':exact_after,
                        'heldout_after_exact_retraction_status':exact_target['sentence_results'][3].get('status')},
            'code_hash_after':after,'code_unchanged_during_evaluation':before==after}
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
