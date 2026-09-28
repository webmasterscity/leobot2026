"""G98: frozen-vocabulary continued education and localized evidence supervision."""
import time
BOOT = time.process_time()
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import random
import resource
import subprocess
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from experiments.g97_neural import features, encode_numpy, OUT as OLD
from experiments.g97_backups import ABSTAINED
from experiments.g98_route import EvidenceRoute
from experiments.g57_kiosco import businesses, contains
from experiments.g68_confianza import TRAIN, isotonic
from experiments.g60_calibrar_confianza import naive_bayes, score
from experiments.g74_relation_coverage import ENGINE, BASE_SHA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.leobot-data/g98'


def partition(group):
    fold = int(hashlib.sha256(group.encode()).hexdigest(), 16) % 5
    return 'calibration' if fold == 0 else 'validation' if fold == 1 else 'train'


def tensor(rows):
    result = torch.zeros((len(rows), max(1, max(map(len, rows)))), dtype=torch.long)
    for i, row in enumerate(rows):
        if row: result[i, :len(row)] = torch.tensor(row, dtype=torch.long)
    return result


class Encoder(nn.Module):
    def __init__(self, vocabulary_size, weights=None):
        super().__init__()
        self.embedding = nn.EmbeddingBag(vocabulary_size, 64, mode='mean', padding_idx=0)
        self.q, self.a = nn.Linear(64, 64), nn.Linear(64, 64)
        self.empty = nn.Linear(64, 1)
        with torch.no_grad():
            self.empty.weight.zero_(); self.empty.bias.zero_()
            if weights is not None:
                self.embedding.weight.copy_(torch.from_numpy(weights['embedding']))
                for side in ('q', 'a'):
                    getattr(self, side).weight.copy_(torch.from_numpy(weights[side+'_weight'].T))
                    getattr(self, side).bias.copy_(torch.from_numpy(weights[side+'_bias']))

    def forward(self, rows, side):
        values = torch.tanh(getattr(self, side)(self.embedding(rows)))
        return F.normalize(values, dim=1)*rows.ne(0).any(dim=1, keepdim=True)

    def null(self, vectors):
        return self.empty(vectors)/.1

    def export(self):
        return {'embedding': self.embedding.weight.detach().numpy().copy(),
                **{s+'_weight': getattr(self, s).weight.detach().numpy().T.copy() for s in ('q', 'a')},
                **{s+'_bias': getattr(self, s).bias.detach().numpy().copy() for s in ('q', 'a')},
                'null_weight': self.empty.weight.detach().numpy()[0].copy(),
                'null_bias': self.empty.bias.detach().numpy().copy()}


def selection_loss(logits, targets, valid):
    mask = torch.cat((valid, torch.ones((len(valid), 1), dtype=torch.bool)), 1)
    values = logits.masked_fill(~mask, -1e9)
    return (values.logsumexp(1)-values.masked_fill(~targets, -1e9).logsumexp(1)).mean()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def check_budget():
    if time.process_time()-BOOT > 900: raise TimeoutError('G98 education CPU budget')
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 3*1024**2:
        raise MemoryError('G98 RSS budget')


