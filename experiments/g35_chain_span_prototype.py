"""Development prototype (outside the engine): chained backoff span scorer."""
import types, pathlib
import leobot.reading as R
ORDER={'order':['shape','gap_after','gap_before','position','before','after','run','question_inside','first','last']}
KAPPA={'k':5.0}
src=pathlib.Path(R.__file__).read_text()
old="""                if use_model:
                    score = 0.0
                    for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                        value = memo.get(feature)
                        if value is None:
                            value = memo[feature] = self._feature_score(key, feature, prior)
                        score += value"""
new="""                if use_model:
                    chain = tuple(self._span_features(tokens, start, end, anchors, qset, gap, normalized))
                    score = memo.get(chain)
                    if score is None:
                        score = memo[chain] = self._chain_score(key, chain, prior)"""
assert src.count(old)==1; src=src.replace(old,new)
src=src.replace("""    def consolidate_reading(self) -> dict:""","""    def _chain_score(self, key, chain, prior):
        features = self.reading_model['features']
        rate = prior
        for feature in chain:
            for scope in ('*', key):
                if scope == '*' and key == '*':
                    continue
                pos, neg = features.get('\\x1f'.join(map(str, (scope,) + feature)), (0, 0))
                rate = (pos + KAPPA['k'] * rate) / (pos + neg + KAPPA['k'])
        return _logit(rate) - _logit(prior)

    def consolidate_reading(self) -> dict:""")
mod=types.ModuleType('reading_g35'); mod.__dict__['KAPPA']=KAPPA; exec(compile(src,'reading_g35','exec'),mod.__dict__); mod.KAPPA=KAPPA
orig_span=R.ReadingMemoryMixin._span_features
def cumulative(self,tokens,start,end,anchors,qtokens,gap=(None,None),normalized=None):
    flat={f[0]:f[1:] for f in orig_span(self,tokens,start,end,anchors,qtokens,gap,normalized)}
    out=[]; acc=()
    for name in ORDER['order']:
        acc=acc+(name,)+flat[name]; out.append(('C',)+acc)
    return out
R.ReadingMemoryMixin._span_features=cumulative
R.ReadingMemoryMixin.answer_from_utterances=mod.ReadingMemoryMixin.answer_from_utterances
R.ReadingMemoryMixin._chain_score=mod.ReadingMemoryMixin._chain_score
