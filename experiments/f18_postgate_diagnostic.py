"""Post-gate diagnosis of rejected F-18 candidate on already seen validation."""
from __future__ import annotations

import json
import resource
import statistics
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path

from experiments.f18_order_learner_dev import (
    EXPECTED_SOURCE, metric, partition, predict, structural_features, subset_score,
)
from experiments.f18_pawsx_inventory import rows
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    old = json.loads((ROOT / 'results_v3' / 'f18_order_dev.json').read_text())
    if old['candidate_gate_passed'] or old['engine_tree'] != tree:
        raise RuntimeError('Diagnóstico solo después de la puerta negativa')
    data = rows()
    digest = sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()).hexdigest()
    if digest != EXPECTED_SOURCE:
        raise RuntimeError('Fuente cambió')
    validation = partition(data, tree)['validation']
    treated = old['treatment']['best_raw']['program']
    baseline = old['no_order']['best_raw']['program']
    prepared = []
    times = []
    confusion = Counter()
    for row in validation:
        tick = time.perf_counter()
        feature = structural_features(row['sentence1'], row['sentence2'])
        answer = predict(treated, feature)
        times.append((time.perf_counter() - tick) * 1000)
        prepared.append((feature, row['label']))
        confusion[(row['label'], answer)] += 1
    stratified = {}
    for subset in ('high_overlap', 'same_bag'):
        stratified[subset] = {'treatment': subset_score(treated, prepared, subset),
                              'no_order': subset_score(baseline, prepared, subset)}
    output = {
        'kind': 'diagnostic_not_promotion', 'engine_tree': tree,
        'validation_rows': len(validation), 'treatment': metric(treated, prepared),
        'no_order': metric(baseline, prepared), 'strata': stratified,
        'confusion': {gold + '→' + str(pred): count
                      for (gold, pred), count in sorted(confusion.items())},
        'p50_ms': round(statistics.median(times), 6),
        'p95_ms': round(sorted(times)[(95 * len(times) + 99) // 100 - 1], 6),
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    path = ROOT / 'results_v3' / 'f18_postgate_diagnostic.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
