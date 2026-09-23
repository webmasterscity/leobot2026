"""Development prototype (outside the engine): lexical senses as presence."""
import types, pathlib
import leobot.reading as R
src=pathlib.Path(R.__file__).read_text()
src=src.replace("""        literal = {p: self._reading_overlap(qtokens, word_sets[p]) for p in candidates}
        scored = [(literal[p], p) for p in candidates]""","""        literal = {p: self._reading_overlap(qtokens, word_sets[p]) for p in candidates}
        senses = getattr(self, '_proto_senses', None)
        scored = [(self._sense_overlap(qtokens, word_sets[p]) if senses else literal[p], p) for p in candidates]""")
src=src.replace("""                cover[name] = sum(self._reading_idf(t) * (BM25_K1 + 1) / (1 + norm)
                                  for t in unique if t in words)""","""                cover[name] = sum(self._reading_idf(t) * (BM25_K1 + 1) / (1 + norm) * self._sense_presence(t, words)
                                  for t in unique)""")
src=src.replace("""    def consolidate_reading(self) -> dict:""","""    def _sense_presence(self, token, words):
        if token in words:
            return 1.0
        senses = getattr(self, '_proto_senses', None)
        if not senses or token not in senses:
            return 0.0
        mine = senses[token]
        return WEIGHT if any(w in senses and senses[w] & mine for w in words) else 0.0

    def _sense_overlap(self, question, words):
        total = sum(self._reading_idf(t) for t in question)
        return sum(self._reading_idf(t) * self._sense_presence(t, words) for t in question) / total if total else 0.0

    def consolidate_reading(self) -> dict:""")
src=src.replace("MAX_SPAN = 10\n","MAX_SPAN = 10\nWEIGHT = 0.5\n")
mod=types.ModuleType('reading_g34'); exec(compile(src,'reading_g34','exec'),mod.__dict__)
for name in ('answer_from_utterances','_sense_presence','_sense_overlap'):
    setattr(R.ReadingMemoryMixin,name,getattr(mod.ReadingMemoryMixin,name))
def load_senses(path,shuffle=None):
    import random
    pairs=[l.rstrip('\n').split('\t') for l in open(path,encoding='utf8') if not l.startswith('#')]
    pairs=[(p[0],p[2]) for p in pairs if len(p)>=3 and p[1]=='spa:lemma']
    if shuffle is not None:
        lemmas=[l for _,l in pairs]; random.Random(shuffle).shuffle(lemmas); pairs=[(s,l) for (s,_),l in zip(pairs,lemmas)]
    senses={}
    for sense,lemma in pairs:
        for word in lemma.split('_'):
            senses.setdefault(R._norm(word),set()).add(sense)
    return senses
