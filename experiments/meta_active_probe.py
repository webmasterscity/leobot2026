"""Frozen-engine trial of active evidence selection for ambiguous meta-rules.

The synthetic environment owns the outcomes.  Leobot sees only results of the
trials selected from feasible, unlabeled candidate contexts.  This is a narrow
structural probe, not an open-language or causal-discovery benchmark.
"""
from __future__ import annotations

import hashlib
import json
import resource
import tempfile
import time
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


ROOT = Path(__file__).resolve().parents[1]
FAMILY = 'active_evidence_probe'
OUT = ROOT / 'results_v3' / 'meta_active_probe.json'


def engine_hash():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'leobot').glob('*.py')):
        digest.update(path.name.encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def features(index: int, *, invert_auxiliary: bool = False):
    bits = [(index >> position) & 1 for position in range(3)]
    useful = []
    auxiliary = []
    for position, bit in enumerate(bits):
        center = 10 ** (position + 3) * (1 + index / 10)
        delta = (3.0, 5.0, 7.0)[position]
        useful.extend((center + delta, center - delta) if bit
                      else (center - delta, center + delta))
        auxiliary_center = 1e8 * (position + 1) + index * 100000
        auxiliary_bit = bit ^ int(invert_auxiliary)
        auxiliary.extend((auxiliary_center + 0.01, auxiliary_center - 0.01)
                         if auxiliary_bit else
                         (auxiliary_center - 0.01, auxiliary_center + 0.01))
    return useful + auxiliary


def environment_result(index: int, *, reverse_outcome: bool = False):
    bits = [(index >> position) & 1 for position in range(3)]
    target = 'A' if bits[0] ^ bits[1] ^ bits[2] else 'B'
    if reverse_outcome:
        target = 'B' if target == 'A' else 'A'
    return target


def observe_real_trial(controller, index, vector, *, reverse_outcome=False):
    # The environment returns success for both permitted strategies.  The
    # controller cannot read environment_result or infer an unrun outcome.
    target = environment_result(index, reverse_outcome=reverse_outcome)
    for strategy in ('A', 'B'):
        controller.observe(FAMILY, vector, strategy, success=strategy == target,
                           cost=1 if strategy == target else 9,
                           failure_budget=2)


def score(controller, indices, *, invert_auxiliary, reverse_outcome=False):
    return sum(controller.rank(FAMILY, features(i, invert_auxiliary=invert_auxiliary),
                               ('A', 'B'))['order'][0] ==
               environment_result(i, reverse_outcome=reverse_outcome)
               for i in indices)


def timed(call):
    start = time.perf_counter()
    cpu = time.process_time()
    result = call()
    return result, {'wall_s': round(time.perf_counter()-start, 4),
                    'cpu_s': round(time.process_time()-cpu, 4)}


def run():
    before = engine_hash()

    def train():
        controller = MetaController()
        for i in range(64):
            observe_real_trial(controller, i, features(i))
        return controller

    trained, acquisition_cost = timed(train)
    active = MetaController.from_dict(trained.as_dict())
    passive = MetaController.from_dict(trained.as_dict())
    same_information = MetaController.from_dict(trained.as_dict())
    heldout = range(200, 296)
    initial = score(trained, heldout, invert_auxiliary=True)
    selected = []

    def intervention_rounds():
        for i in (100, 101):
            options = [
                {'features': features(i), 'cost': 1},
                {'features': features(i, invert_auxiliary=True), 'cost': 1},
            ]
            proposal = active.propose_meta_probe(FAMILY, options)
            if proposal.get('status') != 'epistemic_action':
                raise AssertionError(f'No discriminating trial: {proposal}')
            chosen = proposal['chosen_index']
            selected.append({'index':i,'chosen_index':chosen,
                             'information_bits':proposal['chosen']['info_gain_bits'],
                             'ambiguous_hypotheses':proposal['ambiguous_hypotheses']})
            observe_real_trial(active, i, options[chosen]['features'])
            observe_real_trial(same_information, i, options[chosen]['features'])
            observe_real_trial(passive, i, options[0]['features'])

    _, intervention_cost = timed(intervention_rounds)
    active_score = score(active, heldout, invert_auxiliary=True)
    passive_score = score(passive, heldout, invert_auxiliary=True)
    same_info_score = score(same_information, heldout, invert_auxiliary=True)
    fresh_score = score(MetaController(), heldout, invert_auxiliary=True)
    memory_only = MetaController.from_dict(active.as_dict())
    memory_only.routers.clear()
    memory_only.invented_views.clear()
    memory_only_score = score(memory_only, heldout, invert_auxiliary=True)
    incompatible = sum(
        active.rank(FAMILY, features(i, invert_auxiliary=True), ('A', 'B'))['order'][0]
        == ('A' if i & 1 else 'B') for i in heldout)

    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / 'bot.json'
        bot = Bot()
        bot.meta_controller = active
        bot.save(state)
        del bot
        del same_information
        restored = Bot.load(state)
        restarted_score = score(restored.meta_controller, heldout,
                                invert_auxiliary=True)
        persisted_bytes = state.stat().st_size

    counter = MetaController.from_dict(active.as_dict())

    def contrary_experience():
        first_withdrawal = None
        for i in range(300, 316):
            observe_real_trial(counter, i, features(i, invert_auxiliary=True),
                               reverse_outcome=True)
            if first_withdrawal is None and FAMILY not in counter.invented_views:
                first_withdrawal = i
        return first_withdrawal

    first_withdrawal, revision_cost = timed(contrary_experience)
    after_revision = score(counter, heldout, invert_auxiliary=True)
    after = engine_hash()
    report = {
        'experiment': 'active evidence for observationally ambiguous meta-programs',
        'scope': 'synthetic comparator and three-condition strategy task',
        'engine_hash_before': before, 'engine_hash_after': after,
        'engine_unchanged': before == after,
        'training_tasks': 64, 'selected_trials': selected,
        'heldout_tasks': len(heldout), 'baseline_reversed': initial,
        'active_reversed': active_score, 'passive_reversed': passive_score,
        'same_information_reversed': same_info_score,
        'fresh_reversed': fresh_score,
        'memory_only_reversed': memory_only_score,
        'incompatible_structure': incompatible,
        'restarted_reversed': restarted_score,
        'persisted_bytes': persisted_bytes,
        'counterevidence_trials': 16,
        'first_program_withdrawal_at': first_withdrawal,
        'old_rule_after_counterevidence': after_revision,
        'acquisition_cost': acquisition_cost,
        'intervention_cost': intervention_cost,
        'revision_cost': revision_cost,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    if not (report['engine_unchanged'] and active_score >= 90 and
            passive_score <= 6 and same_info_score == active_score and
            restarted_score == active_score and first_withdrawal is not None):
        raise AssertionError(json.dumps(report, ensure_ascii=False))
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                   encoding='utf8')
    return report


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, ensure_ascii=False))
