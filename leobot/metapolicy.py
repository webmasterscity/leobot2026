"""Domain-neutral search-policy language for replay-based meta-exploration.

Policies only order candidate metadata already produced by the relational learner.
They never inspect predicate names, task names, benchmark ids, answers, or held-out
labels.  This module is deliberately small so every learner uses the same policy
semantics and persistence validation.
"""
from __future__ import annotations
from itertools import permutations

LEGACY = {
    'reverse_first': (('inv','cat','p','q'), ('reverse','same','forward')),
    'forward_first': (('inv','cat','p','q'), ('forward','same','reverse')),
    'same_first': (('inv','cat','p','q'), ('same','forward','reverse')),
}
FEATURES = ('inv','cat','p','q')
CATEGORIES = ('same','forward','reverse')


def policy_spec(policy: str):
    if policy in LEGACY:
        return LEGACY[policy]
    if not isinstance(policy, str) or not policy.startswith('synth:'):
        return None
    try:
        _, feature_text, category_text = policy.split(':', 2)
        features = tuple(feature_text.split(','))
        categories = tuple(category_text.split(','))
    except Exception:
        return None
    if set(features) != set(FEATURES) or len(features) != len(FEATURES):
        return None
    if set(categories) != set(CATEGORIES) or len(categories) != len(CATEGORIES):
        return None
    return features, categories


def valid_policy(policy: str) -> bool:
    return policy == 'baseline' or policy_spec(policy) is not None


def policy_key(meta: dict, policy: str):
    if policy == 'baseline':
        return (int(meta['baseline_index']),)
    spec = policy_spec(policy)
    if spec is None:
        # Unknown persisted policies have no influence: deterministic baseline.
        return (int(meta['baseline_index']),)
    features, categories = spec
    values = {
        'inv': int(meta['inv_rank']),
        'cat': categories.index(meta['pair_category']),
        'p': int(meta['p_rank']),
        'q': int(meta['q_rank']),
    }
    return tuple(values[name] for name in features) + (int(meta['baseline_index']),)


def policy_family() -> tuple[str, ...]:
    """Return baseline + legacy controls + 144 synthesized lexicographic policies.

    Legacy policies come first so exact replay ties preserve historical behaviour.
    """
    out = ['baseline', 'reverse_first', 'forward_first', 'same_first']
    for features in permutations(FEATURES):
        for categories in permutations(CATEGORIES):
            name = 'synth:' + ','.join(features) + ':' + ','.join(categories)
            if name not in out:
                out.append(name)
    return tuple(out)
