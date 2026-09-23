"""F-11 pilot: query real feedback where bounded semantic programs disagree.

Only unlabeled text and identifiers are visible to the selector. Environment
annotations are supplied later by the evaluator, never fabricated here.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import log2
from time import process_time

from leobot.language import normalize
from experiments.f10_contrastive_grammar import ContrastiveGrammar,generate,parse,_tokens


def _bigrams(text):
    words=[word for word,_,_ in _tokens(normalize(text))]
    return set(zip(words,words[1:]))


def select_queries(labeled,unlabeled,count=20):
    """Return ids plus audit data; labels of ``unlabeled`` are inaccessible."""
    started=process_time()
    if any(set(row)!={'id','text'} for row in unlabeled):
        raise ValueError('El selector solo admite identificador y texto')
    programs,pairs=generate(labeled)
    index=ContrastiveGrammar._index(programs,labeled)
    known=set().union(*(_bigrams(row['text']) for row in labeled)) if labeled else set()
    rivals=[];gaps=[];singles=[];analyses=0
    for row in unlabeled:
        text=row['text'];triggered=ContrastiveGrammar._triggered(index,text)
        frequencies=Counter()
        for number in triggered:
            item=programs[number]
            for args in parse(item['program'],text):
                frequencies[(item['predicate'],args)]+=1
        analyses+=len(triggered)
        digest=sha256(row['id'].encode()).hexdigest()
        if len(frequencies)>1:
            total=sum(frequencies.values())
            entropy=-sum((n/total)*log2(n/total) for n in frequencies.values())
            value=entropy/max(1,len(triggered))
            rivals.append((-value,-len(frequencies),digest,row['id']))
        elif not frequencies:
            grams=_bigrams(text)
            novelty=len(grams-known)/max(1,len(grams))
            gaps.append((-novelty,digest,row['id']))
        else:
            singles.append((len(triggered),digest,row['id']))
    rivals.sort();gaps.sort();singles.sort()
    gap_quota=max(1,count//5)
    selected=[row[-1] for row in rivals[:count-gap_quota]]
    selected.extend(row[-1] for row in gaps[:gap_quota])
    used=set(selected)
    remaining=[row[-1] for row in (*rivals,*gaps,*singles)
               if row[-1] not in used]
    selected.extend(remaining[:max(0,count-len(selected))])
    return selected[:count],{'programs':len(programs),'source_pairs':pairs,
        'rival_texts':len(rivals),'representation_gaps':len(gaps),
        'single_analysis_texts':len(singles),'analyses':analyses,
        'cpu_s':round(process_time()-started,6)}
