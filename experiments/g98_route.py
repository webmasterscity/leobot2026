"""Experimental retriever after G98 education; NumPy only during answering."""
from experiments.g97_neural import NeuralRoute
from experiments.g60_calibrar_confianza import score
from experiments.g68_confianza import calibrated
from leobot.context import _bin


class EvidenceRoute(NeuralRoute):
    def raw(self, question):
        result = super().raw(question)
        if result is not None and self.meta['models'][self.name].get('null_option'):
            q, _ = self.encode(question, 'q')
            # Both logits were trained at temperature .1; compare before scaling.
            null = float(q @ self.weights['null_weight'] + self.weights['null_bias'][0])
            margin = result['similarity'] - null
            result['null_selected'] = margin <= 0.
            result['features']['null_margin'] = str(_bin(margin, (-.4, -.2, -.1, 0., .1, .2, .4)))
        return result

    def propose(self, question, history):
        r = self.raw(question)
        if r is None or r.get('null_selected') or self.gate is None:
            return None
        p = calibrated(self.gate['calibration'], score(self.gate['counts'], r['features']))
        return {'index': r['index'], 'confidence': p} if p >= .4 else None
