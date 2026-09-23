"""V4.7: retire extensional alias guessing from the default operational path."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from leobot.bot import Bot
from leobot.core import Atom,KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]; RESULT=ROOT/'results_v3'/'v47_safe_grounding_retirement.json'
def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def seed(bot, suffix=''):
    bot.kb.add(Atom('trabaja',(f'bruno{suffix}',f'acme{suffix}')),'seed')
    bot.kb.add(Atom('trabaja',(f'eva{suffix}',f'globex{suffix}')),'seed')
    return bot

def trial(word, suffix=''):
    safe=seed(Bot(KnowledgeBase()),suffix); legacy=seed(Bot(KnowledgeBase(),allow_extensional_grounding=True),suffix)
    texts=[f'bruno{suffix} {word} acme{suffix}',f'eva{suffix} {word} globex{suffix}',f'luis{suffix} {word} initech{suffix}']
    safe_reports=[safe.respond(t) for t in texts]; legacy_reports=[legacy.respond(t) for t in texts]
    false_atom=Atom('trabaja',(f'luis{suffix}',f'initech{suffix}'))
    safe_false=safe.kb.contains(false_atom); legacy_false=legacy.kb.contains(false_atom)
    safe_primitive=any(safe.kb.contains(Atom(v['predicate'],(f'luis{suffix}',f'initech{suffix}'))) for v in safe.raw_relation_promotions.values())
    return safe_false,legacy_false,safe_primitive,safe_reports[-1].get('status'),legacy_reports[-1].get('status')

def main():
    before=code_hash(); rows=[]
    for i in range(20): rows.append(trial(f'verbo{i}',str(i)))
    after=code_hash()
    report={'version':'0.4.7','experiment':'retire_underdetermined_extensional_grounding',
            'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'trials':len(rows),
            'default_false_existing_predicate_facts':sum(r[0] for r in rows),
            'legacy_false_existing_predicate_facts':sum(r[1] for r in rows),
            'default_distinct_primitives_learned':sum(r[2] for r in rows),
            'default_final_statuses':sorted({r[3] for r in rows}),
            'legacy_final_statuses':sorted({r[4] for r in rows}),
            'operational_default_allow_extensional_grounding':False,
            'legacy_reproduction_requires_explicit_opt_in':True,
            'interpretation':'La coincidencia extensional sola no identifica el significado de una palabra nueva; el camino por defecto conserva una relacion nueva como primitiva separada en vez de reetiquetar hechos existentes.',
            'limits':['Una primitiva opaca tampoco establece equivalencia semantica con otros predicados.','Falta un mecanismo seguro para aprender sinonimia/equivalencia mediante evidencia definicional o contrastiva suficiente.','No demuestra AGI/ASI.']}
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
