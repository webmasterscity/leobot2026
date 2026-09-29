"""Diagnóstico de desarrollo (banco G-62 a G-64, base enseñada en seis bancos): ¿añadir a la mejor unidad otra que explique lo que
ella deja sin explicar cubre más claves?  Solo mide cobertura por claves; no es una medida de mejora.

python3 -m experiments.g106_complemento_dev BASE.json CARPETA...
"""
import collections
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from leobot import Bot


def main():
    bot = Bot.load(Path(sys.argv[1]))
    model = bot.context_model['usefulness']
    pairs = bot._pair_weights(model)
    rows = []
    for name, text, instructions, conversations in businesses(sys.argv[2:]):
        bot.load_context(text, instructions)
        for conversation in conversations:
            for turn in conversation:
                action = turn.get('accion', 'responder')
                if action == 'charla':
                    continue
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                _, question = bot._question_part(turn['cliente'])
                terms = bot.context_terms(question)
                if not terms:
                    continue
                base, gains, how, asked = bot._gains(terms, question)
                table = bot._candidate_table(terms, question, base, gains, how, asked)
                if not table:
                    continue
                for c in table:
                    c['z'] = model['bias'] + sum(w * (x - m) / s for x, m, s, w in zip(c['dense'], model['mean'], model['scale'], model['weights'])) \
                        + model['pair_scale'] * sum(pairs.get(k, 0.0) for k in c['pairs'])
                table.sort(key=lambda c: -c['z'])
                first = table[0]
                delta = how.get(None, {})
                explained = set(how.get(first['unit'], {}))
                mass = sum(delta.values()) or 1.0
                best, best_mass = None, 0.0
                for c in table[1:]:
                    extra = sum(delta.get(q, 0.0) for q in how.get(c['unit'], {}) if q not in explained)
                    if extra > best_mass:
                        best, best_mass = c, extra
                shown = [bot.context_units[first['unit']]['text']]
                second = bot.context_units[best['unit']]['text'] if best else None
                rows.append({'tipo': turn.get('tipo'), 'action': action, 'keys': keys, 'first': shown[0], 'second': second,
                             'share': best_mass / mass, 'z1': first['z']})
    def covered(texts, keys):
        h = ' ' + plain(' '.join(texts)) + ' '
        return bool(keys) and all(f' {plain(k)} ' in h for k in keys)
    for theta in (0.1, 0.2, 0.3, 0.4, 0.5):
        gain = lose = junk = silent = 0
        for r in rows:
            adds = r['second'] is not None and r['share'] >= theta
            if r['action'] == 'responder' and r['keys']:
                one = covered([r['first']], r['keys'])
                two = covered([r['first'], r['second']], r['keys']) if adds else one
                gain += (not one) and two
                junk += one and adds
            elif r['action'] in ('abstenerse', 'derivar'):
                silent += adds
        by = collections.Counter(r['tipo'] for r in rows if r['second'] is not None and r['share'] >= theta and r['action'] == 'responder')
        print(f'θ={theta}: claves recuperadas por la segunda unidad {gain}; turnos ya cubiertos que recibirían una segunda unidad {junk}; '
              f'sin respuesta con segunda unidad {silent}; por tipo {dict(by)}')


if __name__ == '__main__':
    main()
