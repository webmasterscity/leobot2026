"""G77 separates learned group emissions from collection background counts."""
from collections import Counter, defaultdict
import json
import math
import resource
import time

from experiments import g76_paired_groups as g76


def smooth_background(counts, global_background):
    total = sum(counts.values())+1
    return [(counts.get(i, 0)+p)/total for i, p in enumerate(global_background)]


def backgrounds(rows, domains, qsize, asize):
    q, a = Counter(), Counter()
    local = defaultdict(Counter)
    for (qs, ans), domain in zip(rows, domains):
        q.update(qs)
        a.update(ans)
        local[domain].update(ans)
    qtotal, atotal = sum(q.values()), sum(a.values())
    qglobal = [q[i]/qtotal for i in range(qsize)]
    aglobal = [a[i]/atotal for i in range(asize)]
    return qglobal, aglobal, {d: smooth_background(counts, aglobal) for d, counts in local.items()}


def mixtures(column, bg, rho):
    signal = [rho*math.exp(value) for value in column]
    noise = (1-rho)*bg
    denominators = [value+noise for value in signal]
    return [math.log(p) for p in denominators], [value/p for value, p in zip(signal, denominators)]


def project(model, ids, side, background):
    values = [math.log(p) for p in model['prior']]
    rho = model['rho'][0 if side == 'qlog' else 1]
    for i in ids:
        logs, _ = mixtures(model[side][i], background[i], rho)
        for k, value in enumerate(logs):
            values[k] += value
    return g76.softmax(values)[0]


def train(rows, domains, bg, *, seed, groups=32, rounds=12, local=True, deadline=None):
    begin = time.process_time()
    qglobal, aglobal, adomain = bg
    model, _ = g76.train(rows, len(qglobal), len(aglobal), seed=seed, groups=groups, rounds=0)
    model['rho'] = [.5, .5]
    observations = [sum(len(row[side]) for row in rows) for side in (0, 1)]
    trace = []
    for iteration in range(rounds):
        if deadline is not None and time.process_time() > deadline:
            raise TimeoutError('G77 enseñanza agotó presupuesto')
        start = time.process_time()
        qcounts = [[.1]*groups for _ in qglobal]
        acounts = [[.1]*groups for _ in aglobal]
        totals, foreground = [1.]*groups, [0., 0.]
        qmix = [mixtures(column, qglobal[i], model['rho'][0]) for i, column in enumerate(model['qlog'])]
        amix = {}
        priors = [math.log(p) for p in model['prior']]
        likelihood = 0.
        for (qs, ans), domain in zip(rows, domains):
            values = priors.copy()
            grouped = [qmix[i] for i in qs]
            answer_parts = []
            for i in ans:
                cache_key = domain if local else None, i
                if cache_key not in amix:
                    noise = adomain[domain][i] if local else aglobal[i]
                    amix[cache_key] = mixtures(model['alog'][i], noise, model['rho'][1])
                answer_parts.append(amix[cache_key])
            for logs, _ in grouped + answer_parts:
                for k, value in enumerate(logs):
                    values[k] += value
            responsibility, ll = g76.softmax(values)
            likelihood += ll
            for k, r in enumerate(responsibility):
                totals[k] += r
            for side, ids, parts, counts in ((0, qs, grouped, qcounts), (1, ans, answer_parts, acounts)):
                for i, (_, allocation) in zip(ids, parts):
                    for k, (r, probability) in enumerate(zip(responsibility, allocation)):
                        value = r*probability
                        counts[i][k] += value
                        foreground[side] += value
        model = g76.parameters(qcounts, acounts, totals)
        model['rho'] = [(n+1)/(total+2) for n, total in zip(foreground, observations)]
        trace.append({'round': iteration+1, 'rho': model['rho'], 'log_likelihood': likelihood,
                      'cpu_s': time.process_time()-start})
        if len(rows) > 100 and (iteration+1) % 4 == 0:
            print(json.dumps({'stage': 'education', 'seed': seed, 'local': local, 'round': iteration+1,
                              'rho': model['rho'], 'cpu_s': time.process_time()-begin}), flush=True)
    return model, {'seed': seed, 'groups': groups, 'pairs': len(rows), 'rounds': trace,
                   'cpu_s': time.process_time()-begin}


class BackgroundRanker(g76.TopicRanker):
    def prepare_units(self):
        start = time.process_time()
        if self.bundle['local_background']:
            counts = Counter()
            for unit in self.bot.context_units:
                terms = set(self.bot.context_terms(unit['text'])) | set(unit.get('inherited', ()))
                counts.update(self.bundle['av'][w] for w in terms if w in self.bundle['av'])
            self.document_background = smooth_background(counts, self.bundle['abackground'])
        else:
            self.document_background = self.bundle['abackground']
        self.preparation_cpu += time.process_time()-start
        super().prepare_units()

    def project(self, model, ids, side):
        bg = self.bundle['qbackground'] if side == 'qlog' else self.document_background
        return project(model, ids, side, bg)


def produce(bot, start_cpu, hashes, model_path):
    qv, av, pairs, permuted, teaching, domains = g76.teaching_pairs(bot, with_domains=True)
    bg = backgrounds(pairs, domains, len(qv), len(av))
    acquisition = time.process_time()-start_cpu
    bundles, learning = {}, {}
    seed0 = int(g76.ENGINE[:8], 16)
    for mode, data, local in (('full', pairs, True), ('global', pairs, False), ('shuffled', permuted, True)):
        bundles[mode] = {'qv': qv, 'av': av, 'models': [], 'qbackground': bg[0],
                         'abackground': bg[1], 'local_background': local}
        learning[mode] = []
        for offset in range(3):
            model, report = train(data, domains, bg, seed=seed0+offset, local=local, deadline=start_cpu+600)
            bundles[mode]['models'].append(model)
            learning[mode].append(report)
            model_path.write_text(json.dumps({'models': bundles, 'learning': learning,
                                             'teaching': teaching, 'sources_sha256': hashes}, ensure_ascii=False))
            print(json.dumps({'stage': 'learned', 'mode': mode, 'seed': seed0+offset,
                              'rho': model['rho'], 'cpu_s': report['cpu_s']}), flush=True)
    return bundles, learning, teaching, acquisition


if __name__ == '__main__':
    cpu0, wall0 = time.process_time(), time.monotonic()
    try:
        g76.main(producer=produce, ranker_type=BackgroundRanker, experiment='G77', validation_seconds=200,
                 reuse_training_contexts=True,
                 extra_sources=('experiments/g77_background_groups.py', 'prereg/G-77-separar-tema-del-sitio.md'))
    except TimeoutError as error:
        (g76.ROOT / 'results_v3/g77_interruption.json').write_text(json.dumps({
            'status': 'interrupted_budget', 'error': str(error), 'cpu_s': time.process_time()-cpu0,
            'wall_s': time.monotonic()-wall0, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }, ensure_ascii=False, indent=2)+'\n')
        raise
