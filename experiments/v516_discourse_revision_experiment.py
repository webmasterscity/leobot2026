from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]


def code_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def ground_event(bot: Bot):
    last=None
    for text in (
        'evento alfa sera lunes en sala norte',
        'evento beta sera martes en sala azul',
        'evento gamma sera miercoles en salon central',
    ):
        last=bot.respond(text)
    assert last['status']=='raw_relation_learned'
    return last['predicate']


def ground_delivery(bot: Bot):
    last=None
    for text in (
        'ana entrega caja a luis',
        'bea entrega libro a mario',
        'cora entrega mapa a nora',
    ):
        last=bot.respond(text)
    assert last['status']=='raw_relation_learned'
    return last['predicate']


def main():
    frozen=code_hash(); started=time.perf_counter()

    treatment=Bot(allow_extensional_grounding=False)
    event=ground_event(treatment); delivery=ground_delivery(treatment)
    prior_topic_ok=0; untouched_ok=0; multi_role_ok=0
    for i in range(100):
        old=(f'e{i}',f'd{i}',f'l{i}')
        new=(f'e{i}',f'nd{i}',f'nl{i}')
        treatment.respond(f'evento {old[0]} sera {old[1]} en {old[2]}')
        treatment.respond(f'p{i} entrega o{i} a r{i}')
        report=treatment.respond(f'No, evento {new[0]} sera {new[1]} en {new[2]}.')
        if (report.get('status')=='corrected_contextually'
                and report.get('changed_slots')==[1,2]
                and treatment.kb.contains(Atom(event,new))
                and not treatment.kb.contains(Atom(event,old))):
            prior_topic_ok+=1
        if treatment.kb.contains(Atom(delivery,(f'p{i}',f'o{i}',f'r{i}'))):
            untouched_ok+=1
        if report.get('mechanism')=='grounded_multi_slot_revision_v516':
            multi_role_ok+=1

    no_context=Bot(allow_extensional_grounding=False)
    event_c=ground_event(no_context); ground_delivery(no_context)
    control_corrected=0
    for i in range(100):
        old=(f'ce{i}',f'cd{i}',f'cl{i}')
        new=(f'ce{i}',f'cnd{i}',f'cnl{i}')
        no_context.respond(f'evento {old[0]} sera {old[1]} en {old[2]}')
        last=no_context.respond(f'cp{i} entrega co{i} a cr{i}')['id']
        # Ablation: preserve the KB and language but remove the earlier event from
        # conversational focus, leaving only the intervening topic available.
        no_context.discourse_facts=[last]; no_context.last_fact=last
        report=no_context.respond(f'No, evento {new[0]} sera {new[1]} en {new[2]}.')
        if report.get('status')=='corrected_contextually':
            control_corrected+=1

    elliptical=Bot(allow_extensional_grounding=False)
    event_e=ground_event(elliptical)
    elliptical_ok=0
    for i in range(100):
        old=(f'x{i}',f'a{i}',f'b{i}')
        new=(f'x{i}',f'na{i}',f'nb{i}')
        elliptical.respond(f'evento {old[0]} sera {old[1]} en {old[2]}')
        report=elliptical.respond(f'No, sera {new[1]} en {new[2]}.')
        if (report.get('status')=='corrected_contextually'
                and report.get('changed_slots')==[1,2]
                and elliptical.kb.contains(Atom(event_e,new))
                and not elliptical.kb.contains(Atom(event_e,old))):
            elliptical_ok+=1

    polarity=Bot(allow_extensional_grounding=False)
    event_p=ground_event(polarity)
    polarity_ok=0
    for i in range(100):
        args=(f'n{i}',f'd{i}',f'l{i}')
        polarity.respond(f'evento {args[0]} sera {args[1]} en {args[2]}')
        report=polarity.respond(f'No, evento {args[0]} no sera {args[1]} en {args[2]}.')
        if (report.get('status')=='corrected_contextually'
                and report.get('polarity_changed')
                and polarity.kb.contains(Atom('!'+event_p,args))
                and not polarity.kb.contains(Atom(event_p,args))):
            polarity_ok+=1

    ambiguity=Bot(allow_extensional_grounding=False)
    for text in (
        'equipo alfa usa llave roja en zona norte',
        'equipo beta usa llave azul en zona sur',
        'equipo gamma usa llave blanca en zona este',
    ):
        learned=ambiguity.respond(text)
    amb_pred=learned['predicate']; ambiguous_ok=0
    for i in range(50):
        first=(f's{i}',f'a{i}',f'x{i}'); second=(f's{i}',f'b{i}',f'y{i}')
        ambiguity.respond(f'equipo {first[0]} usa llave {first[1]} en zona {first[2]}')
        ambiguity.respond(f'equipo {second[0]} usa llave {second[1]} en zona {second[2]}')
        report=ambiguity.respond(f'No, equipo s{i} usa llave c{i} en zona z{i}.')
        if (report.get('status')=='correction_ambiguous'
                and ambiguity.kb.contains(Atom(amb_pred,first))
                and ambiguity.kb.contains(Atom(amb_pred,second))):
            ambiguous_ok+=1

    result={
        'version':'V5.16',
        'mechanism':'grounded_and_anchored_multi_role_discourse_revision',
        'frozen_code_sha256':frozen,
        'final_code_sha256':code_hash(),
        'treatment_prior_topic_revisions':prior_topic_ok,
        'treatment_unrelated_fact_retention':untouched_ok,
        'treatment_grounded_multi_role_path':multi_role_ok,
        'control_without_prior_discourse_revisions':control_corrected,
        'elliptical_two_role_revisions':elliptical_ok,
        'explicit_polarity_revisions':polarity_ok,
        'ambiguous_cases_safely_rejected':ambiguous_ok,
        'ambiguous_cases_total':50,
        'elapsed_ms':round((time.perf_counter()-started)*1000,3),
    }
    assert prior_topic_ok==100 and untouched_ok==100 and multi_role_ok==100
    assert control_corrected==0
    assert elliptical_ok==100 and polarity_ok==100 and ambiguous_ok==50
    assert frozen==result['final_code_sha256']
    out=ROOT/'results_v3'/'v516_discourse_revision.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
