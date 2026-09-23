"""Development-only runtime patch (never committed): tree features for reading."""
import leobot.reading as R
from leobot.reading import _TOKEN,_norm,_bucket,_is_word
M=R.ReadingMemoryMixin
def _reading_parse(self,tokens):
    m=getattr(self,'syntax_model',None)
    if not m or not m.get('sentences'): return None
    p=self.parse_words(tokens)
    if not p or p.get('status')!='parsed_syntax': return None
    return p['tags'],p['heads']
def _tree(parse,size):
    tags,heads=parse; head=[h-1 for h in heads]; low,high=list(range(size)),list(range(size))
    for node in range(size):
        cur,steps=node,0
        while head[cur]>=0 and steps<=size:
            par=head[cur]; low[par]=min(low[par],node); high[par]=max(high[par],node); cur=par; steps+=1
    return {'tags':tags,'head':head,'span':list(zip(low,high))}
def _gap_head(self,question,key,present):
    words=_TOKEN.findall(question); parse=self._reading_parse(words)
    if parse is None: return None
    norm=[_norm(w) for w in words]
    if key not in norm: return None
    head=[h-1 for h in parse[1]]; cur,steps=norm.index(key),0
    while head[cur]>=0 and steps<=len(words):
        cur=head[cur]; steps+=1
        if norm[cur] in present: return norm[cur]
    return None
MODE={'mode':'joint'}
def _tree_features(tree,start,end,anchors,gap_head,normalized):
    head=tree['head']; roots=[i for i in range(start,end) if not start<=head[i]<end]
    if len(roots)!=1: return [('treej','multi')]
    r=roots[0]; par=head[r]
    attach='root' if par<0 else ('gap_head' if gap_head is not None and normalized[par]==gap_head else ('anchor' if par in anchors else 'other'))
    full=tree['span'][r]==(start,end-1)
    if MODE['mode']=='joint': return [('treej',attach,full,tree['tags'][r])]
    if MODE['mode']=='joint2': return [('treej',attach,full)]
    return []
orig_span=M._span_features
def _span_features(self,tokens,start,end,anchors,qtokens,gap=(None,None),normalized=None):
    base=orig_span(self,tokens,start,end,anchors,qtokens,gap,normalized)
    ctx=getattr(self,'_dev_tree_ctx',None)
    if ctx is None or ctx[0] is not tokens: return base
    return base+_tree_features(ctx[1],start,end,anchors,ctx[2],normalized or [_norm(t) for t in tokens])
M._reading_parse=_reading_parse; M._gap_head=_gap_head; M._span_features=_span_features
orig_obs=M.observe_reading_example
def observe(self,context,question,answer):
    # set tree context lazily through a wrapper around _anchors (called once per sentence)
    self._dev_q=question
    return orig_obs(self,context,question,answer)
orig_anchors=M._anchors
def _anchors(self,tokens,qtokens):
    a=orig_anchors(self,tokens,qtokens)
    parse=self._reading_parse(tokens)
    if parse is not None and getattr(self,'_dev_q',None):
        present={_norm(t) for t in tokens}; key=self._gap_marker([_norm(t) for t in _TOKEN.findall(self._dev_q) if _is_word(t)])
        self._dev_tree_ctx=(tokens,_tree(parse,len(tokens)),self._gap_head(self._dev_q,key,present))
    else:
        self._dev_tree_ctx=None
    return a
M._anchors=_anchors; M.observe_reading_example=observe
orig_ans=M.answer_from_utterances
def answer(self,question,*a,**k):
    self._dev_q=question; return orig_ans(self,question,*a,**k)
M.answer_from_utterances=answer
