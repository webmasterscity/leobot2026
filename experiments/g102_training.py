"""End-to-end local-context education on the immutable G98 partitions."""
import time
BOOT = time.process_time()
import hashlib
import json
from collections import defaultdict, Counter
import random
import resource
import subprocess
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from leobot import Bot
from experiments.g98_training import prepare, partition
from experiments.g99_training import Decision, decision_loss
from experiments.g102_context import (ROOT, OUT, NAMES, ContextRoute, lexical_encoder,
                                     word_ids, padded, score_numpy)
from experiments.g68_confianza import isotonic
from experiments.g57_kiosco import contains
from experiments.g97_backups import ABSTAINED
from experiments.g74_relation_coverage import ENGINE, BASE_SHA


def interaction_torch(q, qmask, a, amask):
    match = torch.einsum('bqd,bnad->bnqa', q, a)
    match = match.masked_fill(~amask[:, :, None, :], -1e9).max(-1).values
    match = torch.where(amask.any(-1)[:, :, None], match, 0)
    mask = qmask[:, None, :]
    count = qmask.sum(-1).clamp_min(1)
    mean = (match*mask).sum(-1)/count[:, None]
    variance = ((match*match*mask).sum(-1)/count[:, None]-mean*mean).clamp_min(0)
    ordered = match.masked_fill(~mask, 1e9).sort(-1).values
    quartiles = []
    for fraction in (.25, .75):
        location = (count-1)*fraction
        lo, hi = location.long(), location.ceil().long()
        gather = lambda ix: ordered.gather(-1, ix[:, None, None].expand(-1, ordered.shape[1], 1))[..., 0]
        quartiles.append(gather(lo)+(gather(hi)-gather(lo))*(location-lo)[:, None])
    result = torch.stack((mean, match.masked_fill(~mask, 1e9).min(-1).values,
                          torch.sqrt(variance+1e-12), *quartiles,
                          match.masked_fill(~mask, -1e9).max(-1).values), -1)
    return torch.where(qmask.any(-1)[:, None, None], result, 0)