def prepare(bot, vocab, weights):
    from experiments.g78_localized_education import segments, locate, SOURCE_SHA
    path = ROOT/'.leobot-data/sqac_train.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SOURCE_SHA
    data = json.loads(path.read_text())['data']
    excluded = Counter(); available = []
    for article in data:
        for paragraph in article['paragraphs']:
            text = paragraph['context']; units = segments(text)
            identity = article.get('title') or hashlib.sha256(text.encode()).hexdigest()
            group = hashlib.sha256(json.dumps((article.get('source'), identity), sort_keys=True).encode()).hexdigest()
            split = partition(group)
            if split == 'calibration': continue
            for qa in paragraph['qas']:
                if qa['id'] == '6cf3dcd6-b5a3-4516-8f9e-c5c1c6b66628': continue
                answer = (qa.get('answers') or [{}])[0]
                key = answer.get('text', '')
                own = locate(text, key, answer.get('answer_start'), units)
                if own is None:
                    excluded['invalid_span'] += 1; continue
                candidates = [u[2].strip() for u in units if u[2].strip()]
                positive = [i for i, u in enumerate(candidates) if key in u]
                if not positive or len(positive) == len(candidates) or len(positive) > 16:
                    excluded['no_contrast_or_too_many_positives'] += 1; continue
                available.append({'id': qa['id'], 'group': group, 'source': 'human_sqac',
                                  'split': split, 'q': qa['question'], 'units': candidates, 'pos': positive})
    selected = []
    for split, limit in (('train', 6000), ('validation', 1000)):
        selected += sorted((r for r in available if r['split'] == split),
                           key=lambda r: hashlib.sha256(r['id'].encode()).digest())[:limit]
    del available, data
    banks = []
    for bank in TRAIN:
        root = ROOT/'results_v3/kiosco'/bank
        for name, text, ins, conversations in businesses(sorted(p for p in root.iterdir() if p.is_dir())):
            group = bank+'/'+name
            banks.append({'id': group, 'text': text, 'instructions': ins, 'conversations': conversations})
            if partition(group) == 'calibration': continue
            bot.load_context(text, ins)
            units = [u for u in bot.context_units if u.get('kind') not in ('heading', 'question')]
            for ci, conv in enumerate(conversations):
                for ti, turn in enumerate(conv):
                    action = turn.get('accion', 'responder'); keys = turn.get('claves') or []
                    if action == 'charla' or (action == 'responder' and not keys): continue
                    absent = action in ('abstenerse', 'derivar')
                    positive = [] if absent else [i for i, u in enumerate(units) if all(contains(u['text'], k) for k in keys)]
                    if not units or (not absent and not positive) or len(positive) > 16:
                        excluded['business_no_local_evidence'] += 1; continue
                    selected.append({'id': f'{group}/{ci}/{ti}', 'group': group, 'source': 'synthetic_business_train',
                                     'split': partition(group), 'q': turn['cliente'], 'pos': positive,
                                     'units': [u['text']+(' '+u['heading'] if u.get('inherited') else '') for u in units]})
            check_budget()
    cache = {}
    def encoded(text):
        if text not in cache:
            cache[text] = [vocab[f] for f in features(bot.context_terms(text)) if f in vocab]
        return cache[text]
    for r in selected:
        r['qids'] = encoded(r['q'])
        aids = [encoded(t) for t in r['units']]
        if len(aids) > 16:
            q = encode_numpy(r['qids'], weights, 'q')
            values = [float(encode_numpy(a, weights, 'a')@q) for a in aids]
            others = sorted((i for i in range(len(aids)) if i not in r['pos']), key=lambda i: (-values[i], i))
            keep = sorted(r['pos']+others[:16-len(r['pos'])])
            r['pos'] = [j for j, i in enumerate(keep) if i in r['pos']]
            r['units'] = [r['units'][i] for i in keep]; aids = [aids[i] for i in keep]
        r['aids'] = aids
        check_budget()
    train = [r for r in selected if r['split'] == 'train']
    validation = [r for r in selected if r['split'] == 'validation']
    groups = {s: sorted({r['group'] for r in selected if r['split'] == s}) for s in ('train', 'validation')}
    groups['calibration'] = sorted(b['id'] for b in banks if partition(b['id']) == 'calibration')
    assert not any(set(groups[a]) & set(groups[b]) for a, b in [('train', 'validation'), ('train', 'calibration'), ('validation', 'calibration')])
    return train, validation, banks, {'source_sqac_sha256': SOURCE_SHA, 'exclusions': dict(excluded), 'groups': groups,
        'train_examples': dict(Counter(r['source'] for r in train)), 'validation_examples': dict(Counter(r['source'] for r in validation)),
        'train_sha256': digest(train), 'validation_sha256': digest(validation),
        'train_absent': sum(not r['pos'] for r in train), 'validation_absent': sum(not r['pos'] for r in validation)}


def validate(model, rows):
    counts = Counter()
    with torch.no_grad():
        for r in rows:
            q = model(tensor([r['qids']]), 'q')
            a = model(tensor(r['aids']), 'a')
            values = a@q[0]/.1
            choice = int(values.argmax()); selected = int(torch.cat((values, model.null(q)[0])).argmax())
            category = 'absent' if not r['pos'] else 'answerable'
            counts[category] += 1
            counts['raw_correct'] += choice in r['pos']
            counts['correct_with_null'] += (selected in r['pos'] if r['pos'] else selected == len(a))
    return dict(counts)


