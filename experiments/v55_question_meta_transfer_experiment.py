"""V5.5 internal experiment: transfer a learned question transformation.

This is an internal development validation, not an independent AGI evaluation.
The learner is frozen during the held-out phase: no source edits occur between
training and evaluation.  The control receives only one predicate supporting the
abstract question transformation, so it must not promote the meta-schema.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]


def code_hash() -> str:
    h = hashlib.sha256()
    for path in sorted((ROOT / 'leobot').glob('*.py')):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def seed_relation(bot: Bot, rows: list[str]) -> tuple[str, dict]:
    report = None
    for text in rows:
        report = bot.respond(text)
    assert report and report['status'] == 'raw_relation_learned', report
    return report['predicate'], report


def teach_fronted(bot: Bot, fronted: str, insitu: str) -> dict:
    report = bot.respond(f'"{fronted}" significa lo mismo que "{insitu}".')
    assert report['status'] == 'paraphrase_learned', report
    return report


def train_first_support(bot: Bot) -> dict:
    seed_relation(bot, [
        'ana entrega caja a luis',
        'bea entrega libro a mario',
        'cora entrega mapa a nora',
    ])
    return teach_fronted(bot, '¿qué entrega ana a luis?', '¿ana entrega qué a luis?')


def train_second_support(bot: Bot) -> dict:
    seed_relation(bot, [
        'dora envia carta hacia raul',
        'eva envia paquete hacia sara',
        'fede envia llave hacia tomas',
    ])
    return teach_fronted(bot, '¿qué envia dora hacia raul?', '¿dora envia qué hacia raul?')


def seed_target(bot: Bot) -> tuple[str, dict]:
    return seed_relation(bot, [
        'gina transporta libro hasta hugo',
        'ines transporta mapa hasta jorge',
        'kira transporta llave hasta leo',
    ])


def add_heldout_facts(bot: Bot, n: int = 100) -> list[tuple[str, str, str]]:
    rows = []
    for i in range(n):
        a = f'persona{i:03d}'
        obj = f'objeto{i:03d}'
        dst = f'destino{i:03d}'
        result = bot.respond(f'{a} transporta {obj} hasta {dst}')
        assert result['status'] in ('stored', 'schema_fact_stored'), result
        rows.append((a, obj, dst))
    return rows


def evaluate_fronted(bot: Bot, pred: str, rows: list[tuple[str, str, str]]) -> dict:
    correct = unrecognized = mutated = 0
    before = bot.kb.stats()['facts']
    for a, obj, dst in rows:
        answer = bot.respond(f'¿qué transporta {a} hasta {dst}?')
        if answer.get('status') == 'unrecognized':
            unrecognized += 1
            continue
        if answer.get('status') == 'bindings':
            proofs = answer.get('proofs', [])
            if any(p.get('atom', {}).get('pred') == pred and
                   p.get('atom', {}).get('args') == [a, obj, dst] for p in proofs):
                correct += 1
    after = bot.kb.stats()['facts']
    mutated = after - before
    return {'correct': correct, 'unrecognized': unrecognized, 'fact_delta': mutated}


def run() -> dict:
    before_hash = code_hash()

    educated = Bot(allow_extensional_grounding=False)
    first = train_first_support(educated)
    assert first['question_transform']['support'] == 1
    assert first['question_transform']['promoted'] is False
    second = train_second_support(educated)
    assert second['question_transform']['support'] == 2
    assert second['question_transform']['promoted'] is True
    target_pred, target_promotion = seed_target(educated)
    assert target_promotion.get('question_constructions') == 1
    heldout = add_heldout_facts(educated, 100)
    educated_eval = evaluate_fronted(educated, target_pred, heldout)

    # One-support control: same target language and facts, but insufficient
    # independent evidence to promote the abstract question transformation.
    control = Bot(allow_extensional_grounding=False)
    control_first = train_first_support(control)
    assert control_first['question_transform']['support'] == 1
    control_pred, control_promotion = seed_target(control)
    assert control_promotion.get('question_constructions') == 0
    control_rows = add_heldout_facts(control, 100)
    control_eval = evaluate_fronted(control, control_pred, control_rows)

    # Topology negative: a binary assertion must not inherit the ternary transform.
    binary_pred, binary_promotion = seed_relation(educated, [
        'alfa enlaza beta', 'gamma enlaza delta', 'epsilon enlaza zeta'
    ])
    binary_question = educated.respond('¿qué enlaza alfa?')

    promoted = [v for v in educated.question_transform_hypotheses.values() if v.get('promoted')]
    after_hash = code_hash()
    result = {
        'version': '0.5.5',
        'mechanism': 'predicate-independent question transformation meta-schema',
        'educated': {
            'support_after_first_predicate': first['question_transform']['support'],
            'promoted_after_first_predicate': first['question_transform']['promoted'],
            'support_after_second_predicate': second['question_transform']['support'],
            'promoted_after_second_predicate': second['question_transform']['promoted'],
            'target_question_constructions_added_without_target_question_example': target_promotion.get('question_constructions'),
            'heldout': educated_eval,
            'promoted_transform_count': len(promoted),
        },
        'one_support_control': {
            'target_question_constructions_added': control_promotion.get('question_constructions'),
            'heldout': control_eval,
        },
        'topology_negative': {
            'predicate': binary_pred,
            'arity': binary_promotion.get('arity'),
            'question_constructions_added': binary_promotion.get('question_constructions'),
            'fronted_question_status': binary_question.get('status'),
        },
        'safety': {
            'allow_extensional_grounding': educated.allow_extensional_grounding,
            'question_fact_delta': educated_eval['fact_delta'],
        },
        'code_hash_before': before_hash,
        'code_hash_after': after_hash,
        'code_unchanged_during_experiment': before_hash == after_hash,
        'claim_boundary': 'Internal transfer evidence only; does not demonstrate general language understanding or AGI.',
    }
    assert educated_eval == {'correct': 100, 'unrecognized': 0, 'fact_delta': 0}, result
    assert control_eval['correct'] == 0 and control_eval['unrecognized'] == 100 and control_eval['fact_delta'] == 0, result
    assert binary_promotion.get('question_constructions') == 0, result
    assert binary_question.get('status') == 'unrecognized', result
    assert before_hash == after_hash, result
    return result


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
