import sys, json, collections
sys.path.insert(0,'.')
from experiments.g57_kiosco import businesses, plain
from experiments.nube_recuperacion import containing, make_bm25, unit_terms
from leobot import Bot
bot=Bot.load('.leobot-data/base_general_nube.json')
sc=make_bm25(True)
folders=sys.argv[1:]
c=collections.Counter(); bytype=collections.defaultdict(collections.Counter)
for name,text,ins,convs in businesses(folders):
    bot.load_context(text,ins); units=bot.context_units
    for conv in convs:
        for t in conv:
            if t.get('accion','responder')!='responder': continue
            keys=[k for k in t.get('claves') or [] if plain(k)]
            if not keys or t.get('tipo') not in ('directa','si_no'): continue
            gold={i for i,u in enumerate(units) if u['kind']!='question' and containing(u['text'],keys)}
            if not gold: continue
            terms=list(dict.fromkeys(bot.context_terms(t['cliente'])))
            s=sc(bot,terms,units)
            order=sorted((i for i,u in enumerate(units) if u['kind']!='question'),key=lambda i:(-s[i],i))
            top=order[0]
            first=min(order.index(g) for g in gold)
            top_ok = top in gold
            overlap=max((len(set(unit_terms(units[g]))&set(terms)) for g in gold),default=0)
            cls='top1' if top_ok else ('rank2-5' if first<5 else 'rank6+')
            k='overlap0' if overlap==0 else ('overlap1' if overlap==1 else 'overlap2+')
            c[(cls,k)]+=1
            # same heading as top?
            if not top_ok:
                g=min(gold,key=lambda g:order.index(g))
                same_head = units[top]['heading']==units[g]['heading'] and units[g]['heading']!=''
                adj = abs(top-g)==1
                bytype['wrong'][('same_heading' if same_head else 'diff_heading')]+=1
                bytype['wrong'][('adjacent' if adj else 'nonadjacent')]+=1
                bytype['wrong'][('top_kind_'+units[top]['kind'])]+=1
                bytype['wrong'][('gold_kind_'+units[g]['kind'])]+=1
n=sum(c.values()); print('n',n)
for k,v in sorted(c.items()): print(k,v,round(v/n,3))
for k,v in sorted(bytype['wrong'].items()): print(k,v)
