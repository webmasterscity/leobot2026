"""Scalable bot facade: disk-backed facts + compact cognitive sidecar."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from .bot import Bot
from .diskkb import SQLiteKnowledgeBase
from .core import Rule
from .language import Language
from .programs import ProgramLearner
from .procedures import ProcedureGrounder
from .symbolic import SymbolicWorldLearner
from .concepts import ConceptGrounder


class ScalableBot(Bot):
    def __init__(self, db_path: str | Path, grounding_min_support: int = 2) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(SQLiteKnowledgeBase(self.db_path), grounding_min_support=grounding_min_support)

    def save(self, path: str | Path) -> None:
        """Save only compact cognitive state; bulk facts remain in SQLite."""
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'version': 1,
            'db_path': str(self.db_path),
            'language': self.language.as_dict(),
            'grounded_language': self.grounded_language,
            'grounding_min_support': self.grounding_min_support,
            'grounding_hypotheses': self.grounding_hypotheses,
            'programs': self.programs.as_dict(),
            'procedures': self.procedures.as_dict(),
            'symbolic': self.symbolic.as_dict(),
            'concepts': self.concepts.as_dict(),
            'last_fact': self.last_fact,
            'training_reports': self.training_reports,
            'kb_rules': [r.as_dict() for r in self.kb.rules.values()],
            'kb_examples': {p:[{'args':list(a),'labels':sorted(labels)} for a,labels in es.items()]
                            for p,es in self.kb.examples.items()},
            'kb_audit': self.kb.audit,
        }
        self.kb.db.commit()
        fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf8') as out:
                json.dump(data,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    @classmethod
    def load(cls, path: str | Path, db_path: str | Path | None = None) -> 'ScalableBot':
        data=json.loads(Path(path).read_text(encoding='utf8'))
        if data.get('version') != 1: raise ValueError('Estado escalable no compatible.')
        bot=cls(db_path or data['db_path'], grounding_min_support=data.get('grounding_min_support',2)); bot.grounded_language=bool(data.get('grounded_language',True))
        bot.language=Language.from_dict(data['language'])
        bot.programs=ProgramLearner.from_dict(data['programs'])
        bot.procedures=ProcedureGrounder.from_dict(data.get('procedures',{}),bot.programs)
        bot.symbolic=SymbolicWorldLearner.from_dict(data.get('symbolic',{}))
        bot.concepts=ConceptGrounder.from_dict(data.get('concepts',{}), bot.kb)
        for rd in data.get('kb_rules',[]):bot.kb.add_rule(Rule.from_dict(rd))
        bot.kb.examples={p:{tuple(e['args']):set(e['labels']) for e in entries}
                         for p,entries in data.get('kb_examples',{}).items()}
        bot.kb.audit=data.get('kb_audit',[])
        bot.last_fact=data.get('last_fact');bot.grounding_hypotheses=data.get('grounding_hypotheses',{});bot.training_reports=data.get('training_reports',[])
        return bot

    def close(self) -> None:
        self.kb.close()
