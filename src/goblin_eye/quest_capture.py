"""Saved active quest and location observations; no live game access."""
import math
from datetime import datetime, timezone

from goblin_eye.character_capture import stamp, _id, _array


def _text(row, key):
    value = row.get(key)
    if value is not None and (not isinstance(value, str) or len(value.encode('utf-8')) > 200):
        raise ValueError(f'Invalid quest/location text: {key}')


def _count(row, key, maximum=100000000):
    value = row.get(key)
    if value is not None and (type(value) is not int or not 0 <= value <= maximum):
        raise ValueError(f'Invalid quest count: {key}')


def _status(row):
    if not isinstance(row, dict) or row.get('status') not in ('recorded', 'partial', 'not_recorded'):
        raise ValueError('Invalid quest/location coverage')


def validate_quest_capture(char):
    for key in ('goblinEyeQuestLog', 'goblinEyeLocation'):
        capture = char.get(key)
        if capture is None:
            continue
        _status(capture)
        if type(capture.get('version')) is not int or capture['version'] != 1:
            raise ValueError('Unsupported quest/location export')
        stamp(capture.get('capturedAt'))
        for field in ('build', 'locale'):
            _text(capture, field)
        if key == 'goblinEyeLocation':
            for field in ('zone', 'subZone'):
                _text(capture, field)
            if capture.get('uiMapID') is not None:
                _id(capture['uiMapID'])
            for field in ('x', 'y'):
                value = capture.get(field)
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
                    raise ValueError('Invalid normalized map coordinate')
            if (capture.get('x') is None) != (capture.get('y') is None):
                raise ValueError('Map coordinates require both axes')
            if capture.get('x') is not None and capture.get('uiMapID') is None:
                raise ValueError('Map coordinates require a UI map ID')
            if capture['status'] == 'recorded' and capture.get('x') is None:
                raise ValueError('Recorded location requires coordinates')
            continue
        _count(capture, 'reportedQuestCount', 100)
        entries = _array(capture.get('entries'), 100)
        seen = set()
        for row in entries:
            if not isinstance(row, dict):
                raise ValueError('Invalid active quest row')
            _id(row.get('questID'))
            if row['questID'] in seen:
                raise ValueError('Duplicate active quest ID')
            seen.add(row['questID'])
            _text(row, 'title'); _count(row, 'level', 1000)
            for flag in ('readyForTurnIn', 'complete', 'failed'):
                if row.get(flag) is not None and type(row[flag]) is not bool:
                    raise ValueError('Invalid active quest flag')
            objectives = row.get('objectives')
            _status(objectives)
            indexes = set()
            for objective in _array(objectives.get('records'), 20):
                if not isinstance(objective, dict):
                    raise ValueError('Invalid quest objective')
                _id(objective.get('index')); _count(objective, 'index', 20)
                if objective['index'] in indexes:
                    raise ValueError('Duplicate objective index')
                indexes.add(objective['index'])
                for field in ('text', 'type'):
                    _text(objective, field)
                for field in ('numFulfilled', 'numRequired'):
                    _count(objective, field)
                if objective.get('finished') is not None and type(objective['finished']) is not bool:
                    raise ValueError('Invalid objective completion flag')
            if objectives['status'] == 'not_recorded' and objectives['records']:
                raise ValueError('Unrecorded objectives cannot contain records')
        if capture['status'] == 'recorded' and capture.get('reportedQuestCount') != len(entries):
            raise ValueError('Quest log count does not match complete capture')
        if capture['status'] == 'not_recorded' and entries:
            raise ValueError('Unrecorded quest log cannot contain entries')


def evidence(capture, snapshot, field):
    if not capture:
        return {'status': 'not_captured', 'captured_at': None,
                'reason': 'No saved Alts observation. Updated extension and a normal game save are required.'}
    captured = stamp(capture['capturedAt'])
    age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(captured)).total_seconds())
    return {'status': capture['status'], 'captured_at': captured, 'imported_at': snapshot['imported_at'],
            'game_build': capture.get('build'), 'source_key': snapshot['source_key'],
            'raw_reference': snapshot['raw_reference'] + '/' + field,
            'evidence_kind': 'observed',
            'freshness': {'age_seconds': int(age), 'status': 'stale' if age > 300 else 'recent',
                          'timestamp_basis': 'client capture time; not live state'}}


def location(char, snapshot):
    capture = char.get('goblinEyeLocation')
    result = evidence(capture, snapshot, 'goblinEyeLocation')
    result.update(coordinate_units='normalized_0_to_1',
                  interpretation='Position observed on login/save only. It may differ from the current starting point; no movement tracking.')
    if capture:
        result.update({dest: capture.get(src) for src, dest in
                       (('zone', 'zone'), ('subZone', 'subzone'), ('uiMapID', 'ui_map_id'), ('x', 'x'), ('y', 'y'))})
    return result


def active_quests(char, snapshot, limit=20, offset=0):
    capture = char.get('goblinEyeQuestLog')
    result = evidence(capture, snapshot, 'goblinEyeQuestLog')
    raw = (capture or {}).get('entries', {})
    rows = [raw[k] for k in sorted(raw, key=int)]
    records = []
    for row in rows[offset:offset + limit]:
        objectives = row['objectives']
        records.append({'quest_id': row['questID'], 'title': row.get('title'), 'level': row.get('level'),
                        'ready_for_turn_in': row.get('readyForTurnIn'), 'complete': row.get('complete'),
                        'failed': row.get('failed'), 'objectives_status': objectives['status'],
                        'objectives': [{dest: obj.get(src) for src, dest in
                            (('index', 'index'), ('text', 'text'), ('type', 'type'), ('numFulfilled', 'fulfilled'),
                             ('numRequired', 'required'), ('finished', 'finished'))}
                            for obj in [objectives['records'][k] for k in sorted(objectives['records'], key=int)]]})
    result.update(records=records, total=len(rows), limit=limit, offset=offset,
                  next_offset=offset+len(records) if offset+len(records)<len(rows) else None,
                  reported_quest_count=(capture or {}).get('reportedQuestCount'),
                  interpretation='Accepted quests at capture time, separate from completed-quest history. Missing flags/progress are unknown. Partial or missing capture cannot establish an empty log. Use quest IDs with world evidence for starters, objectives and turn-ins; static catalogs remain current enrichment.')
    return result
