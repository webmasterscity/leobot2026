from __future__ import annotations
import hashlib, json, time, tempfile
from pathlib import Path
from leobot.bot import Bot
from leobot.scalable import ScalableBot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]

class UniqueOnlyBot(Bot):
    """Ablation: grounded episodes are usable only when individually unique."""
    def _record_grounding_candidates(self, text, choices):
        if len(choices) != 1:
            return None
        return super()._record_grounding_candidates(text, choices)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def seed(bot, facts):
    for pred,args in facts:
        bot.kb.add(Atom(pred,tuple(args)),'frozen_world')

def run_condition(bot):
    # No frames are supplied here: all training goes through normal Spanish respond().
    episodes=[
        'Bruno reside en Mérida.', 'Eva reside en Barquisimeto.',
        'Lucia labora para Acme.', 'Mario labora para Globex.',
        'Sara tiene bajo su custodia Bicicleta.', 'Omar tiene bajo su custodia Camara.',
        'Elena es progenitora de Luis.', 'Marta es progenitora de Pablo.',
        'Paquete1 va de Caracas a Valencia.', 'Paquete2 va de Merida a Maracay.',
        'Ana no reside en Caracas.', 'Pedro no reside en Valencia.',
        '¿En qué ciudad reside Bruno?', '¿En qué ciudad reside Eva?',
        '¿Para qué empresa labora Lucia?', '¿Para qué empresa labora Mario?',
    ]
    training=[bot.respond(x)['status'] for x in episodes]
    tests=[
        ('Diego reside en Maracay.', Atom('vive',('diego','maracay'))),
        ('Nora labora para Initech.', Atom('trabaja',('nora','initech'))),
        ('Iris tiene bajo su custodia Patineta.', Atom('posee',('iris','patineta'))),
        ('Rosa es progenitora de Tomas.', Atom('progenitor',('rosa','tomas'))),
        ('Paquete3 va de Valencia a Barquisimeto.', Atom('ruta',('paquete3','valencia','barquisimeto'))),
        ('Julia no reside en Maracay.', Atom('!vive',('julia','maracay'))),
    ]
    assert_rows=[]
    for text,expected in tests:
        r=bot.respond(text)
        assert_rows.append({'text':text,'status':r['status'],'correct':bot.kb.contains(expected)})
    query_tests=[
        ('¿En qué ciudad reside Diego?', ('diego','maracay')),
        ('¿Para qué empresa labora Nora?', ('nora','initech')),
    ]
    query_rows=[]
    for text,expected in query_tests:
        r=bot.respond(text)
        got=[tuple(p['atom']['args']) for p in r.get('proofs',[])]
        query_rows.append({'text':text,'status':r['status'],'correct':expected in got})
    return {'training_statuses':training,'assertions':assert_rows,'queries':query_rows}

def legitimate_world():
    return [
        ('vive',('bruno','merida')),('vive',('eva','barquisimeto')),
        ('trabaja',('lucia','acme')),('trabaja',('mario','globex')),
        ('posee',('sara','bicicleta')),('posee',('omar','camara')),
        ('progenitor',('elena','luis')),('progenitor',('marta','pablo')),
        ('ruta',('paquete1','caracas','valencia')),('ruta',('paquete2','merida','maracay')),
        ('!vive',('ana','caracas')),('!vive',('pedro','valencia')),
    ]

def false_semantics(bot):
    seed(bot,[('trabaja',('bruno','acme'))])
    first=bot.respond('Bruno odia Acme.')
    second=bot.respond('Eva odia Globex.')
    return {'first':first['status'],'second':second['status'],
            'false_fact_created':bot.kb.contains(Atom('trabaja',('eva','globex')))}

def ambiguous_case(bot):
    seed(bot,[('vive',('ana','caracas')),('trabaja',('ana','caracas'))])
    before=len(bot.language.examples)
    r=bot.respond('Ana está en Caracas.')
    return {'status':r['status'],'grammar_changed':len(bot.language.examples)!=before}

def disk_noise_case():
    with tempfile.TemporaryDirectory() as td:
        b=ScalableBot(Path(td)/'facts.db',allow_extensional_grounding=True)
        try:
            atoms=(Atom(f'ruido{i%200}',(f'x{i}',f'y{i}')) for i in range(20000))
            b.kb.bulk_add(atoms,'noise')
            seed(b,[('vive',('bruno','merida')),('vive',('eva','barquisimeto'))])
            t=time.perf_counter(); r1=b.respond('Bruno reside en Mérida.'); r2=b.respond('Eva reside en Barquisimeto.'); elapsed=(time.perf_counter()-t)*1000
            out=b.respond('Diego reside en Maracay.')
            return {'noise_facts':20000,'training':[r1['status'],r2['status']],
                    'transfer_status':out['status'],'correct':b.kb.contains(Atom('vive',('diego','maracay'))),
                    'two_training_ms':elapsed}
        finally:b.close()

def contrastive_version_space(bot):
    # No episode is individually unique.  The only hypothesis common to both is vive.
    seed(bot,[('vive',('ana','caracas')),('trabaja',('ana','caracas')),
              ('vive',('bruno','merida')),('posee',('bruno','merida'))])
    r1=bot.respond('Ana está en Caracas.')
    r2=bot.respond('Bruno está en Mérida.')
    r3=bot.respond('Eva está en Valencia.')
    return {'training':[r1['status'],r2['status']], 'transfer':r3['status'],
            'vive_created':bot.kb.contains(Atom('vive',('eva','valencia'))),
            'wrong_trabaja':bot.kb.contains(Atom('trabaja',('eva','valencia'))),
            'wrong_posee':bot.kb.contains(Atom('posee',('eva','valencia')))}

def main():
    frozen=code_hash()
    world=legitimate_world()
    candidate=Bot(grounding_min_support=2,allow_extensional_grounding=True); seed(candidate,world)
    control=Bot(grounded_language=False); seed(control,world)
    unsafe=Bot(grounding_min_support=1,allow_extensional_grounding=True); seed(unsafe,world)
    result={
        'experiment':'v3.1 grounded language internal validation',
        'frozen_code_sha256':frozen,
        'conditions':{
            'candidate_two_independent_supports':run_condition(candidate),
            'memory_only_control_grounding_disabled':run_condition(control),
            'single_support_ablation':run_condition(unsafe),
        },
        'semantic_coincidence':{
            'candidate':false_semantics(Bot(grounding_min_support=2,allow_extensional_grounding=True)),
            'single_support_ablation':false_semantics(Bot(grounding_min_support=1,allow_extensional_grounding=True)),
        },
        'ambiguity':ambiguous_case(Bot(allow_extensional_grounding=True)),
        'contrastive_version_space':{
            'candidate':contrastive_version_space(Bot(allow_extensional_grounding=True)),
            'unique_only_ablation':contrastive_version_space(UniqueOnlyBot(allow_extensional_grounding=True)),
        },
        'disk_noise':disk_noise_case(),
        'limitations':["Internal developer-designed evaluation, not an independent AGI test.",
                       "Grounding assumes relevant entities already exist in factual memory during acquisition.",
                       "Two supports reduce but do not eliminate the possibility of repeated coincidental correlation."],
    }
    out=ROOT/'results_v3'/'v31_grounding.json'; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
