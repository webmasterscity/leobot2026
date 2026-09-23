from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def seed(bot, rows):
    r=None
    for x in rows: r=bot.respond(x)
    assert r['status']=='raw_relation_learned'
    return r['predicate'],r

def teach_fronted(bot, fronted, insitu):
    r=bot.respond(f'"{fronted}" significa lo mismo que "{insitu}".')
    assert r['status']=='paraphrase_learned'
    return r

def establish_meta(bot):
    p1,_=seed(bot,['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora'])
    a=teach_fronted(bot,'¿qué entrega ana a luis?','¿ana entrega qué a luis?')
    assert not a['question_transform']['promoted']
    p2,_=seed(bot,['dora envia carta hacia raul','eva envia paquete hacia sara','fede envia llave hacia tomas'])
    b=teach_fronted(bot,'¿qué envia dora hacia raul?','¿dora envia qué hacia raul?')
    assert b['question_transform']['promoted']
    return p1,p2

def main():
    frozen=code_hash(); start=time.perf_counter()
    bot=Bot(allow_extensional_grounding=False)
    establish_meta(bot)
    p3,learned=seed(bot,['gina transporta libro hasta hugo','ines transporta mapa hasta jorge','kira transporta llave hasta leo'])
    assert learned.get('question_constructions')==1
    successes=0; no_mutation=0
    for i in range(100):
        before=bot.kb.stats()['facts']
        stored=bot.respond(f'p{i} transporta objeto{i} hasta r{i}')
        assert stored['status']=='stored'
        mid=bot.kb.stats()['facts']
        out=bot.respond('¿qué?')
        if (out.get('status')=='bindings' and out.get('contextual_ellipsis')
                and out.get('answer_pos')==1
                and any(p['atom']['pred']==p3 and p['atom']['args']==[f'p{i}',f'objeto{i}',f'r{i}'] for p in out.get('proofs',[]))):
            successes+=1
        if bot.kb.stats()['facts']==mid==before+1:
            no_mutation+=1

    control=Bot(allow_extensional_grounding=False)
    establish_meta(control)
    p3c,learned=seed(control,['gina transporta libro hasta hugo','ines transporta mapa hasta jorge','kira transporta llave hasta leo'])
    assert learned.get('question_constructions')==1
    control_hits=0
    for i in range(100):
        control.respond(f'c{i} transporta cosa{i} hasta z{i}')
        control.discourse_facts=[]; control.last_fact=None
        r=control.respond('¿qué?')
        if r.get('status')=='bindings': control_hits+=1

    # Topic isolation: a newer relation without a matching query grammar must block
    # fallback to an older transport fact even though that older relation knows ¿qué?.
    topic=Bot(allow_extensional_grounding=False)
    establish_meta(topic)
    seed(topic,['gina transporta libro hasta hugo','ines transporta mapa hasta jorge','kira transporta llave hasta leo'])
    topic.respond('dora transporta carta hasta raul')
    seed(topic,['proyecto alfa ocurre lunes','proyecto beta ocurre martes','proyecto gamma ocurre miercoles'])
    topic_blocked=0
    for i in range(20):
        topic.respond(f'proyecto q{i} ocurre d{i}')
        r=topic.respond('¿qué?')
        if r.get('status')!='bindings': topic_blocked+=1

    # Same cue, two grounded answer roles -> abstain rather than prefer the more
    # lexically specific stored construction.
    amb=Bot(allow_extensional_grounding=False)
    p,_=seed(amb,['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora'])
    teach_fronted(amb,'¿qué entrega ana a luis?','¿ana entrega qué a luis?')
    teach_fronted(amb,'¿qué destino tiene ana con caja?','¿ana entrega caja a qué?')
    ambiguous=0
    for i in range(50):
        amb.respond(f'x{i} entrega y{i} a z{i}')
        r=amb.respond('¿qué?')
        if r.get('status')=='contextual_query_ambiguous': ambiguous+=1

    result={
        'version':'V5.17',
        'mechanism':'grounded_query_ellipsis_from_discourse_focus',
        'frozen_code_sha256':frozen,
        'final_code_sha256':code_hash(),
        'meta_transferred_relation':p3,
        'treatment_contextual_queries':successes,
        'treatment_query_nonmutation':no_mutation,
        'control_without_discourse_hits':control_hits,
        'newer_topic_blocks_older_fallback':topic_blocked,
        'newer_topic_cases':20,
        'ambiguous_same_cue_rejected':ambiguous,
        'ambiguous_cases':50,
        'elapsed_ms':round((time.perf_counter()-start)*1000,3),
    }
    assert successes==100 and no_mutation==100 and control_hits==0
    assert topic_blocked==20 and ambiguous==50 and frozen==result['final_code_sha256']
    (ROOT/'results_v3'/'v517_contextual_query.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
