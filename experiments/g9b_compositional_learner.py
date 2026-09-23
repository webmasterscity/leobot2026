"""G-9b: typed lexical actions learned from explicit SQL demonstrations."""
from __future__ import annotations

import json
import math
import os
import random
import re
import resource
import signal
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g9_structure_gate import signature
from leobot.language import Language, normalize


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (163, 223, 277)
ACTION_NAMES = tuple(sorted(('aggregate', 'filter', 'group', 'join',
                             'limit', 'nested', 'order', 'set')))
FIELDS = ('select',) + tuple(name for name in ACTION_NAMES if name != 'aggregate')
QUOTE = re.compile(r"''[^']*''|\"[^\"]*\"|'[^']*'")
NUMBER = re.compile(r'(?<!\w)\d+(?:[.,]\d+)?(?!\w)')
MAX_CANDIDATES = 1000
PER_QUERY_SECONDS = .010


class QueryDeadline(Exception):
    pass


def bounded_call(func, *args):
    def expired(_signum, _frame):
        raise QueryDeadline()
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, PER_QUERY_SECONDS)
    try:
        return func(*args), False
    except QueryDeadline:
        return None, True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def tokens(text):
    return tuple(NUMBER.sub(' <num> ', QUOTE.sub(' <val> ', normalize(text))).split())


