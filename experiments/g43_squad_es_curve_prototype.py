"""Development prototype (outside the engine): is reading a «no sabía»?

Educates the frozen reading learner with the same 2000 MLQA examples plus N
machine-translated SQuAD-es v1.1 training examples (commit c8478421, SHA-256
196cfa14...) and scores the clean visible development cases of G-28b.
python3 -m experiments.g43_squad_es_curve_prototype SQUAD_ES_JSON N [N ...]
"""
import json
import os
import random
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, ask, rows, scored, summary
from leobot import Bot


def squad_rows(path):
    doc = json.loads(Path(path).read_text(encoding='utf8')); out = []
    for article in doc['data']:
        for paragraph in article['paragraphs']:
            for qa in paragraph['qas']:
                out.append({'id': qa['id'], 'context': paragraph['context'], 'question': qa['question'],
                            'answers': [a['text'] for a in qa['answers']]})
    return sorted(out, key=lambda r: r['id'])


def main():
    path, sizes = sys.argv[1], sorted(int(x) for x in sys.argv[2:])
    z = archive()
    test = rows(z, 'MLQA_V1/test/test-context-es-question-es.json')
    rng = random.Random(EDU_SEED); chosen = rng.sample(test, 2300)
    education = chosen[:2000]
    edu_contexts = {r['context'] for r in education}
    visible = [r for r in rng.sample(test, len(test)) if r['context'] not in edu_contexts][:300]
    extra = squad_rows(path); random.Random(4343).shuffle(extra)
    bot = Bot(); done = 0; report = []
    cpu0 = time.process_time()
    for e in education:
        bot.observe_reading_example(e['context'], e['question'], e['answers'][0])
    for n in [0] + sizes:
        for e in extra[done:n]:
            bot.observe_reading_example(e['context'], e['question'], e['answers'][0])
        done = max(done, n)
        bot.consolidate_reading()
        edu_cpu = time.process_time() - cpu0
        results = [scored(ask(bot, case)[0], case) for case in visible]
        row = {'squad_es': n, 'education_cpu_s': round(edu_cpu, 1), **summary(results),
               'features': len(bot.reading_model.get('features', {}))}
        report.append(row); print(json.dumps(row), flush=True)
    out = Path('results_v3/g43_squad_es_curve_dev.json')
    out.write_text(json.dumps({'hashseed': os.environ.get('PYTHONHASHSEED'), 'rows': report}, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
