"""G-38b differential: candidate against a baseline engine, wider memories.

See prereg/G-38b-tabla-de-atomos-mantenida-por-la-base.md.
python3 -m experiments.g38b_differential BASELINE_ROOT CANDIDATE_ROOT OUT.json N_BASES FIRST_SEED

Memories use arities 1-4, up to 12 sources per atom, removals (also of the
oldest fact of an atom), ``replace`` and queries with repeated variables.  Each
engine answers on memory, after save/load, on disk and on the reopened disk.
The candidate also answers on a disk file whose last writes were made with
direct SQL (as another program would), compared with the same memory built
through the engine.
"""
from __future__ import annotations

import json
import random
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ARITY = {'p': 2, 'q': 2, 'r': 2, 'u': 1, 'w': 3, 'z': 4}
N_QUERIES = 24


def proof_key(p):
    return [p.atom.pred, list(p.atom.args), p.kind, p.id, p.hypothesis, p.contested,
            [proof_key(c) for c in p.children]]


def plan(seed):
    """Operations and queries, drawn once so every store replays the same memory."""
    rng = random.Random(seed)
    ents = [f'e{i}' for i in range(rng.randint(3, 7))]
    # live: op index -> (atom, source) of each present fact; a repeated
    # (atom, source) is the same fact, so it is added but not tracked twice.
    ops, live = [], {}
    for _ in range(rng.randint(30, 200)):
        x = rng.random()
        if live and x < 0.17:
            k = rng.choice(sorted(live))
            if x < 0.12:
                ops.append(('remove', k)); del live[k]
                continue
            new = atom_of(rng, ents)
            if (new, live[k][1]) not in live.values():
                ops.append(('replace', k, new)); live[len(ops) - 1] = (new, live.pop(k)[1])
                continue
        key = (atom_of(rng, ents), f's{rng.randint(0, 11)}')
        ops.append(('add', *key))
        if key not in live.values():
            live[len(ops) - 1] = key
    raw = []
    for _ in range(rng.randint(0, 12)):
        if live and rng.random() < 0.4:
            k = rng.choice(sorted(live)); raw.append(('remove', k)); del live[k]
        else:
            raw.append(('add', atom_of(rng, ents), f'raw{len(raw)}'))
    rules = [('comp', ('t', ('?x', '?z')), [('p', ('?x', '?y')), ('q', ('?y', '?z'))], 'taught')]
    if rng.random() < 0.5:
        rules.append(('un', ('v', ('?x',)), [('u', ('?x',)), ('p', ('?x', '?x'))], 'taught'))
    if rng.random() < 0.5:
        rules.append(('learned:anc:base', ('anc', ('?x', '?y')), [('p', ('?x', '?y'))], 'learned'))
        rules.append(('learned:anc:rec', ('anc', ('?x', '?z')), [('p', ('?x', '?y')), ('anc', ('?y', '?z'))], 'learned'))
    if rng.random() < 0.4:
        rules.append(('w2', ('m', ('?x', '?z')), [('w', ('?x', '?y', '?z')), ('!r', ('?x', '?z'))], 'taught'))
    heads = sorted(set(ARITY) | {'t', 'anc', 'v', 'm'})
    arity = {**ARITY, 't': 2, 'anc': 2, 'v': 1, 'm': 2}
    queries = []
    for _ in range(N_QUERIES):
        pred = rng.choice(heads)
        args = []
        for i in range(arity[pred]):
            y = rng.random()
            args.append(rng.choice(ents) if y < 0.5 else ('?v0' if y < 0.7 else f'?v{i}'))
        queries.append((('!' if rng.random() < 0.2 else '') + pred, tuple(args)))
    return ops, raw, rules, queries


def atom_of(rng, ents):
    pred = rng.choice(sorted(ARITY))
    return (('!' if rng.random() < 0.12 else '') + pred, tuple(rng.choice(ents) for _ in range(ARITY[pred])))


def apply(kb, ops, ids=None):
    from leobot.core import Atom
    ids = ids if ids is not None else {}
    for k, op in enumerate(ops):
        if op[0] == 'add':
            ids[k] = kb.add(Atom(*op[1]), op[2])
        elif op[0] == 'remove':
            kb.remove(ids[op[1]])
        else:
            ids[k] = kb.replace(ids[op[1]], Atom(*op[2]))
    return ids


def apply_raw(path, raw, ids, offset):
    """Direct SQL writes on a closed file, without the engine."""
    db = sqlite3.connect(path)
    for k, op in enumerate(raw):
        if op[0] == 'add':
            (pred, args), source = op[1], op[2]
            cur = db.execute('INSERT INTO facts(pred,base_pred,arity,' + ','.join(f'a{i}' for i in range(len(args))) +
                             ',source,fact_key) VALUES(' + ','.join('?' * (5 + len(args))) + ')',
                             (pred, pred.lstrip('!'), len(args), *args, source, f'raw-{offset + k}'))
            ids[offset + k] = f'f{cur.lastrowid}'
            db.execute('INSERT OR IGNORE INTO fact_entities(fid,entity,base_pred) VALUES ' +
                       ','.join('(?,?,?)' for _ in set(args)),
                       [x for v in sorted(set(args)) for x in (cur.lastrowid, v, pred.lstrip('!'))])
        else:
            db.execute('DELETE FROM fact_entities WHERE fid=?', (int(ids[op[1]][1:]),))
            db.execute('DELETE FROM facts WHERE id=?', (int(ids[op[1]][1:]),))
    db.commit(); db.close()


