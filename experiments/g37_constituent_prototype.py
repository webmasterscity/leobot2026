"""Development prototype (outside the engine): candidate spans restricted to learned constituents."""
import leobot.reading as R
from leobot.reading import _is_word
MODE={'mode':'subtree'}
orig=R.ReadingMemoryMixin._candidate_spans
def constituents(self,tokens):
    if MODE['mode']=='none' or not getattr(self,'syntax_model',{}).get('sentences'):
        yield from orig(self,tokens); return
    cache=getattr(self,'_const_cache',None)
    if cache is None or cache[0] is not tokens:
        p=self.parse_words(tokens); allowed=set()
        if p and p.get('status')=='parsed_syntax':
            heads=[h-1 for h in p['heads']]; n=len(tokens); lo=list(range(n)); hi=list(range(n))
            for i in range(n):
                c,s=i,0
                while heads[c]>=0 and s<=n:
                    par=heads[c]; lo[par]=min(lo[par],i); hi[par]=max(hi[par],i); c=par; s+=1
            for i in range(n):
                a,b=lo[i],hi[i]+1
                while a<b and not _is_word(tokens[a]): a+=1
                while b>a and not _is_word(tokens[b-1]): b-=1
                if a<b: allowed.add((a,b))
                if MODE['mode']=='subtree+head': allowed.add((i,i+1))
        cache=(tokens,allowed); self._const_cache=cache
    for span in orig(self,tokens):
        if span in cache[1]: yield span
R.ReadingMemoryMixin._candidate_spans=constituents
