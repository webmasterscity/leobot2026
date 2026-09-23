"""Read-only inventory of Spanish prose adjacent to executable stdlib tools."""
from __future__ import annotations

import json
import re
import resource
import time
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
URL = 'https://docs.python.org/es/3.12/library/stdtypes.html'


class MethodParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: str | None = None
        self.in_description = False
        self.in_first_paragraph = False
        self.text_parts: list[str] = []
        self.methods: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == 'dt':
            identifier = attrs_map.get('id') or ''
            self.current = identifier if re.fullmatch(
                r'str\.[A-Za-z_][A-Za-z_0-9]*', identifier) else None
            self.in_description = False
            self.in_first_paragraph = False
        elif tag == 'dd' and self.current:
            self.in_description = True
        elif tag == 'p' and self.current and self.in_description and not self.current in self.methods:
            self.in_first_paragraph = True
            self.text_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_first_paragraph:
            self.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == 'p' and self.in_first_paragraph and self.current:
            text = ' '.join(' '.join(self.text_parts).split())
            if text:
                self.methods[self.current] = text
            self.in_first_paragraph = False
        elif tag == 'dd' and self.in_description:
            self.in_description = False
            self.current = None


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
    parser = MethodParser()
    parser.feed(raw.decode('utf8'))
    methods = {name: description for name, description in sorted(parser.methods.items())
               if callable(getattr(str, name.split('.', 1)[1], None))}
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'source_url': URL,
        'document_sha256': sha256(raw).hexdigest(), 'document_bytes': len(raw),
        'engine_tree': tree, 'method_paragraphs': len(parser.methods),
        'executable_methods': len(methods),
        'methods': {name: {'description_chars': len(description),
                           'description_sha256': sha256(description.encode()).hexdigest(),
                           'preview': description[:110]}
                    for name, description in methods.items()},
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g1_tool_docs_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key != 'methods'} | {'method_names': list(methods)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