def value_key(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def components(sig):
    out = {'select': value_key((sig[0], sig[1], sig[2]))}
    out.update({name: value_key(sig[3][i]) for i, name in enumerate(ACTION_NAMES)
                if name != 'aggregate'})
    return out


def assemble(selected):
    projection = json.loads(selected['select'])
    aggs = tuple(projection[1])
    actions = tuple(any(agg != 0 for agg in aggs) if name == 'aggregate'
                    else json.loads(selected[name]) for name in ACTION_NAMES)
    return (projection[0], aggs, projection[2], actions)


def ngrams(seq, width=4):
    return {seq[i:i+n] for n in range(1, width+1)
            for i in range(len(seq)-n+1)}


def contrast_phrase(first, second):
    left, right = tokens(first), tokens(second)
    if left == right:
        return None
    changes = [change for change in SequenceMatcher(
        a=left, b=right, autojunk=False).get_opcodes()
        if change[0] != 'equal']
    if len(changes) != 1 or changes[0][0] != 'replace':
        return None
    _, a, b, c, d = changes[0]
    old, new = left[a:b], right[c:d]
    if (not 1 <= len(old) <= 4 or not 1 <= len(new) <= 4 or
        any(value in ('<val>', '<num>') for value in old+new)):
        return None
    return old, new


def grouped_examples(rows):
    by_db = defaultdict(list)
    for row in rows:
        by_db[row['db_id']].append(row)
    return by_db


def educational_model(examples):
    """Only demonstrations enter; never held-out SQL or answer rows."""
    counts = {field: Counter() for field in FIELDS}
    by_db = grouped_examples(examples)
    candidates = defaultdict(set)
    contrast_pairs = 0
    for db, items in sorted(by_db.items()):
        for item in items:
            for field, value in item['fields'].items():
                counts[field][value] += 1
        for i, left in enumerate(items):
            for right in items[i+1:]:
                changed = [field for field in FIELDS
                           if left['fields'][field] != right['fields'][field]]
                if len(changed) != 1:
                    continue
                phrase = contrast_phrase(left['question'], right['question'])
                if phrase is None:
                    continue
                contrast_pairs += 1
                field = changed[0]
                candidates[(field, left['fields'][field], phrase[0])].add((db, left['question']))
                candidates[(field, right['fields'][field], phrase[1])].add((db, right['question']))
    by_phrase = defaultdict(set)
    for field, value, phrase in candidates:
        by_phrase[phrase].add((field, value))
    occurrence = Counter()
    positive = Counter()
    for item in examples:
        for phrase in ngrams(tokens(item['question'])) & by_phrase.keys():
            for field, value in by_phrase[phrase]:
                occurrence[(field, phrase)] += 1
                positive[(field, value, phrase)] += item['fields'][field] == value
    rules = defaultdict(list)
    for (field, value, phrase), origins in sorted(candidates.items()):
        evidence = positive[(field, value, phrase)]
        total = occurrence[(field, phrase)]
        if (evidence < 3 or len({db for db, _ in origins}) < 2 or
            not total or evidence / total < .90):
            continue
        weight = 3 * math.log1p(evidence) * (2 * evidence / total - 1)
        rules[field].append({'phrase': list(phrase), 'value': value,
                             'weight': weight, 'support': evidence,
                             'total': total, 'databases': len({db for db, _ in origins})})
    defaults = {field: sorted(c.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
                for field, c in counts.items()}
    return {'counts': {field: dict(count) for field, count in counts.items()},
            'defaults': defaults, 'rules': dict(rules),
            'contrast_pairs': contrast_pairs, 'candidate_rules': len(candidates),
            'promoted_rules': sum(map(len, rules.values()))}


def predict(model, question):
    seen = ngrams(tokens(question))
    selected = {}
    considered = 0
    supported_fields = 0
    for field in FIELDS:
        counts = model['counts'][field]
        total = sum(counts.values())
        scores = {value: math.log((count+1)/(total+len(counts)))
                  for value, count in counts.items()}
        matched = False
        for rule in model['rules'].get(field, ()):
            if tuple(rule['phrase']) in seen:
                scores[rule['value']] += rule['weight']
                matched = True
        considered += len(scores)
        if matched:
            supported_fields += 1
        selected[field] = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
    if considered > MAX_CANDIDATES:
        return None, considered, 0
    return assemble(selected), considered, supported_fields


def bag_model(examples):
    field_counts = {field: Counter() for field in FIELDS}
    term_counts = {field: defaultdict(Counter) for field in FIELDS}
    global_terms = Counter()
    for item in examples:
        terms = set(tokens(item['question']))
        global_terms.update(terms)
        for field, value in item['fields'].items():
            field_counts[field][value] += 1
            for term in terms:
                term_counts[field][term][value] += 1
    return field_counts, term_counts, global_terms


def bag_predict(model, question):
    counts, terms, global_terms = model
    selected = {}
    considered = 0
    for field in FIELDS:
        frequencies = counts[field]
        total = sum(frequencies.values())
        values = sorted(frequencies)
        scores = {value: math.log((frequencies[value]+1)/(total+len(values)))
                  for value in values}
        for term in set(tokens(question)):
            freq = global_terms[term]
            if freq < 3:
                continue
            for value in values:
                conditional = (terms[field][term][value]+1)/(freq+len(values))
                prior = (frequencies[value]+1)/(total+len(values))
                scores[value] += .5 * math.log(conditional/prior)
        considered += len(values)
        selected[field] = sorted(scores.items(), key=lambda pair: (-pair[1],pair[0]))[0][0]
    return assemble(selected), considered


def language_model(examples):
    language = Language()
    for item in examples:
        language.teach(item['question'], {'act': 'query_structure',
                                         'pred': value_key(item['signature']),
                                         'args': []}, 'sql_demonstration')
    return language


def language_predict(language, question):
    result = language.parse(question)
    if result['status'] != 'parsed':
        return None
    try:
        sig = json.loads(result['frame']['pred'])
        return (sig[0], tuple(sig[1]), sig[2], tuple(sig[3]))
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def percentile(values, fraction):
    sorted_values = sorted(values)
    return sorted_values[int((len(sorted_values)-1)*fraction)] if values else None


def main(seed):
    cpu0, wall0 = time.process_time(), time.monotonic()
    if seed not in SEEDS:
        raise ValueError('Semilla fuera de preregistro')
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        by_db[row['db_id']].setdefault(row['query'].strip().casefold(), row)
    eligible = sorted(db for db, items in by_db.items() if len(items) >= 20)
    rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x69B)
    rng.shuffle(eligible)
    heldout = set(eligible[:max(20, round(.2*len(eligible)))])
    train, test = [], []
    for db in sorted(eligible):
        for row in by_db[db].values():
            item = {'db_id': db, 'question': row['question']}
            if db in heldout:
                # The evaluator owns the gold AST; learners get question only.
                test.append((item, row['sql']))
            else:
                sig, _ = signature(row['sql'])
                train.append({'db_id': db, 'question': row['question'],
                              'signature': sig, 'fields': components(sig)})
    reading_cpu = time.process_time() - cpu0
    train_cpu0 = time.process_time()
    treatment = educational_model(train)
    treatment_cpu = time.process_time() - train_cpu0
    bag_cpu0 = time.process_time()
    bag = bag_model(train)
    bag_cpu = time.process_time() - bag_cpu0
    lang_cpu0 = time.process_time()
    language = language_model(train)
    language_cpu = time.process_time() - lang_cpu0
    memory = defaultdict(set)
    for item in train:
        memory[normalize(item['question'])].add(item['signature'])
    shuffled = []
    by_train_db = grouped_examples(train)
    for db, items in sorted(by_train_db.items()):
        labels = [item['signature'] for item in items]
        rng.shuffle(labels)
        for item, sig in zip(items, labels):
            shuffled.append({**item, 'signature': sig, 'fields': components(sig)})
    shuffled_model = educational_model(shuffled)
    # Save and reload the declarative model, without serializing executable code.
    with tempfile.NamedTemporaryFile(mode='w+', encoding='utf8') as stream:
        json.dump(treatment, stream, ensure_ascii=False, sort_keys=True)
        stream.flush(); stream.seek(0)
        loaded = json.load(stream)
    restart_same = loaded == treatment
    treatment = loaded
    counts = Counter()
    timeouts = Counter()
    family = {'join_filter': Counter(), 'aggregate_order': Counter()}
    latency = []
    candidate_evaluations = 0
    renamed_values_same = True
    for item, gold_sql in test:
        question = item['question']
        tick = time.perf_counter_ns()
        response, timed_out = bounded_call(predict, treatment, question)
        latency.append((time.perf_counter_ns() - tick)/1e6)
        timeouts['treatment'] += timed_out
        predicted, checked, supported = response if response is not None else (None, MAX_CANDIDATES, 0)
        response, timed_out = bounded_call(predict, shuffled_model, question)
        timeouts['shuffled'] += timed_out
        shuffled_pred = response[0] if response is not None else None
        response, timed_out = bounded_call(bag_predict, bag, question)
        timeouts['bag'] += timed_out
        bag_pred = response[0] if response is not None else None
        lang_pred, timed_out = bounded_call(language_predict, language, question)
        timeouts['language'] += timed_out
        stored = memory.get(normalize(question), set())
        memory_pred = next(iter(stored)) if len(stored) == 1 else None
        fresh_pred = (1, (0,), False, (False,)*len(ACTION_NAMES))
        candidate_evaluations += checked
        renamed = NUMBER.sub(' 987654321 ', QUOTE.sub(' "opaque" ', question))
        renamed_response, renamed_timeout = bounded_call(predict, treatment, renamed)
        timeouts['renamed_treatment'] += renamed_timeout
        renamed_values_same &= (renamed_response is not None and
                                renamed_response[0] == predicted)
        gold, _ = signature(gold_sql)
        counts['questions'] += 1
        for name, answer in (('treatment', predicted), ('shuffled', shuffled_pred),
                             ('bag', bag_pred), ('language', lang_pred),
                             ('memory', memory_pred), ('fresh', fresh_pred)):
            counts[name + '_correct'] += answer == gold
            counts[name + '_answered'] += answer is not None
        counts['supported_fields'] += supported
        counts['unsupported_budget'] += predicted is None
        actions = dict(zip(ACTION_NAMES, gold[3]))
        for family_name, present in (('join_filter', actions['join'] and actions['filter']),
                                     ('aggregate_order', actions['aggregate'] and actions['order'])):
            if present:
                family[family_name]['questions'] += 1
                family[family_name]['correct'] += predicted == gold
    best_control = max(counts[k+'_correct'] for k in ('shuffled','bag','language','memory','fresh'))
    total_cpu = time.process_time()-cpu0
    total_wall = time.monotonic()-wall0
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    p95 = percentile(latency, .95)
    within_budget = (total_cpu <= 120 and total_wall <= 180 and
                     peak_rss <= 256*1024 and p95 is not None and p95 <= 10)
    gate = (counts['questions'] and counts['treatment_correct']/counts['questions'] >= .60
            and (counts['treatment_correct'] - best_control)/counts['questions'] >= .15
            and all(group['questions'] >= 10 and group['correct']/group['questions'] >= .50
                    for group in family.values())
            and candidate_evaluations <= MAX_CANDIDATES * counts['questions']
            and restart_same and renamed_values_same and within_budget)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_typed_phrase_actions',
              'preregistration': 'prereg/G-9c-limite-por-consulta.md',
              'detail': 'prereg/G-9b-detalle-del-learner.md',
              'seed': seed, 'engine_tree': h0, 'engine_unchanged': unchanged,
              'training_databases': len(eligible)-len(heldout),
              'heldout_databases': len(heldout), 'training_demonstrations': len(train),
              'test_questions': len(test), 'counts': dict(counts),
              'timeouts_10ms': dict(timeouts),
              'family': {k:dict(v) for k,v in family.items()},
              'contrast_pairs': treatment['contrast_pairs'],
              'candidate_rules': treatment['candidate_rules'],
              'promoted_rules': treatment['promoted_rules'],
              'shuffled_promoted_rules': shuffled_model['promoted_rules'],
              'candidate_evaluations': candidate_evaluations,
              'restart_same': restart_same, 'renamed_values_same': renamed_values_same,
              'reading_cpu_s': round(reading_cpu, 6),
              'treatment_training_cpu_s': round(treatment_cpu, 6),
              'bag_training_cpu_s': round(bag_cpu, 6),
              'language_training_cpu_s': round(language_cpu, 6),
              'rank_p50_ms': round(statistics.median(latency), 6),
              'rank_p95_ms': round(p95, 6),
              'budget_ok': within_budget, 'gate_pass': gate,
              'cpu_total_s': round(time.process_time()-cpu0, 6),
              'wall_total_s': round(time.monotonic()-wall0, 6),
              'max_rss_kib': peak_rss}
    path = ROOT / f'results_v3/g9c_learner_seed{seed}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante ensayo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g9b_compositional_learner 163|223|277')
    main(int(sys.argv[1]))
