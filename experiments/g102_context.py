"""Experimental learned local context; NumPy inference over document quotations."""
import json
import numpy as np
from experiments.g99_interaction import PairFeatures, LEXICAL, ROOT
from experiments.g68_confianza import calibrated

OUT = ROOT / '.leobot-data/g102'
NAMES = ('context', 'width1', 'shuffled')


def lexical_encoder(bot):
    dummy = {'embedding': np.zeros((1, 64), dtype=np.float32)}
    for side in ('q', 'a'):
        dummy[side+'_weight'] = np.eye(64, dtype=np.float32)
        dummy[side+'_bias'] = np.zeros(64, dtype=np.float32)
    return PairFeatures(bot, {}, dummy)


def word_ids(bot, vocabulary, text, limit):
    return [vocabulary.get(w, 0) for w in bot.context_terms(text)[:limit]]


def padded(rows):
    array = np.zeros((len(rows), max(1, max(map(len, rows), default=0))), dtype=np.int64)
    for i, row in enumerate(rows):
        array[i, :len(row)] = row
    return array


def encode_numpy(ids, weights, side):
    mask = (ids != 0)[..., None]
    values = weights['embedding'][ids] * mask
    for layer in range(2):
        kernel = weights[f'conv{layer}_weight']
        radius = len(kernel)//2
        extended = np.pad(values, ((0, 0), (radius, radius), (0, 0)))
        update = np.broadcast_to(weights[f'conv{layer}_bias'], values.shape).copy()
        for j, matrix in enumerate(kernel):
            update += extended[:, j:j+values.shape[1]] @ matrix
        values = (values + np.tanh(update)) * mask
    values = np.tanh(values @ weights[side+'_weight'] + weights[side+'_bias'])
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12) * mask


def interaction_numpy(q, qmask, a, amask):
    result = np.zeros((len(a), 6), dtype=np.float32)
    if not qmask.any() or not len(a):
        return result
    match = np.einsum('qd,nad->nqa', q[qmask], a, optimize=True)
    match = np.where(amask[:, None, :], match, -1e9).max(-1)
    match[~amask.any(-1)] = 0
    mean = match.mean(-1)
    variance = np.maximum((match*match).mean(-1)-mean*mean, 0)
    result[:] = np.stack((mean, match.min(-1), np.sqrt(variance+1e-12),
                         np.quantile(match, .25, axis=-1), np.quantile(match, .75, axis=-1),
                         match.max(-1)), axis=-1)
    return result


def prepared_scores(qids, vectors, mask, lexical, weights):
    qids = padded([list(qids)])
    q = encode_numpy(qids, weights, 'q')[0]
    features = np.column_stack(((lexical-weights['lex_mean'])/weights['lex_scale'],
                               interaction_numpy(q, qids[0] != 0, vectors, mask)))
    return (np.tanh(features @ weights['w1'] + weights['b1']) @ weights['w2'] + weights['b2'])[:, 0]


def score_numpy(qids, aids, lexical, weights):
    return prepared_scores(qids, encode_numpy(aids, weights, 'a'), aids != 0, lexical, weights)


class ContextRoute:
    def __init__(self, bot, name, threshold=.9, root=OUT):
        self.bot, self.name, self.threshold = bot, name, threshold
        self.meta = json.loads((root/'models.json').read_text())
        self.vocabulary = self.meta['vocabulary']
        with np.load(root/f'{name}.npz', allow_pickle=False) as saved:
            self.weights = dict(saved)
        self.lexical = lexical_encoder(bot)
        self.gate = self.meta.get('calibration', {}).get(name)

    def prepare(self):
        self.lexical.unit_cache.clear()
        self.ids = [i for i, u in enumerate(self.bot.context_units) if u.get('kind') not in ('heading', 'question')]
        texts = [self.bot.context_units[i]['text'] + (' '+self.bot.context_units[i]['heading']
                 if self.bot.context_units[i].get('inherited') else '') for i in self.ids]
        self.units = self.lexical.prepare(texts)
        ids = padded([word_ids(self.bot, self.vocabulary, t, 64) for t in texts])
        self.vectors, self.mask = encode_numpy(ids, self.weights, 'a'), ids != 0

    def raw(self, question, history=()):
        if not self.ids:
            return None
        q = word_ids(self.bot, self.vocabulary, question, 32)
        lex = self.lexical.one_question(question, self.units)[:, :LEXICAL]
        values = prepared_scores(q, self.vectors, self.mask, lex, self.weights)
        i = int(values.argmax())
        return {'index': self.ids[i], 'score': float(values[i]), 'null_selected': bool(values[i] <= 0)}

    def propose(self, question, history):
        raw = self.raw(question, history)
        if raw is None or raw['null_selected'] or self.gate is None:
            return None
        p = calibrated(self.gate['blocks'], raw['score'])
        return {'index': raw['index'], 'confidence': p} if p >= self.threshold else None
