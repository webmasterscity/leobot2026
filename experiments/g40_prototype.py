"""Development prototype (outside the engine): answer-type scope = gap marker + the question word after it."""
import types, pathlib
import leobot.reading as R
from leobot.reading import _TOKEN,_norm,_is_word
src=pathlib.Path(R.__file__).read_text()
def rep(old,new):
    global src
    assert src.count(old)==1,old[:60]; src=src.replace(old,new)
rep("""            for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized) + extra:
                for scope in (key, '*'):""" if "+ extra" in src else """            for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                for scope in (key, '*'):""","""            for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                for scope in (key, '*', self._type_scope(qtokens, key)):""")
rep("""    def _feature_score(self, scope: str, feature: tuple, prior: float) -> float:
        features = self.reading_model['features']
        general = features.get('\\x1f'.join(map(str, ('*',) + feature)), (0, 0))
        rate = (general[0] + SMOOTHING * prior) / (general[0] + general[1] + SMOOTHING)
        if scope != '*':
            local = features.get('\\x1f'.join(map(str, (scope,) + feature)), (0, 0))
            rate = (local[0] + SMOOTHING * rate) / (local[0] + local[1] + SMOOTHING)
        return _logit(rate) - _logit(prior)""","""    def _feature_score(self, scope, feature: tuple, prior: float) -> float:
        features = self.reading_model['features']
        general = features.get('\\x1f'.join(map(str, ('*',) + feature)), (0, 0))
        rate = (general[0] + SMOOTHING * prior) / (general[0] + general[1] + SMOOTHING)
        scopes = scope if isinstance(scope, tuple) else (scope,)
        for s in scopes:
            if s == '*':
                continue
            local = features.get('\\x1f'.join(map(str, (s,) + feature)), (0, 0))
            rate = (local[0] + SMOOTHING * rate) / (local[0] + local[1] + SMOOTHING)
        return _logit(rate) - _logit(prior)

    def _type_scope(self, question, key):
        if key == '*' or key not in question:
            return key + '|-'
        i = question.index(key)
        nxt = question[i + 1] if i + 1 < len(question) else '-'
        return key + '|' + nxt""")
rep("""                            value = memo[feature] = self._feature_score(key, feature, prior)""","""                            value = memo[feature] = self._feature_score((key, self._type_scope(qtokens, key)), feature, prior)""")
mod=types.ModuleType('reading_g40'); exec(compile(src,'reading_g40','exec'),mod.__dict__)
for name in ('observe_reading_example','answer_from_utterances','_feature_score','_type_scope'):
    setattr(R.ReadingMemoryMixin,name,getattr(mod.ReadingMemoryMixin,name))
