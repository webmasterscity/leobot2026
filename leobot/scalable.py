"""Scalable bot facade: disk-backed facts + compact cognitive sidecar."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .bot import Bot
from .concepts import ConceptGrounder
from .core import Rule
from .diskkb import SQLiteKnowledgeBase
from .language import Language
from .metacontrol import MetaController
from .metarepr import MetaRepresentationLibrary
from .programs import ProgramLearner
from .procedures import ProcedureGrounder
from .schemas import OpenArityConceptGrounder
from .symbolic import SymbolicWorldLearner
from .state_fields import plain_state, restore_plain_state
from .sequence_learner import SequenceLearner


class ScalableBot(Bot):
    def __init__(self, db_path: str | Path, grounding_min_support: int = 2,
                 raw_relation_min_support: int = 3, allow_extensional_grounding: bool = False,
                 raw_relation_max_arity: int = 8) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(SQLiteKnowledgeBase(self.db_path),
                         grounding_min_support=grounding_min_support,
                         raw_relation_min_support=raw_relation_min_support,
                         allow_extensional_grounding=allow_extensional_grounding,
                         raw_relation_max_arity=raw_relation_max_arity)

    def save(self, path: str | Path) -> None:
        """Save only compact cognitive state; bulk facts remain in SQLite."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bot.as_dict() would serialize the complete in-memory KB. The SQLite
        # sidecar includes only learned metadata; facts stay in the database.
        data = {
            'version': 1,
            'db_path': str(self.db_path),
            'language': self.language.as_dict(),
            'grounded_language': self.grounded_language,
            'allow_extensional_grounding': self.allow_extensional_grounding,
            'grounding_min_support': self.grounding_min_support,
            'raw_relation_min_support': self.raw_relation_min_support,
            'raw_relation_max_arity': self.raw_relation_max_arity,
            'programs': self.programs.as_dict(),
            'procedures': self.procedures.as_dict(),
            'sequence_learner': self.sequence_learner.as_dict(),
            'symbolic': self.symbolic.as_dict(),
            'concepts': self.concepts.as_dict(),
            'schemas': self.schemas.as_dict(),
            'meta_representations': self.meta_representations.as_dict(),
            'meta_controller': self.meta_controller.as_dict(),
        }
        data.update(plain_state(self))
        data.update({
            'last_fact': self.last_fact,
            'discourse_facts': self.discourse_facts,
            'discourse_referents': self.discourse_referents,
            'discourse_max_referents': self.discourse_max_referents,
            'last_symbolic_state': ([list(f) for f in self.last_symbolic_state]
                                    if self.last_symbolic_state is not None else None),
            'symbolic_entities': sorted(self.symbolic_entities),
            'kb_rules': [r.as_dict() for r in self.kb.rules.values()],
            'kb_examples': {
                pred: [{'args': list(args), 'labels': sorted(labels)}
                       for args, labels in examples.items()]
                for pred, examples in self.kb.examples.items()
            },
            'kb_audit': self.kb.audit,
        })
        self.kb.db.commit()
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str | Path, db_path: str | Path | None = None) -> 'ScalableBot':
        data = json.loads(Path(path).read_text(encoding='utf8'))
        if data.get('version') != 1:
            raise ValueError('Estado escalable no compatible.')

        bot = cls(db_path or data['db_path'],
                  grounding_min_support=data.get('grounding_min_support', 2),
                  raw_relation_min_support=data.get('raw_relation_min_support', 3),
                  allow_extensional_grounding=data.get('allow_extensional_grounding', False),
                  raw_relation_max_arity=data.get('raw_relation_max_arity', 8))
        bot.grounded_language = bool(data.get('grounded_language', True))
        bot.language = Language.from_dict(data['language'])
        bot.programs = ProgramLearner.from_dict(data['programs'])
        bot.procedures = ProcedureGrounder.from_dict(data.get('procedures', {}), bot.programs)
        bot.sequence_learner = SequenceLearner.from_dict(data.get('sequence_learner', {}))
        bot.symbolic = SymbolicWorldLearner.from_dict(data.get('symbolic', {}))
        bot.concepts = ConceptGrounder.from_dict(data.get('concepts', {}), bot.kb)
        bot.schemas = OpenArityConceptGrounder.from_dict(data.get('schemas', {}), bot.kb)
        bot.meta_representations = MetaRepresentationLibrary.from_dict(
            data.get('meta_representations', {}))
        bot.meta_controller = MetaController.from_dict(data.get('meta_controller', {}))
        bot._sync_meta_controller()
        bot._sync_meta_representations()

        # Rules and examples are the small executable part of the KB. Fact rows
        # are already in SQLite and are never materialized during this restore.
        for rule_data in data.get('kb_rules', []):
            bot.kb.add_rule(Rule.from_dict(rule_data))
        bot.kb.examples = {
            pred: {tuple(row['args']): set(row['labels']) for row in entries}
            for pred, entries in data.get('kb_examples', {}).items()
        }
        bot.kb.audit = data.get('kb_audit', [])

        bot.last_fact = data.get('last_fact')
        bot.discourse_facts = [
            fid for fid in data.get('discourse_facts', [])
            if isinstance(fid, str) and bot.kb.get_fact(fid) is not None
        ][-32:]
        if (bot.last_fact and bot.last_fact not in bot.discourse_facts
                and bot.kb.get_fact(bot.last_fact) is not None):
            bot.discourse_facts.append(bot.last_fact)

        # An absent key in an older version-1 sidecar keeps Bot's own default.
        restore_plain_state(bot, data)
        bot._restore_raw_consumption()

        bot.discourse_max_referents = max(4, int(data.get('discourse_max_referents', 32)))
        bot.discourse_referents = list(data.get('discourse_referents', []))[
            -bot.discourse_max_referents:]
        state = data.get('last_symbolic_state')
        bot.last_symbolic_state = [tuple(fact) for fact in state] if state is not None else None
        bot.symbolic_entities = set(data.get('symbolic_entities', []))
        return bot

    def close(self) -> None:
        self.kb.close()
