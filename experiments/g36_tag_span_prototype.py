"""Development prototype (outside the engine): learned word classes as span features."""
import leobot.reading as R
MODE={'mode':'first_last'}
orig_span=R.ReadingMemoryMixin._span_features
def with_tags(self,tokens,start,end,anchors,qtokens,gap=(None,None),normalized=None):
    base=orig_span(self,tokens,start,end,anchors,qtokens,gap,normalized)
    cache=getattr(self,'_tag_cache',None)
    if cache is None or cache[0] is not tokens:
        tags=self.tag_words(tokens) if getattr(self,'syntax_model',{}).get('sentences') else None
        cache=(tokens,tags); self._tag_cache=cache
    tags=cache[1]
    if not tags: return base
    if MODE['mode']=='first_last': base.append(('tags',tags[start],tags[end-1]))
    elif MODE['mode']=='all': base.append(('tags',tags[start],tags[end-1])); base.append(('before_tag',tags[start-1] if start else '<s>',tags[end] if end<len(tags) else '</s>'))
    return base
R.ReadingMemoryMixin._span_features=with_tags
