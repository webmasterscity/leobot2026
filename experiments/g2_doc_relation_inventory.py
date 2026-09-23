"""Read-only inventory of explicit method references and parallel prose."""
from __future__ import annotations

import json
import re
import resource
import time
from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g1_active_tool_docs_dev import (
    DOC_SHA, DEVELOPMENT_GROUPS, TRAIN_GROUPS,
)
from experiments.g1_tool_docs_inventory import MethodParser, URL


ROOT = Path(__file__).resolve().parents[1]


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: str | None = None
        self.in_description = False
        self.in_first_paragraph = False
        self.finished: set[str] = set()
        self.refs: dict[str, set[str]] = defaultdict(set)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == 'dt':
            value = attrs_map.get('id') or ''
            self.current = value if re.fullmatch(r'str\.[A-Za-z_][A-Za-z_0-9]*', value) else None
            self.in_description = False
            self.in_first_paragraph = False
        elif tag == 'dd' and self.current:
            self.in_description = True
        elif tag == 'p' and self.current and self.in_description and self.current not in self.finished:
            self.in_first_paragraph = True
        elif tag == 'a' and self.current and self.in_first_paragraph:
            href = attrs_map.get('href') or ''
            if re.fullmatch(r'#str\.[A-Za-z_][A-Za-z_0-9]*', href):
                self.refs[self.current].add(href[1:])

    def handle_endtag(self, tag: str) -> None:
        if tag == 'p' and self.in_first_paragraph and self.current:
            self.finished.add(self.current)
            self.in_first_paragraph = False
        elif tag == 'dd' and self.in_description:
            self.current = None
            self.in_description = False


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    with urlopen(URL, timeout=20) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if sha256(raw).hexdigest() != DOC_SHA:
        raise RuntimeError('Documento cambió')
    paragraphs = MethodParser()
    paragraphs.feed(raw.decode('utf8'))
    links = ReferenceParser()
    links.feed(raw.decode('utf8'))
    edges = {name: sorted(target for target in targets
                          if target in paragraphs.methods and target != name)
             for name, targets in sorted(links.refs.items())}
    edges = {name: targets for name, targets in edges.items() if targets}
    pairs = []
    for left, right in (*TRAIN_GROUPS, *DEVELOPMENT_GROUPS):
        first = re.findall(r'[^\W_]+', paragraphs.methods['str.' + left].casefold())
        second = re.findall(r'[^\W_]+', paragraphs.methods['str.' + right].casefold())
        pairs.append({'methods': [left, right],
                      'token_similarity': round(SequenceMatcher(
                          None, first, second, autojunk=False).ratio(), 6),
                      'mutual_reference': 'str.' + right in edges.get('str.' + left, ())
                      or 'str.' + left in edges.get('str.' + right, ())})
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'engine_tree': tree,
        'document_sha256': DOC_SHA, 'methods': len(paragraphs.methods),
        'methods_with_outgoing_reference': len(edges),
        'outgoing_references': edges, 'contrast_pairs': pairs,
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g2_doc_relation_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