def add_rules(kb, rules):
    from leobot.core import Atom, Rule
    for rid, head, body, origin in rules:
        kb.add_rule(Rule(rid, Atom(*head), tuple(Atom(*b) for b in body), origin))


def run_base(kb, queries, budget):
    from leobot.core import Atom, Engine
    out = {'matches': [], 'contains': [], 'answers': []}
    for pred, args in queries:
        q = Atom(pred, args)
        out['matches'].append([f['id'] for f in kb.matches(q)])
        out['contains'].append(kb.contains(q))
        r = Engine(kb, max_work=budget).answer(q)
        out['answers'].append({
            'status': r['status'],
            'complete': r['positive']['complete'] and (r['negative'] is None or r['negative']['complete']),
            'positive': [proof_key(p) for p in r['positive']['answers']],
            'negative': [proof_key(p) for p in r['negative']['answers']] if r['negative'] else None})
    return out


def child(root, first, n, with_raw):
    sys.path.insert(0, str(Path(root).resolve()))
    import leobot
    from leobot import Bot
    from leobot.diskkb import SQLiteKnowledgeBase
    for seed in range(first, first + n):
        budget = 200_000 if seed % 3 else 300
        ops, raw, rules, queries = plan(seed)
        bot = Bot(); apply(bot.kb, ops); add_rules(bot.kb, rules)
        rec = {'seed': seed, 'engine': leobot.__file__, 'memory': run_base(bot.kb, queries, budget)}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bot.json'; bot.save(path)
            rec['restart'] = run_base(Bot.load(path).kb, queries, budget)
            db_path = Path(d) / 'k.sqlite'
            kb = SQLiteKnowledgeBase(db_path); ids = apply(kb, ops); add_rules(kb, rules)
            rec['disk'] = run_base(kb, queries, budget); kb.close()
            kb = SQLiteKnowledgeBase(db_path); add_rules(kb, rules)
            rec['disk_reopened'] = run_base(kb, queries, budget); kb.close()
            if with_raw:
                apply_raw(db_path, raw, ids, len(ops))
                kb = SQLiteKnowledgeBase(db_path); add_rules(kb, rules)
                rec['disk_raw'] = run_base(kb, queries, budget); kb.close()
                mem = Bot(); apply(mem.kb, ops + raw); add_rules(mem.kb, rules)
                rec['memory_raw_equivalent'] = run_base(mem.kb, queries, budget)
        print(json.dumps(rec), flush=True)


def compare(x, y, counts, examples, tag):
    for kind in ('matches', 'contains'):
        for i, (a, b) in enumerate(zip(x[kind], y[kind], strict=True)):
            counts['comparisons'] += 1
            if a != b:
                counts['differences'] += 1; examples.append({'where': tag, 'kind': kind, 'query': i, 'base': a, 'cand': b})
    for i, (a, b) in enumerate(zip(x['answers'], y['answers'], strict=True)):
        counts['comparisons'] += 1
        if not a['complete']:
            counts['baseline_incomplete'] += 1
            counts['baseline_incomplete_differences'] += a != b
            continue
        if a != b:
            counts['differences'] += 1; examples.append({'where': tag, 'kind': 'answer', 'query': i, 'base': a, 'cand': b})


def main():
    if sys.argv[1] == '--child':
        child(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5] == '1')
        return
    base_root, cand_root, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    n, first = int(sys.argv[4]), int(sys.argv[5])

    def run(root, with_raw):
        text = subprocess.check_output([sys.executable, '-m', 'experiments.g38b_differential', '--child', root,
                                        str(first), str(n), '1' if with_raw else '0'],
                                       text=True, env={'PYTHONHASHSEED': '0', 'PATH': '/usr/bin:/bin'},
                                       cwd=Path(__file__).resolve().parents[1], timeout=3600)
        return [json.loads(line) for line in text.splitlines()]

    base, cand = run(base_root, False), run(cand_root, True)
    vs_base = {'comparisons': 0, 'differences': 0, 'baseline_incomplete': 0, 'baseline_incomplete_differences': 0}
    raw = {'comparisons': 0, 'differences': 0, 'baseline_incomplete': 0, 'baseline_incomplete_differences': 0}
    examples = []
    for b, c in zip(base, cand, strict=True):
        for store in ('memory', 'restart', 'disk', 'disk_reopened'):
            compare(b[store], c[store], vs_base, examples, f"{b['seed']}:{store}")
        compare(c['memory_raw_equivalent'], c['disk_raw'], raw, examples, f"{b['seed']}:raw")
    report = {'baseline': base[0]['engine'], 'candidate': cand[0]['engine'], 'bases': n, 'first_seed': first,
              'against_baseline': vs_base, 'direct_sql_disk_vs_memory': raw, 'examples': examples[:20]}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'examples'}))
    for e in examples[:3]:
        print(json.dumps(e)[:600])


if __name__ == '__main__':
    main()
