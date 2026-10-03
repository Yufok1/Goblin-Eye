"""Player-controlled continuity for any MCP-capable agent.

Entries are personal notes, not imported world facts. Text is immutable; status
changes are audited. Agents must keep their inferences distinct from player reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from goblin_eye.repository import Database


KINDS = ('goal', 'note', 'session')
STATUSES = ('active', 'completed', 'archived')
BASES = ('player_report', 'agent_inference', 'sourced_evidence')
AUTHORS = ('player', 'agent')


def _choice(value: Any, label: str, choices: tuple[str, ...]) -> str:
    if type(value) is not str or value not in choices:
        raise ValueError(f"{label} must be one of: {', '.join(choices)}")
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f'{label} must be nonempty text of at most {maximum} characters')
    return value.strip()


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 64:
        raise ValueError('occurred_at must be a timezone-qualified ISO 8601 timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('occurred_at must be a timezone-qualified ISO 8601 timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('occurred_at must include a timezone')
    return parsed.isoformat()


class CompanionStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _entry(row) -> dict[str, Any]:
        value = dict(row)
        value['evidence_refs'] = json.loads(value.pop('evidence_refs_json'))
        return value

    def add(self, kind: str, title: str, body: str, basis: str,
            author: str = 'player', character_snapshot_id: int | None = None,
            evidence_refs: list[str] | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        _choice(kind, 'kind', KINDS)
        title = _text(title, 'title', 160)
        body = _text(body, 'body', 8000)
        _choice(basis, 'basis', BASES)
        _choice(author, 'author', AUTHORS)
        if character_snapshot_id is not None and (type(character_snapshot_id) is not int or character_snapshot_id < 1):
            raise ValueError('character_snapshot_id must be a positive integer')
        if evidence_refs is None:
            evidence_refs = []
        if not isinstance(evidence_refs, list) or len(evidence_refs) > 20 or any(type(ref) is not str or not ref.strip() or len(ref) > 240 for ref in evidence_refs):
            raise ValueError('evidence_refs must be an array of at most 20 nonempty references, each at most 240 characters')
        if basis == 'sourced_evidence' and not evidence_refs:
            raise ValueError('sourced_evidence requires at least one explicit evidence reference')
        occurred_at = _timestamp(occurred_at)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction() as connection:
            if character_snapshot_id is not None and not connection.execute('SELECT 1 FROM character_snapshots WHERE id=?', (character_snapshot_id,)).fetchone():
                raise ValueError('character_snapshot_id does not exist')
            cursor = connection.execute('''INSERT INTO companion_entries
                (kind,title,body,status,basis,author,character_snapshot_id,evidence_refs_json,occurred_at,created_at,updated_at)
                VALUES (?,?,?,'active',?,?,?,?,?,?,?)''',
                (kind,title,body,basis,author,character_snapshot_id,json.dumps(evidence_refs,ensure_ascii=False),occurred_at,now,now))
            row = connection.execute('SELECT * FROM companion_entries WHERE id=?', (cursor.lastrowid,)).fetchone()
        return self._entry(row)

    def get(self, entry_id: int) -> dict[str, Any] | None:
        if type(entry_id) is not int or entry_id < 1:
            raise ValueError('entry_id must be a positive integer')
        with self.database.transaction() as connection:
            row = connection.execute('SELECT * FROM companion_entries WHERE id=?', (entry_id,)).fetchone()
            if row is None:
                return None
            events = [dict(event) for event in connection.execute(
                'SELECT old_status,new_status,author,changed_at FROM companion_status_events WHERE entry_id=? ORDER BY id', (entry_id,))]
        return {**self._entry(row), 'status_events': events}

    def list(self, kind: str | None = None, status: str | None = None,
             limit: int = 30, offset: int = 0) -> dict[str, Any]:
        if kind is not None: _choice(kind, 'kind', KINDS)
        if status is not None: _choice(status, 'status', STATUSES)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be an integer from 1 to 100')
        if type(offset) is not int or offset < 0:
            raise ValueError('offset must be a nonnegative integer')
        clauses = []
        args: list[Any] = []
        if kind is not None:
            clauses.append('kind=?'); args.append(kind)
        if status is not None:
            clauses.append('status=?'); args.append(status)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.database.transaction() as connection:
            total = connection.execute('SELECT COUNT(*) FROM companion_entries' + where, args).fetchone()[0]
            rows = connection.execute('SELECT * FROM companion_entries' + where +
                ' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?', [*args,limit,offset]).fetchall()
        records = [self._entry(row) for row in rows]
        return {'records':records,'total':total,'limit':limit,'offset':offset,
                'next_offset':offset+len(records) if offset+len(records)<total else None,
                'limitations':['Personal entries are user reports or agent notes, not verified game state or market evidence.']}

    def set_status(self, entry_id: int, status: str, author: str = 'player') -> dict[str, Any]:
        if type(entry_id) is not int or entry_id < 1:
            raise ValueError('entry_id must be a positive integer')
        _choice(status, 'status', STATUSES)
        _choice(author, 'author', AUTHORS)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT status FROM companion_entries WHERE id=?', (entry_id,)).fetchone()
            if row is None:
                raise ValueError('Companion entry not found')
            if row['status'] != status:
                connection.execute('UPDATE companion_entries SET status=?,updated_at=? WHERE id=?', (status,now,entry_id))
                connection.execute('INSERT INTO companion_status_events(entry_id,old_status,new_status,author,changed_at) VALUES (?,?,?,?,?)',
                                   (entry_id,row['status'],status,author,now))
        return self.get(entry_id)

    def context(self) -> dict[str, Any]:
        """Bounded handoff, avoiding a stale, model-written 'summary of truth'."""
        def brief(row):
            value = self._entry(row)
            if len(value['body']) > 600:
                value['body'] = value['body'][:600] + '…'
                value['body_truncated'] = True
            if value['evidence_refs']:
                shortened = len(value['evidence_refs']) > 3 or any(len(ref) > 120 for ref in value['evidence_refs'])
                value['evidence_refs'] = [ref[:120] for ref in value['evidence_refs'][:3]]
                if shortened: value['evidence_refs_truncated'] = True
            return value
        with self.database.transaction() as connection:
            goals = [brief(row) for row in connection.execute(
                "SELECT * FROM companion_entries WHERE kind='goal' AND status='active' ORDER BY updated_at DESC,id DESC LIMIT 10")]
            recent = [brief(row) for row in connection.execute(
                "SELECT * FROM companion_entries WHERE kind IN ('note','session') AND status='active' ORDER BY created_at DESC,id DESC LIMIT 5")]
            counts = {row['kind']:row['n'] for row in connection.execute(
                "SELECT kind,COUNT(*) n FROM companion_entries WHERE status='active' GROUP BY kind")}
        return {'queried_at':datetime.now(timezone.utc).isoformat(), 'active_goals':goals,
                'recent_notes_and_sessions':recent,'active_counts':counts,
                'limitations':['This is a bounded handoff; use list_companion_entries to page through older notes.',
                    'Entries are reports or interpretations, not live game state. Re-query Goblin Eye evidence before economic or character advice.',
                    'No model is embedded, and no gameplay actions are performed.']}
