"""Disk-backed fact memory for Leobot V3.

Facts live in SQLite with positional and entity indexes. Rules/examples stay in
small in-memory metadata because they are executable/learned structure rather
than the bulk episodic fact store. The class implements the subset of
KnowledgeBase used by Engine and RelationalLearner.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re
import sqlite3
import hashlib
import json
from .core import Atom, Rule, variable, unify

# G-38b: file format with the trigger-maintained atom table.
FORMAT_VERSION = 2


class SQLiteKnowledgeBase:
    def __init__(self, path: str | Path, pragmas: bool = True) -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        if pragmas:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=NORMAL')
            self.db.execute('PRAGMA temp_store=MEMORY')
            self.db.execute('PRAGMA cache_size=-32768')
        cols = ','.join(f'a{i} TEXT' for i in range(8))
        self.db.execute(f'''CREATE TABLE IF NOT EXISTS facts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pred TEXT NOT NULL,
            base_pred TEXT NOT NULL,
            arity INTEGER NOT NULL,
            {cols},
            source TEXT NOT NULL,
            fact_key TEXT NOT NULL UNIQUE
        )''')
        # G-38: exact-atom index; equal atoms from different sources sit together.
        # G-38b: positional lookups go through the atom table, so facts keep
        # only this index (its prefixes serve pred and pred+a0).
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_facts_atom ON facts(pred,' +
                        ','.join(f'a{i}' for i in range(8)) + ')')
        # A compact digest-free uniqueness index: unused columns are NULL and SQLite
        # permits duplicate NULLs, so dedup is enforced explicitly before insert.
        self.db.execute('''CREATE TABLE IF NOT EXISTS fact_entities(
            fid INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
            entity TEXT NOT NULL,
            base_pred TEXT NOT NULL,
            PRIMARY KEY(fid,entity,base_pred)
        )''')
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_entity_pred ON fact_entities(entity,base_pred)')
        present = self.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN "
                                  "('atoms','facts_atoms_insert','facts_atoms_delete','facts_atoms_update')").fetchone()[0]
        if self.db.execute('PRAGMA user_version').fetchone()[0] < FORMAT_VERSION or present < 4:
            self._migrate()
        self.db.commit()
        self.arity: dict[str, int] = {r['base_pred']: r['arity'] for r in self.db.execute(
            'SELECT base_pred, MAX(arity) AS arity FROM facts GROUP BY base_pred')}
        self.rules: dict[str, Rule] = {}
        self.heads: dict[str, dict[str, Rule]] = defaultdict(dict)
        self.examples: dict[str, dict[tuple[str, str], set[bool]]] = {}
        self.audit: list[dict] = []
        self.revision = 0

    def close(self) -> None:
        self.db.commit(); self.db.close()

    def _check(self, a: Atom, commit: bool = True) -> None:
        pred = a.pred.lstrip('!')
        if pred in self.arity and self.arity[pred] != len(a.args):
            raise ValueError(f'Aridad incompatible: {pred}.')
        if commit:
            self.arity[pred] = len(a.args)

    @staticmethod
    def _fact_key(pred: str, source: str, args) -> str:
        payload = json.dumps([pred, source, *args], ensure_ascii=False).encode('utf8')
        return hashlib.blake2b(payload, digest_size=16).hexdigest()

    def _migrate(self) -> None:
        """G-38b: one-time upgrade of an older file, in a single transaction.

        One row per distinct atom (its oldest fact and number of sources) is kept
        by triggers inside the file, so any writer keeps it current.  The key
        is (pred, arity, k0..k7) with ki = ai or '' beyond the arity: exact, no hash.
        """
        ks = ','.join(f'k{i}' for i in range(8))
        key = ' AND '.join(['pred=old.pred', 'arity=old.arity'] + [f"k{i}=ifnull(old.a{i},'')" for i in range(8)])
        same = ' AND '.join(['pred=old.pred'] + [f'a{i} IS old.a{i}' for i in range(8)])
        new_values = ','.join(['new.pred', 'new.arity'] + [f"ifnull(new.a{i},'')" for i in range(8)] + ['new.id', '1'])
        on_insert = (f'INSERT INTO atoms(pred,arity,{ks},first,n) VALUES({new_values}) ON CONFLICT({"pred,arity," + ks}) '
                     'DO UPDATE SET n=n+1, first=min(first, excluded.first);')
        on_delete = (f'UPDATE atoms SET n=n-1 WHERE {key}; DELETE FROM atoms WHERE {key} AND n<=0; '
                     f'UPDATE atoms SET first=(SELECT MIN(id) FROM facts INDEXED BY ix_facts_atom WHERE {same}) '
                     f'WHERE {key} AND first=old.id;')
        self.db.execute('BEGIN')
        try:
            for name in ('facts_atoms_insert', 'facts_atoms_delete', 'facts_atoms_update'):
                self.db.execute(f'DROP TRIGGER IF EXISTS {name}')
            self.db.execute('DROP TABLE IF EXISTS atoms')
            for name in ['ix_facts_pred'] + [f'ix_facts_pred_a{i}' for i in range(8)]:
                self.db.execute(f'DROP INDEX IF EXISTS {name}')
            self.db.execute(f'''CREATE TABLE atoms(
                id INTEGER PRIMARY KEY,
                pred TEXT NOT NULL, arity INTEGER NOT NULL,
                {','.join(f'k{i} TEXT NOT NULL' for i in range(8))},
                first INTEGER NOT NULL, n INTEGER NOT NULL,
                UNIQUE(pred,arity,{ks}))''')
            self.db.execute('CREATE INDEX ix_atoms_pred ON atoms(pred,first)')
            for i in range(1, 8):
                self.db.execute(f'CREATE INDEX ix_atoms_pred_k{i} ON atoms(pred,k{i})')
            self.db.execute(f"INSERT INTO atoms(pred,arity,{ks},first,n) SELECT pred,arity,{','.join(f'ifnull(a{i},{chr(39)*2})' for i in range(8))},"
                            f"MIN(id),COUNT(*) FROM facts GROUP BY pred,arity,{','.join(f'a{i}' for i in range(8))}")
            self.db.execute(f'CREATE TRIGGER facts_atoms_insert AFTER INSERT ON facts BEGIN {on_insert} END')
            self.db.execute(f'CREATE TRIGGER facts_atoms_delete AFTER DELETE ON facts BEGIN {on_delete} END')
            self.db.execute(f'CREATE TRIGGER facts_atoms_update AFTER UPDATE OF pred,arity,{",".join(f"a{i}" for i in range(8))} '
                            f'ON facts BEGIN {on_delete} {on_insert} END')
            rows = self.db.execute('SELECT id,pred,arity,source,' + ','.join(f'a{i}' for i in range(8)) + ' FROM facts').fetchall()
            self.db.executemany('UPDATE facts SET fact_key=? WHERE id=?',
                                [(self._fact_key(r['pred'], r['source'], [r[f'a{i}'] for i in range(r['arity'])]), r['id'])
                                 for r in rows])
            self.db.execute(f'PRAGMA user_version={FORMAT_VERSION}')
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _row_to_fact(self, row: sqlite3.Row) -> dict:
        args = tuple(row[f'a{i}'] for i in range(row['arity']))
        return {'id': f"f{row['id']}", 'atom': Atom(row['pred'], args), 'source': row['source']}

    def add(self, atom: Atom, source: str = 'usuario') -> str:
        if not atom.ground:
            raise ValueError('Un hecho no puede contener variables.')
        self._check(atom)
        fact_key = self._fact_key(atom.pred, source, atom.args)
        row = self.db.execute('SELECT id FROM facts WHERE fact_key=?', (fact_key,)).fetchone()
        if row:
            return f"f{row['id']}"
        cols = ['pred','base_pred','arity'] + [f'a{i}' for i in range(8)] + ['source','fact_key']
        data = [atom.pred, atom.pred.lstrip('!'), len(atom.args)] + list(atom.args) + [None]*(8-len(atom.args)) + [source,fact_key]
        cur = self.db.execute('INSERT INTO facts(' + ','.join(cols) + ') VALUES(' + ','.join('?' for _ in cols) + ')', data)
        fid = cur.lastrowid
        self.db.executemany('INSERT OR IGNORE INTO fact_entities(fid,entity,base_pred) VALUES(?,?,?)',
                            [(fid, v, atom.pred.lstrip('!')) for v in set(atom.args)])
        self.revision += 1
        return f'f{fid}'

    def bulk_add(self, atoms, source: str = 'dataset', commit_every: int = 10000) -> int:
        before = self.count_facts()
        for i, atom in enumerate(atoms, 1):
            self.add(atom, source)
            if i % commit_every == 0:
                self.db.commit()
        self.db.commit()
        return self.count_facts() - before

    def get_fact(self, fid: str) -> dict | None:
        if not re.fullmatch(r'f[1-9][0-9]*', fid):
            return None
        row = self.db.execute('SELECT * FROM facts WHERE id=?', (int(fid[1:]),)).fetchone()
        return self._row_to_fact(row) if row else None

    def fact_source(self, fid: str) -> str:
        fact = self.get_fact(fid)
        return fact['source'] if fact else 'retirado'

    def remove(self, fid: str) -> bool:
        fact = self.get_fact(fid)
        if not fact:
            return False
        self.db.execute('DELETE FROM facts WHERE id=?', (int(fid[1:]),))
        self.revision += 1
        return True

    def replace(self, fid: str, new: Atom) -> str:
        old = self.get_fact(fid)
        if not old:
            raise ValueError('No existe el hecho que quieres corregir.')
        self._check(new, commit=False)
        self.remove(fid)
        nid = self.add(new, old['source'])
        self.audit.append({'event':'correction','old':fid,'new':nid,
                           'old_atom':old['atom'].as_dict(),'new_atom':new.as_dict(),
                           'source':old['source']})
        return nid

    def _atom_filter(self, pattern: Atom) -> tuple[str, str, list]:
        """FROM/WHERE over the atom table for a non-ground pattern."""
        where, vals = ['a.pred=?', 'a.arity=?'], [pattern.pred, len(pattern.args)]
        for i, value in enumerate(pattern.args):
            if not variable(value):
                where.append(f'a.k{i}=?'); vals.append(value)
        # Without statistics the planner may scan a whole predicate to avoid
        # sorting; use the unique key when the first argument is known (the
        # unary + keeps the ordering from choosing an index), else its index.
        bound = [i for i, value in enumerate(pattern.args) if not variable(value)]
        if not bound:
            index = 'INDEXED BY ix_atoms_pred'
        elif bound[0] == 0:
            index = ''
        else:
            index = f'INDEXED BY ix_atoms_pred_k{bound[0]}'
        return f'atoms a {index}', ' AND '.join(where), vals

    def matches(self, pattern: Atom):
        """Every fact matching ``pattern``, one per source, in id order."""
        self._check(pattern, commit=False)
        if pattern.ground:
            where = ' AND '.join(['pred=?'] + [f'a{i}=?' for i in range(len(pattern.args))] +
                                 [f'a{i} IS NULL' for i in range(len(pattern.args), 8)])
            sql = f'SELECT * FROM facts INDEXED BY ix_facts_atom WHERE {where} ORDER BY id'
            vals = [pattern.pred, *pattern.args]
        else:
            source, where, vals = self._atom_filter(pattern)
            same = ' AND '.join(['f.pred=a.pred'] + [f'f.a{i} IS (CASE WHEN a.arity>{i} THEN a.k{i} END)'
                                                     for i in range(8)])
            sql = (f'SELECT f.* FROM {source} JOIN facts f INDEXED BY ix_facts_atom ON {same} '
                   f'WHERE {where} ORDER BY f.id')
        for row in self.db.execute(sql, vals):
            fact = self._row_to_fact(row)
            if unify(pattern.args, fact['atom'].args) is not None:
                yield fact

    def distinct_matches(self, pattern: Atom):
        """The oldest fact of each distinct matching atom, in the order of its id."""
        self._check(pattern, commit=False)
        if pattern.ground:
            where = ' AND '.join(['a.pred=?', 'a.arity=?'] + [f'a.k{i}=?' for i in range(8)])
            vals = [pattern.pred, len(pattern.args), *pattern.args, *[''] * (8 - len(pattern.args))]
            sql = f'SELECT f.* FROM atoms a JOIN facts f ON f.id=a.first WHERE {where}'
        else:
            source, where, vals = self._atom_filter(pattern)
            order = '+a.first' if 'INDEXED' not in source else 'a.first'
            sql = f'SELECT f.* FROM {source} JOIN facts f ON f.id=a.first WHERE {where} ORDER BY {order}'
        for row in self.db.execute(sql, vals):
            fact = self._row_to_fact(row)
            if unify(pattern.args, fact['atom'].args) is not None:
                yield fact

    def contains(self, atom: Atom) -> bool:
        return next(self.distinct_matches(atom), None) is not None

    def predicates_for_entities(self, entities: set[str]) -> dict[str, int]:
        if not entities:
            return {}
        result: dict[str,int] = defaultdict(int)
        values = list(entities)
        for start in range(0, len(values), 500):
            chunk = values[start:start+500]
            q = ','.join('?' for _ in chunk)
            for row in self.db.execute(f'''SELECT base_pred, COUNT(DISTINCT entity) AS n
                                           FROM fact_entities WHERE entity IN ({q})
                                           GROUP BY base_pred''', chunk):
                result[row['base_pred']] += int(row['n'])
        return dict(result)

    def known_entities(self, candidates: set[str]) -> set[str]:
        if not candidates:
            return set()
        found: set[str] = set(); values = list(candidates)
        for start in range(0, len(values), 500):
            chunk = values[start:start+500]; q = ','.join('?' for _ in chunk)
            for row in self.db.execute(f'SELECT DISTINCT entity FROM fact_entities WHERE entity IN ({q})', chunk):
                found.add(str(row['entity']))
        return found

    def neighbor_entities(self, entities: set[str], predicates: set[str] | None = None,
                          max_neighbors: int = 512) -> set[str]:
        if not entities or max_neighbors <= 0:
            return set()
        out: set[str] = set(); values = sorted(entities)
        pred_values = sorted(predicates) if predicates else None
        for start in range(0, len(values), 400):
            chunk=values[start:start+400]; q=','.join('?' for _ in chunk)
            where=[f'e.entity IN ({q})','f.arity=2']; params=list(chunk)
            if pred_values:
                pq=','.join('?' for _ in pred_values)
                where.append(f'f.base_pred IN ({pq})');params.extend(pred_values)
            sql=('SELECT f.a0,f.a1 FROM fact_entities e JOIN facts f ON f.id=e.fid WHERE ' +
                 ' AND '.join(where))
            for row in self.db.execute(sql,params):
                for value in (row['a0'],row['a1']):
                    if value is not None and value not in entities:
                        out.add(str(value))
                        if len(out) >= max_neighbors:
                            return out
        return out

    def add_rule(self, rule: Rule) -> None:
        proposed = dict(self.arity)
        for a in (rule.head, *rule.body):
            p = a.pred.lstrip('!')
            if p in proposed and proposed[p] != len(a.args):
                raise ValueError(f'Aridad incompatible: {p}.')
            proposed[p] = len(a.args)
        self.remove_rule(rule.id)
        self.arity = proposed
        self.rules[rule.id] = rule
        self.heads[rule.head.pred][rule.id] = rule
        self.revision += 1

    def remove_rule(self, rid: str) -> None:
        if rid in self.rules:
            rule = self.rules.pop(rid)
            self.heads[rule.head.pred].pop(rid, None)
            self.revision += 1

    def withdraw_learned(self, target: str) -> int:
        todo, seen, removed = [target], set(), 0
        while todo:
            pred = todo.pop()
            if pred in seen: continue
            seen.add(pred)
            for rule in list(self.rules.values()):
                if rule.origin == 'learned' and (rule.head.pred == pred or any(a.pred == pred for a in rule.body)):
                    todo.append(rule.head.pred); self.remove_rule(rule.id); removed += 1
        return removed

    def add_example(self, target: str, args: tuple[str,str], positive: bool) -> bool:
        a = Atom(target, tuple(args))
        if not a.ground or len(args) != 2 or not isinstance(positive, bool):
            raise ValueError('Se requieren un par concreto y una etiqueta booleana.')
        self._check(a)
        labels = self.examples.setdefault(target, {}).setdefault(tuple(args), set())
        if positive in labels: return False
        labels.add(positive)
        removed = self.withdraw_learned(target)
        self.audit.append({'event':'example','target':target,'args':list(args),'positive':positive,'withdrawn_rules':removed})
        return True

    def count_facts(self) -> int:
        return int(self.db.execute('SELECT COUNT(*) FROM facts').fetchone()[0])

    def stats(self) -> dict:
        return {'facts': self.count_facts(), 'rules': len(self.rules), 'predicates': len(self.arity),
                'examples': sum(len(v) for v in self.examples.values()), 'revision': self.revision,
                'disk_backed': True, 'path': self.path}
