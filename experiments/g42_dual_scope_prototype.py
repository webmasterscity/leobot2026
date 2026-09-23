"""Development prototype (outside the engine): two scopes, question-word marker (Wilson) and current key."""
import math, types, pathlib
import leobot.reading as R
def wilson(p,n,z=1.96):
    if n==0: return 0.0
    ph=p/n; d=1+z*z/n
    return (ph+z*z/(2*n)-z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n)))/d
src=pathlib.Path(R.__file__).read_text()
def rep(old,new):
    global src
    assert src.count(old)==1,old[:70]; src=src.replace(old,new)
rep("""                for scope in (key, '*'):""","""                for scope in (key, '*', 'W:' + self._wh_marker(qtokens)):""")
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
        for s in (scope if isinstance(scope, tuple) else (scope,)):
            if s == '*':
                continue
            local = features.get('\\x1f'.join(map(str, (s,) + feature)), (0, 0))
            rate = (local[0] + SMOOTHING * rate) / (local[0] + local[1] + SMOOTHING)
        return _logit(rate) - _logit(prior)

    def _wh_marker(self, question):
        model = self.reading_model
        df, missing = model['question_df'], model.get('question_unmatched', {})
        markers = [t for t in set(question) if self._marker_ok(t)]
        if not markers:
            return '*'
        return max(markers, key=lambda t: (wilson(missing.get(t, 0), df[t]), df[t], t))""")
rep("""                            value = memo[feature] = self._feature_score(key, feature, prior)""","""                            value = memo[feature] = self._feature_score(ORDER(key, 'W:' + self._wh_marker(qtokens)), feature, prior)""")
mod=types.ModuleType('reading_g42'); mod.__dict__.update(wilson=wilson,ORDER=lambda a,b:(b,a)); exec(compile(src,'reading_g42','exec'),mod.__dict__)
for name in ('observe_reading_example','answer_from_utterances','_feature_score','_wh_marker'):
    setattr(R.ReadingMemoryMixin,name,getattr(mod.ReadingMemoryMixin,name))
MOD=mod