class ContextModel(nn.Module):
    def __init__(self, initial, width, mean=None, scale=None):
        super().__init__()
        self.embedding = nn.Embedding.from_pretrained(torch.from_numpy(initial['embedding'].copy()),
                                                      freeze=False, padding_idx=0)
        self.layers = nn.ModuleList([nn.Conv1d(64, 64, width, padding=width//2) for _ in range(2)])
        self.q, self.a = nn.Linear(64, 64), nn.Linear(64, 64)
        with torch.no_grad():
            self.embedding.weight[0].zero_()
            for side in ('q', 'a'):
                getattr(self, side).weight.copy_(torch.from_numpy(initial[side+'_weight'].T))
                getattr(self, side).bias.copy_(torch.from_numpy(initial[side+'_bias']))
        self.decision = Decision(19)
        self.register_buffer('lex_mean', torch.tensor(np.zeros(13) if mean is None else mean, dtype=torch.float32))
        self.register_buffer('lex_scale', torch.tensor(np.ones(13) if scale is None else scale, dtype=torch.float32))

    def encode(self, ids, side):
        mask = ids.ne(0)[..., None]
        values = self.embedding(ids)*mask
        for layer in self.layers:
            values = (values+torch.tanh(layer(values.transpose(1, 2)).transpose(1, 2)))*mask
        return F.normalize(torch.tanh(getattr(self, side)(values)), dim=-1)*mask

    def forward(self, qids, aids, lexical):
        q = self.encode(qids, 'q')
        a = self.encode(aids.flatten(0, 1), 'a').reshape(*aids.shape, 64)
        matches = interaction_torch(q, qids.ne(0), a, aids.ne(0))
        return self.decision(torch.cat(((lexical-self.lex_mean)/self.lex_scale, matches), -1))

    def export(self):
        result = {'embedding': self.embedding.weight.detach().numpy().copy(), **self.decision.export(),
                  'lex_mean': self.lex_mean.numpy().copy(), 'lex_scale': self.lex_scale.numpy().copy()}
        for side in ('q', 'a'):
            result[side+'_weight'] = getattr(self, side).weight.detach().numpy().T.copy()
            result[side+'_bias'] = getattr(self, side).bias.detach().numpy().copy()
        for i, layer in enumerate(self.layers):
            result[f'conv{i}_weight'] = layer.weight.detach().numpy().transpose(2, 1, 0).copy()
            result[f'conv{i}_bias'] = layer.bias.detach().numpy().copy()
        return result


def check():
    if time.process_time()-BOOT > 1200:
        raise TimeoutError('G102 total preparation/education/calibration CPU budget')
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 3*1024**2:
        raise MemoryError('G102 RSS budget')


def batch(rows, ids, questions, lexical):
    width = max(len(rows[i]['tokens_a']) for i in ids)
    q = torch.from_numpy(padded([questions[i] for i in ids]))
    a = torch.from_numpy(padded([a for i in ids for a in rows[i]['tokens_a']+[[]]*(width-len(rows[i]['tokens_a']))]))
    a = a.reshape(len(ids), width, -1)
    lex = torch.zeros((len(ids), width, 13))
    valid = torch.zeros((len(ids), width), dtype=torch.bool)
    target = torch.zeros((len(ids), width+1), dtype=torch.bool)
    for j, i in enumerate(ids):
        n = len(rows[i]['tokens_a'])
        lex[j, :n] = torch.from_numpy(lexical[i])
        valid[j, :n] = True
        target[j, rows[i]['pos'] or [width]] = True
    return q, a, lex, valid, target


def train():
    wall = time.monotonic()
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() == ENGINE
    assert hashlib.sha256((ROOT/'.leobot-data/base_kiosco.json').read_bytes()).hexdigest() == BASE_SHA
    old = ROOT/'.leobot-data/g98'
    previous = json.loads((old/'neural.json').read_text())
    assert hashlib.sha256((old/'localized.npz').read_bytes()).hexdigest() == previous['models']['localized']['sha256']
    with np.load(old/'localized.npz', allow_pickle=False) as source:
        initial = dict(source)
    with np.load(ROOT/'.leobot-data/g97/trained.npz', allow_pickle=False) as source:
        candidates = dict(source)
    bot = Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    vocab = previous['vocabulary']
    rows, validation, banks, education = prepare(bot, vocab, candidates)
    for key in ('train_sha256', 'validation_sha256'):
        assert education[key] == previous['education'][key]
    perm = list(range(len(rows))); groups = defaultdict(list); rng = random.Random(1)
    for i, r in enumerate(rows): groups[r['group']].append(i)
    for _, indices in sorted(groups.items()):
        mixed = indices.copy(); rng.shuffle(mixed)
        for i, j in zip(indices, mixed): perm[i] = j
    encoder = lexical_encoder(bot)
    truncations = Counter()
    for part, selected in (('train', rows), ('validation', validation)):
        for r in selected:
            terms = bot.context_terms(r['q'])
            r['tokens_q'] = [vocab.get(w, 0) for w in terms[:32]]
            truncations[part+'_questions'] += len(terms) > 32
            r['tokens_a'] = []
            for unit in r['units']:
                terms = bot.context_terms(unit)
                truncations[part+'_units'] += len(terms) > 64
                r['tokens_a'].append([vocab.get(w, 0) for w in terms[:64]])
    lexical, confused, vallex = [], [], []
    for i, r in enumerate(rows):
        units = encoder.prepare(r['units'])
        lexical.append(encoder.one_question(r['q'], units)[:, :13].copy())
        confused.append(encoder.one_question(rows[perm[i]]['q'], units)[:, :13].copy())
        if i % 512 == 0: check()
    for r in validation:
        vallex.append(encoder.one_question(r['q'], encoder.prepare(r['units']))[:, :13].copy())
    encoder.unit_cache.clear()
    OUT.mkdir(exist_ok=True)
    if (OUT/'models.json').exists(): raise FileExistsError('Preserve G102 artifacts')
    meta = {'engine': ENGINE, 'base_sha256': BASE_SHA, 'vocabulary': vocab, 'education': education,
            'initial_sha256': previous['models']['localized']['sha256'], 'models': {}, 'calibration': {},
            'truncations': dict(truncations), 'shuffled_changed': sum(rows[i]['q'] != rows[j]['q'] for i, j in enumerate(perm)),
            'preparation_cpu_s': time.process_time()-BOOT}
    print(json.dumps({'stage': 'prepared', 'rows': len(rows), 'cpu_s': time.process_time()-BOOT}), flush=True)
    for name in NAMES:
        start = time.process_time(); source = confused if name == 'shuffled' else lexical
        questions = [rows[perm[i] if name == 'shuffled' else i]['tokens_q'] for i in range(len(rows))]
        joined = np.concatenate(source); mean, scale = joined.mean(0), np.maximum(joined.std(0), 1e-3)
        del joined
        torch.manual_seed(1)
        model = ContextModel(initial, 1 if name == 'width1' else 3, mean, scale)
        opt = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.001)
        order = list(range(len(rows))); rng = random.Random(1); losses = []
        for epoch in range(6):
            rng.shuffle(order); total = 0.
            for lo in range(0, len(order), 16):
                check(); ids = order[lo:lo+16]
                q, a, x, valid, target = batch(rows, ids, questions, source)
                loss = decision_loss(model(q, a, x), target, valid)
                if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
                opt.zero_grad(); loss.backward(); opt.step()
                total += float(loss.detach())*len(ids)
            losses.append(total/len(rows))
            print(json.dumps({'stage': 'epoch', 'mode': name, 'epoch': epoch+1, 'loss': losses[-1],
                              'cpu_s': time.process_time()-BOOT}), flush=True)
        model.eval(); weights = model.export()
        val = Counter(); error = 0.
        with torch.no_grad():
            for lo in range(0, len(validation), 16):
                check(); ids = list(range(lo, min(lo+16, len(validation))))
                q, a, x, valid, target = batch(validation, ids, [r['tokens_q'] for r in validation], vallex)
                scores = model(q, a, x).numpy()
                for j, i in enumerate(ids):
                    r = validation[i]; values = scores[j, :len(r['tokens_a'])]; best = int(values.argmax())
                    val['answerable' if r['pos'] else 'absent'] += 1
                    val['raw_correct'] += best in r['pos']
                    val['correct_with_null'] += bool(best in r['pos'] and values[best] > 0) if r['pos'] else bool(values[best] <= 0)
                    if lo == 0:
                        actual = score_numpy(r['tokens_q'], padded(r['tokens_a']), vallex[i], weights)
                        error = max(error, float(np.max(np.abs(actual-values))))
        assert error < 1e-4, error
        np.savez(OUT/f'{name}.npz', **weights)
        meta['models'][name] = {'parameters': sum(p.numel() for p in model.parameters()), 'losses': losses,
            'cpu_s': time.process_time()-start, 'validation': dict(val), 'export_max_error': error,
            'sha256': hashlib.sha256((OUT/f'{name}.npz').read_bytes()).hexdigest()}
        (OUT/'models.json').write_text(json.dumps(meta, ensure_ascii=False))
        print(json.dumps({'stage': 'saved', 'mode': name, **meta['models'][name]}), flush=True)
    del model, opt, encoder
    start = time.process_time(); routes = {n: ContextRoute(bot, n) for n in NAMES}
    points = {n: [] for n in NAMES}
    for b in banks:
        if partition(b['id']) != 'calibration': continue
        bot.load_context(b['text'], b['instructions'])
        for route in routes.values(): route.prepare()
        for conv in b['conversations']:
            history = []
            for t in conv:
                reply = bot.answer(t['cliente'], history)
                if reply['status'] in ABSTAINED and t.get('accion') != 'charla':
                    absent = t.get('accion') in ('abstenerse', 'derivar'); keys = t.get('claves') or []
                    if absent or keys:
                        for name, route in routes.items():
                            raw = route.raw(t['cliente'], history)
                            if raw is not None:
                                correct = int(not absent and all(contains(bot.context_units[raw['index']]['text'], k) for k in keys))
                                points[name].append((raw['score'], correct))
                history += [t['cliente'], reply['text']]
        check()
    for name, values in points.items():
        meta['calibration'][name] = {'blocks': isotonic(values), 'rows': len(values),
                                      'correct_proposals': sum(y for _, y in values)}
    meta.update(gate_cpu_s=time.process_time()-start, cpu_s=time.process_time()-BOOT, wall_s=time.monotonic()-wall,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    meta['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((ROOT/'experiments').glob('g102_*.py'))}
    check(); (OUT/'models.json').write_text(json.dumps(meta, ensure_ascii=False))
    report = {k: v for k, v in meta.items() if k not in ('vocabulary', 'calibration')}
    report['calibration'] = {n: {'rows': g['rows'], 'correct_proposals': g['correct_proposals'],
                                   'maximum': max(p[1] for p in g['blocks'])} for n, g in meta['calibration'].items()}
    report['metadata_sha256'] = hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g102_training.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'stage': 'done', 'cpu_s': meta['cpu_s'], 'calibration': report['calibration']}), flush=True)


if __name__ == '__main__':
    try:
        train()
    except Exception as exc:
        (ROOT/'results_v3/g102_interruption.json').write_text(json.dumps({'error': repr(exc), 'cpu_s': time.process_time()-BOOT,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n')
        raise