def train():
    from leobot import Bot
    from experiments.g65_correspondencias import examples
    startwall = time.monotonic()
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() == ENGINE
    base = ROOT/'.leobot-data/base_kiosco.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    previous = json.loads((OLD/'neural.json').read_text())
    assert hashlib.sha256((OLD/'trained.npz').read_bytes()).hexdigest() == previous['models']['trained']['sha256']
    with np.load(OLD/'trained.npz', allow_pickle=False) as saved: initial = dict(saved)
    bot = Bot.load(base); vocab = previous['vocabulary']
    rows, validation, banks, education = prepare(bot, vocab, initial)
    sampled = examples(bot, ROOT/'.leobot-data/mfaq_es_train.jsonl')
    eligible = sorted((r for r in sampled if 1 <= len(r[1]) <= 40 and 1 <= len(r[2]) <= 160),
                      key=lambda r: hashlib.sha256(json.dumps(r, ensure_ascii=False).encode()).digest())
    faq = [r for r in eligible if int(hashlib.sha256(r[0].encode()).hexdigest(), 16) % 5 != 0][:6000]
    assert hashlib.sha256(json.dumps(faq, ensure_ascii=False).encode()).hexdigest() == previous['training_sha256']
    encode = lambda words: [vocab[f] for f in features(words) if f in vocab]
    fq, fa = [encode(q) for _, q, _ in faq], [encode(a) for _, _, a in faq]
    del sampled, eligible
    OUT.mkdir(exist_ok=True)
    if (OUT/'neural.json').exists(): raise FileExistsError('Preserve prior G98 artifacts')
    meta = {'vocabulary': vocab, 'engine': ENGINE, 'base_sha256': BASE_SHA, 'education': education,
            'initial_sha256': previous['models']['trained']['sha256'], 'models': {}, 'gates': {},
            'preparation_cpu_s': time.process_time()-BOOT}
    print(json.dumps({'stage': 'prepared', 'cpu_s': meta['preparation_cpu_s'], **{k:v for k,v in education.items() if k != 'groups'}}), flush=True)
    perm = list(range(len(rows))); bygroup = defaultdict(list); rng = random.Random(1)
    for i, r in enumerate(rows): bygroup[r['group']].append(i)
    for _, indices in sorted(bygroup.items()):
        shuffled = indices.copy(); rng.shuffle(shuffled)
        for i, j in zip(indices, shuffled): perm[i] = j
    meta['shuffled_changed'] = sum(rows[i]['q'] != rows[j]['q'] for i, j in enumerate(perm))
    for mode in ('more', 'localized', 'shuffled'):
        begin = time.process_time(); torch.manual_seed(1)
        model = Encoder(len(vocab)+1, initial)
        opt = torch.optim.AdamW(model.parameters(), lr=.003 if mode == 'more' else .001, weight_decay=.0001)
        order = list(range(len(faq) if mode == 'more' else len(rows)))
        rng = random.Random(1); losses = []
        for epoch in range(6 if mode == 'more' else 12):
            rng.shuffle(order); total, n = 0., 0
            size = 64 if mode == 'more' else 32
            for lo in range(0, len(order), size):
                check_budget(); ids = order[lo:lo+size]
                if mode == 'more':
                    q, a = model(tensor([fq[i] for i in ids]), 'q'), model(tensor([fa[i] for i in ids]), 'a')
                    logits = q@a.T/.1
                    mask = torch.tensor([[faq[i][1] == faq[j][1] or faq[i][2] == faq[j][2] for j in ids] for i in ids])
                    calc = lambda x,m: (x.logsumexp(1)-x.masked_fill(~m, -1e9).logsumexp(1)).mean()
                    loss = (calc(logits, mask)+calc(logits.T, mask.T))/2
                else:
                    selected = [rows[i] for i in ids]; width = max(len(r['aids']) for r in selected)
                    qrows = [rows[perm[i] if mode == 'shuffled' else i]['qids'] for i in ids]
                    arows = [a for r in selected for a in r['aids']+[[]]*(width-len(r['aids']))]
                    q = model(tensor(qrows), 'q'); a = model(tensor(arows), 'a').reshape(len(ids), width, 64)
                    logits = torch.cat(((a*q[:, None]).sum(2)/.1, model.null(q)), 1)
                    valid = torch.zeros((len(ids), width), dtype=torch.bool)
                    target = torch.zeros((len(ids), width+1), dtype=torch.bool)
                    for j, r in enumerate(selected):
                        valid[j, :len(r['aids'])] = True
                        target[j, r['pos'] or [width]] = True
                    loss = selection_loss(logits, target, valid)
                opt.zero_grad(); loss.backward(); opt.step()
                total += float(loss.detach())*len(ids); n += len(ids)
            losses.append(total/n)
            print(json.dumps({'stage': 'epoch', 'mode': mode, 'epoch': epoch+1, 'loss': losses[-1], 'cpu_s': time.process_time()-BOOT}), flush=True)
        model.eval(); weights = model.export()
        with torch.no_grad(): expected = model(tensor(fq[:32]), 'q').numpy()
        error = float(np.max(np.abs(expected-np.stack([encode_numpy(r, weights, 'q') for r in fq[:32]]))))
        assert error < 1e-5
        np.savez(OUT/f'{mode}.npz', **weights)
        meta['models'][mode] = {'null_option': mode != 'more', 'epochs': losses, 'cpu_s': time.process_time()-begin,
            'parameters': sum(p.numel() for p in model.parameters()), 'export_max_error': error,
            'sha256': hashlib.sha256((OUT/f'{mode}.npz').read_bytes()).hexdigest(),
            'validation': validate(model, validation)}
        (OUT/'neural.json').write_text(json.dumps(meta, ensure_ascii=False))
        print(json.dumps({'stage':'saved','mode':mode, **meta['models'][mode]}), flush=True)
    del model, opt
    gatebegin = time.process_time()
    routes = {n: EvidenceRoute(bot, n, root=OUT) for n in meta['models']}; gate_rows = {n: [] for n in routes}
    for b in banks:
        if partition(b['id']) != 'calibration': continue
        half = int(hashlib.sha256((b['id']+':gate').encode()).hexdigest(), 16) % 2
        bot.load_context(b['text'], b['instructions'])
        for r in routes.values(): r.prepare()
        for conv in b['conversations']:
            history = []
            for t in conv:
                reply = bot.answer(t['cliente'], history)
                history += [t['cliente'], reply['text']]
                if reply['status'] not in ABSTAINED or t.get('accion') == 'charla': continue
                absent = t.get('accion') in ('abstenerse', 'derivar'); keys = t.get('claves') or []
                if not absent and not keys: continue
                for name, route in routes.items():
                    raw = route.raw(t['cliente'])
                    if raw is None: continue
                    y = int(not absent and all(contains(bot.context_units[raw['index']]['text'], k) for k in keys))
                    gate_rows[name].append({'f': raw['features'], 'y': y, 'half': half})
        check_budget()
    for name, items in gate_rows.items():
        crossed = []
        assert {r['half'] for r in items} == {0, 1}
        for half in (0, 1):
            counts = naive_bayes([r for r in items if r['half'] != half])
            crossed += [(score(counts, r['f']), r['y']) for r in items if r['half'] == half]
        meta['gates'][name] = {'counts': naive_bayes(items), 'calibration': isotonic(crossed),
                              'rows': len(items), 'correct_proposals': sum(r['y'] for r in items)}
    meta.update(gate_cpu_s=time.process_time()-gatebegin, cpu_s=time.process_time()-BOOT,
                wall_s=time.monotonic()-startwall, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    meta['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((ROOT/'experiments').glob('g98_*.py'))}
    check_budget()
    (OUT/'neural.json').write_text(json.dumps(meta, ensure_ascii=False))
    result = {k:v for k,v in meta.items() if k not in ('vocabulary', 'gates')}
    result['gates'] = {n: {'rows':g['rows'],'correct_proposals':g['correct_proposals'],
                         'max_confidence':max(x[1] for x in g['calibration'])} for n,g in meta['gates'].items()}
    result['metadata_sha256'] = hashlib.sha256((OUT/'neural.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g98_training.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'stage':'done','cpu_s':meta['cpu_s'],'gates':result['gates']}), flush=True)


if __name__ == '__main__':
    try: train()
    except Exception as exc:
        (ROOT/'results_v3/g98_training_interruption.json').write_text(json.dumps({'error':repr(exc),
            'cpu_s':time.process_time()-BOOT,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n')
        raise
