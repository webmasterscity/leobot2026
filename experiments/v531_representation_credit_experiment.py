"""V5.31 frozen experiment: non-circular credit chooses/abstains between event and entity representations."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v531_representation_credit.json'

class AlwaysEventBot(Bot):
    """Ablation: preserve V5.29 transfer but ignore V5.31 representation credit."""
    def _document_event_representation_decision(self,candidate,predicate,slot):
        if candidate.get('mechanism')=='latent_document_event_meta_v527':
            return 'event'
        return super()._document_event_representation_decision(candidate,predicate,slot)

def core_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()

def families(n=106):
    return [(f'm{i:03d}a',f'm{i:03d}b',f'm{i:03d}c') for i in range(n)]

def ground(bot, fams):
    rels=['frobla','tulka','norga','peka','rula','soma','activa']+[x for fam in fams for x in fam]
    lines=[]
    for j,name in enumerate(rels):
        lines += [f'a{j}x {name} b{j}x.',f'a{j}y {name} b{j}y.',f'a{j}z {name} b{j}z.']
    out=bot.ingest_document_text(' '.join(lines),source='v531_grammar')
    assert out['relations_promoted']==len(rels)

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

def prepare(cls,fams):
    b=cls(allow_extensional_grounding=False);ground(b,fams)
    train_family(b,('frobla','tulka','norga'),'f');use_family(b,('frobla','tulka','norga'),'f')
    train_family(b,('peka','rula','soma'),'g');use_family(b,('peka','rula','soma'),'g')
    assert any(x.get('promoted') for x in b.document_event_meta_hypotheses.values())
    assert any(x.get('promoted') for x in b.document_event_reference_hypotheses.values())
    return b

def contrary(bot,prefix,names,confirm=True):
    p,q,r=names
    tail=f' {prefix}obj activa {prefix}alarm.' if confirm else ''
    return bot.ingest_document_text(
        f'{prefix}obj activa {prefix}old. {prefix}u {p} {prefix}obj. '
        f'{prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. '
        f'Eso activa {prefix}alarm.'+tail,source=f'v531_{prefix}')

def main():
    fams=families()
    before=core_hash()
    treatment=prepare(Bot,fams)
    control=prepare(AlwaysEventBot,fams)

    # One independently confirmed surprise must make the treatment cautious.
    first_t=contrary(treatment,'surprise',fams[0],confirm=True)
    first_c=contrary(control,'surprise',fams[0],confirm=True)
    choice=next(iter(treatment.document_event_choice_hypotheses.values()))
    assert choice['event_support']==2 and choice['independent_support']==1 and choice['decision']=='abstain'
    assert any(a.get('event')=='document_event_representation_auto_revised' for a in treatment.kb.audit)

    cautious=0; control_false=0
    for i in range(100):
        rt=contrary(treatment,f'c{i}',fams[i+1],confirm=False)
        rc=contrary(control,f'c{i}',fams[i+1],confirm=False)
        if rt['sentence_results'][4]['status'] in ('document_coreference_ambiguous','document_coreference_unresolved'):
            cautious+=1
        row=rc['sentence_results'][4]
        if row['status']=='document_coreference_resolved' and str(row['args'][0]).startswith('event_'):
            control_false+=1

    # Fresh pair: four predicate-disjoint confirmations must eventually select
    # the entity hypothesis directly rather than merely abstaining.
    selective=prepare(Bot,fams)
    selective_control=prepare(AlwaysEventBot,fams)
    for i in range(4):
        contrary(selective,f's{i}',fams[i],confirm=True)
        contrary(selective_control,f's{i}',fams[i],confirm=True)
    selected=next(iter(selective.document_event_choice_hypotheses.values()))
    assert selected['event_support']==2 and selected['independent_support']==4 and selected['decision']=='independent'
    entity_correct=0; ablation_event=0
    for i in range(100):
        fam=fams[i+4]
        rt=contrary(selective,f't{i}',fam,confirm=False)
        rc=contrary(selective_control,f't{i}',fam,confirm=False)
        row_t=rt['sentence_results'][4]; row_c=rc['sentence_results'][4]
        if row_t['status']=='document_coreference_resolved' and row_t['args'][0]==f't{i}obj':
            entity_correct+=1
        if row_c['status']=='document_coreference_resolved' and str(row_c['args'][0]).startswith('event_'):
            ablation_event+=1
    after=core_hash(); assert before==after
    report={
        'version':'0.5.31','experiment':'noncircular_representation_credit',
        'code_hash':before,'code_frozen':True,
        'one_surprise':{'treatment_decision':choice['decision'],'event_support':choice['event_support'],
                        'independent_support':choice['independent_support'],
                        'heldout_safe_abstentions':cautious,'heldout_cases':100,
                        'ablation_false_event_transfers':control_false},
        'four_confirmations':{'treatment_decision':selected['decision'],
                              'event_support':selected['event_support'],
                              'independent_support':selected['independent_support'],
                              'heldout_entity_resolved':entity_correct,'heldout_cases':100,
                              'ablation_false_event_transfers':ablation_event},
        'initial_auto_revision': any(a.get('event')=='document_event_representation_auto_revised' for a in treatment.kb.audit),
        'claim':'bounded autonomous representation selection; not AGI/ASI'
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
