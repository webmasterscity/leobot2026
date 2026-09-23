"""Read-only inventory of safe string-method traces and observable ambiguity."""
from __future__ import annotations

import json
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g1_tool_docs_inventory import MethodParser, URL


ROOT = Path(__file__).resolve().parents[1]
TEXTS = ('ababa', 'bcbc', 'ccc', 'a b a', '')
ARGUMENTS = ((), ('a',), ('b',), ('',), ('a', 'b'), ('b', 'a'), (2,))


def observe(method: str, text: str, args: tuple) -> tuple[str, str]:
    try:
        value = getattr(text, method)(*args)
        return type(value).__name__, repr(value)[:160]
    except (TypeError, ValueError, LookupError, UnicodeError, AttributeError) as exc:
        return 'error:' + type(exc).__name__, ''


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    with urlopen(URL, timeout=20) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError('Documento supera presupuesto')
    old = json.loads((ROOT / 'results_v3' / 'g1_tool_docs_inventory.json').read_text())
    if sha256(raw).hexdigest() != old['document_sha256']:
        raise RuntimeError('Documento cambió')
    parser = MethodParser()
    parser.feed(raw.decode('utf8'))
    names = sorted(name.split('.', 1)[1] for name in parser.methods
                   if callable(getattr(str, name.split('.', 1)[1], None)))
    success_by_arity = defaultdict(list)
    signatures = defaultdict(list)
    type_profiles = {}
    for name in names:
        profile = []
        for args in ARGUMENTS:
            observed = tuple(observe(name, text, args) for text in TEXTS)
            good = sum(not kind.startswith('error:') for kind, _ in observed)
            if good >= 4:
                success_by_arity[str(len(args))].append(name)
            if args == ('a',) and good >= 4:
                signatures[observed].append(name)
            profile.append({'argument_types': [type(arg).__name__ for arg in args],
                            'successful_texts': good,
                            'result_types': sorted({kind for kind, _ in observed})})
        type_profiles['str.' + name] = profile
    ambiguous = [group for group in signatures.values() if len(group) > 1]
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'engine_tree': tree,
        'document_sha256': sha256(raw).hexdigest(),
        'texts': list(TEXTS), 'argument_signatures': [list(args) for args in ARGUMENTS],
        'method_count': len(names),
        'methods_with_success_by_arity': {
            arity: sorted(set(group)) for arity, group in sorted(success_by_arity.items())},
        'one_string_argument_equivalence_groups': ambiguous,
        'type_profiles': type_profiles,
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g1_tool_trace_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('type_profiles',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
