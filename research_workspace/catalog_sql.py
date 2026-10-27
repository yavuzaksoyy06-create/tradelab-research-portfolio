"""Ephemeral SQL reports from freshly verified snapshots, without persistent writes."""
import sqlite3
from research_workspace.real_sources import catalog

SCHEMA = '''
CREATE TABLE sources(source_id TEXT PRIMARY KEY, publisher TEXT NOT NULL, unit TEXT NOT NULL);
CREATE TABLE versions(
 version_id TEXT PRIMARY KEY, source_id TEXT REFERENCES sources(source_id),
 status TEXT NOT NULL CHECK(status IN ('verified','rejected')),
 declared_rows INTEGER CHECK(declared_rows >= 0), collected_at TEXT, rejection_reason TEXT);
CREATE TABLE observations(
 version_id TEXT NOT NULL REFERENCES versions(version_id),
 observation_date TEXT NOT NULL, series TEXT NOT NULL, value REAL NOT NULL,
 PRIMARY KEY(version_id, observation_date, series));
'''
COVERAGE_SQL = '''
SELECT v.version_id, s.publisher, s.unit, o.series, COUNT(*) AS observations,
 MIN(o.observation_date) AS first_date, MAX(o.observation_date) AS last_date, v.collected_at
FROM versions v JOIN sources s ON s.source_id=v.source_id
JOIN observations o ON o.version_id=v.version_id
WHERE v.status='verified'
GROUP BY v.version_id,s.publisher,s.unit,o.series,v.collected_at
ORDER BY v.version_id,o.series
'''
RECONCILIATION_SQL = '''
SELECT v.version_id,v.status,v.declared_rows,COUNT(o.observation_date) AS loaded_rows,
 CASE WHEN v.status='verified' THEN COUNT(o.observation_date)=v.declared_rows
 ELSE NULL END AS row_count_matches,v.rejection_reason
FROM versions v LEFT JOIN observations o ON o.version_id=v.version_id
GROUP BY v.version_id,v.status,v.declared_rows,v.rejection_reason
ORDER BY v.version_id
'''

def _database(entries):
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        db.executescript(SCHEMA)
        with db:
            for entry in entries:
                if entry['status']=='rejected':
                    db.execute('INSERT INTO versions(version_id,status,rejection_reason) VALUES (?,?,?)',
                               (entry['version'],'rejected',entry['error']))
                    continue
                if entry['status']!='verified' or not entry.get('verified') or not entry.get('available'):
                    raise ValueError('Snapshot must be verified and currently available')
                m,s=entry['manifest'],entry['source']
                db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?)',(m['source'],s['publisher'],s['unit']))
                stored=db.execute('SELECT publisher,unit FROM sources WHERE source_id=?',(m['source'],)).fetchone()
                if tuple(stored)!=(s['publisher'],s['unit']):
                    raise ValueError('Conflicting source metadata')
                db.execute('INSERT INTO versions VALUES (?,?,?,?,?,?)',
                           (entry['version'],m['source'],'verified',m['rows'],m['collected_at'],None))
                db.executemany('INSERT INTO observations VALUES (?,?,?,?)',
                               [(entry['version'],r['date'],r['series'],r['value']) for r in entry['rows']])
                count=db.execute('SELECT COUNT(*) FROM observations WHERE version_id=?',(entry['version'],)).fetchone()[0]
                if count!=m['rows']:
                    raise ValueError('Manifest row count mismatch')
        db.execute('PRAGMA query_only=ON')
        return db
    except Exception:
        db.close()
        raise

def reports():
    """No caller-supplied trust flag: always invoke the unchanged file verifier."""
    db=_database(catalog())
    try:
        return {'coverage':[dict(r) for r in db.execute(COVERAGE_SQL)],
                'reconciliation':[dict(r) for r in db.execute(RECONCILIATION_SQL)],
                'persistent_database':False,'evaluation_enabled':False}
    finally:
        db.close()
