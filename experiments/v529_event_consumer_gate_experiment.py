"""V5.29 diagnostic: measure the consumer gate's marginal effect.

Disabling this gate does not disable later representation decisions. A zero
false-positive count in the control therefore cannot prove this gate caused
the abstentions.
"""
from __future__ import annotations
import hashlib,json,tempfile
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v529_event_consumer_gate.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


class WithoutConsumerGateBot(Bot):
    def _document_event_reference_gate_allows(self,candidate,predicate,slot):
        return True


def ground(bot):
    names=('frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa','rechaza')
    lines=[]
    for j,name in enumerate(names):
        lines += [f'a{j}x {name} b{j}x.',f'a{j}y {name} b{j}y.',f'a{j}z {name} b{j}z.']
    bot.ingest_document_text(' '.join(lines),source='v529_grammar')


def train_family(bot,names,prefix):
    p,q,r=names
    for i in range(3):
        bot.ingest_document_text(
            f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
            source=f'{prefix}_schema_{i}')


def use_family(bot,names,prefix,consumer='activa'):
    p,q,r=names
    return bot.ingest_document_text(
        f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso {consumer} {prefix}alarm.',
        source=f'{prefix}_use')


def prepare(cls=Bot):
    b=cls(allow_extensional_grounding=False);ground(b)
    train_family(b,('frobla','tulka','norga'),'f');use_family(b,('frobla','tulka','norga'),'f')
    train_family(b,('peka','rula','soma'),'g');use_family(b,('peka','rula','soma'),'g')
    return b


def main():
    before=code_hash();b=prepare(Bot)
    gates=[g for g in b.document_event_reference_hypotheses.values() if g.get('promoted')]
    with tempfile.TemporaryDirectory() as td:
        state=Path(td)/'treatment.json';b.save(state)
        allowed=blocked=0;times=[]
        for i in range(100):
            trial=Bot.load(state);t0=perf_counter()
            r=trial.ingest_document_text(
                f'n{i} zeta o{i}. n{i} kora l{i}. n{i} miva t{i}. Eso activa a{i}.',source=f'v529_allowed_{i}')
            times.append((perf_counter()-t0)*1000)
            allowed += r['sentence_results'][3].get('status')=='document_coreference_resolved'
            trial=Bot.load(state)
            r=trial.ingest_document_text(
                f'x{i} zeta xo{i}. x{i} kora xl{i}. x{i} miva xt{i}. Eso rechaza q{i}.',source=f'v529_blocked_{i}')
            blocked += r['sentence_results'][3].get('status')=='document_coreference_unresolved'
        # Ablation: same learned meta-topology, but disable the V5.29 gate.
        control=WithoutConsumerGateBot.load(state)
        control_path=Path(td)/'control.json';control.save(control_path)
        false_positive=0
        for i in range(100):
            trial=WithoutConsumerGateBot.load(control_path)
            r=trial.ingest_document_text(
                f'c{i} zeta co{i}. c{i} kora cl{i}. c{i} miva ct{i}. Eso rechaza cq{i}.',source=f'v529_control_{i}')
            false_positive += r['sentence_results'][3].get('status')=='document_coreference_resolved'
    after=code_hash()
    report={'version':'0.5.29','experiment':'event_consumer_role_gate',
            'code_hash_before':before,
            'learned':{'promoted_gates':len(gates),'gate_support':gates[0].get('support') if len(gates)==1 else None,
                       'validated_consumer_resolved':allowed,'validated_cases':100,
                       'unvalidated_consumer_abstained':blocked,'unvalidated_cases':100,
                       'median_document_ms':median(times)},
            'controls':{'consumer_gate_disabled_false_resolutions':false_positive,
                        'consumer_gate_disabled_cases':100,
                        'incremental_gate_effect_demonstrated':false_positive>0},
            'interpretation':('The consumer gate has a measurable marginal effect in this setup.'
                              if false_positive>0 else
                              'A separate representation decision also blocks these cases; this ablation does not isolate the consumer gate.'),
            'code_hash_after':after,'code_unchanged_during_evaluation':before==after}
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
