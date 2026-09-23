"""Post-hoc provenance audit of the F-6e role-set sources (no new gate)."""
from __future__ import annotations

import json
from collections import Counter
from hashlib import blake2b

from experiments.b1_aggregate_operator import ROOT
from experiments.f6e_human_text_grounding import download_split, frozen, select_train, teach


def main():
    tree=frozen()
    all_rows,_,_=download_split('train')
    chosen=select_train(all_rows,tree)
    bot,report=teach(chosen,'global',tree)
    rdf_by_episode={}
    for row in chosen:
        world=json.dumps([[],[(row['predicate'],row['subject'],row['object'])]],
                         ensure_ascii=False)
        digest=blake2b(world.encode('utf8'),digest_size=12).hexdigest()
        rdf_by_episode[digest]=row['predicate']
    sources=[]
    for role_set in bot.meta_representations.rows():
        if role_set.get('kind')!='role_set' or 'raw_world' not in role_set.get('families',{}):
            continue
        for source in sorted(role_set['sources']):
            predicate=source.removeprefix('raw_world:')
            promotion=next((row for row in bot.raw_relation_promotions.values()
                            if row.get('predicate')==predicate),None)
            state=bot.raw_world_alignment_hypotheses.get(predicate,{})
            properties=Counter(rdf_by_episode.get(obs['episode'],'<missing>')
                               for obs in state.get('observations',()))
            sources.append({'role_set':role_set['schema'],'source':source,
                            'surface':promotion.get('surface') if promotion else None,
                            'initial_text_support':promotion.get('support') if promotion else None,
                            'world_observations':len(state.get('observations',())),
                            'distinct_rdf_properties':len(properties),
                            'rdf_properties':dict(sorted(properties.items()))})
    output={'source_result':'results_v3/f6e_human_text_grounding.json',
            'engine_tree':tree,'source_rows':len(chosen),
            'raw_promotions':report['raw_promotions'],
            'role_set_sources':sources,'engine_unchanged':frozen()==tree}
    path=ROOT/'results_v3'/'f6e_human_text_audit.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    main()
