"""Development prototype (outside the engine): structured events from learned parses."""
from leobot.reading import _TOKEN,_norm,_is_word
def tree(parse):
    heads=[h-1 for h in parse['heads']]; kids={i:[] for i in range(len(heads))}
    for i,h in enumerate(heads):
        if h>=0: kids[h].append(i)
    def span(i):
        lo=hi=i; st=[i]
        while st:
            n=st.pop(); lo=min(lo,n); hi=max(hi,n); st.extend(kids[n])
        return lo,hi
    return heads,kids,span
def answer(bot,context,question):
    q=_TOKEN.findall(question); qp=bot.parse_words(q)
    if not qp or 'labels' not in qp: return None
    qn=[_norm(t) for t in q]; key=bot._gap_marker([t for t in qn if t])
    if key=='*' or key not in qn: return None
    qh,qk,_=tree(qp); m=qn.index(key)
    events=[]
    for s in bot._document_sentences(context):
        toks=_TOKEN.findall(s); p=bot.parse_words(toks)
        if not p or 'labels' not in p: continue
        events.append((toks,[_norm(t) for t in toks],p,tree(p)))
    present=set(n for _,sn,_,_ in events for n in sn)
    path=[m]
    while qh[path[-1]]>=0:
        path.append(qh[path[-1]])
        if qn[path[-1]] in present and _is_word(q[path[-1]]): break
    anchor=path[-1]
    if anchor==m or qn[anchor] not in present: return None
    slot=path[-2]; slot_label=qp['labels'][slot]
    constraints=[(qp['labels'][c],qn[c]) for c in qk[anchor] if c!=slot and _is_word(q[c]) and qp['labels'][c]!='punct']
    best=[]; 
    for toks,sn,p,(h,k,span) in events:
        for i,n in enumerate(sn):
            if n!=qn[anchor]: continue
            fill=[c for c in k[i] if p['labels'][c]==slot_label]
            if len(fill)!=1: continue
            ok=0
            for lab,word in constraints:
                for c in k[i]:
                    lo,hi=span(c)
                    if p['labels'][c]==lab and word in sn[lo:hi+1]: ok+=1; break
            lo,hi=span(fill[0])
            if any(sn[j] in set(qn) and _is_word(toks[j]) and sn[j]!=key for j in range(lo,hi+1)): continue
            best.append((ok,' '.join(t for t in toks[lo:hi+1] if t not in ('.',',')) ))
    if not best: return None
    top=max(b[0] for b in best); cands={b[1] for b in best if b[0]==top}
    if len(cands)!=1 or (constraints and top==0): return None
    return cands.pop()
