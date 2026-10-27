"""Ephemeral SQL reports from freshly verified snapshots, without persistent writes."""
import sqlite3
from research_workspace.real_sources import catalog
from research_workspace.publication_calendar import publication_reports

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

# Observed-date grid is diagnostic, not a publisher calendar or expected universe.
QUALITY_SQL = """
WITH grid AS (SELECT version_id, COUNT(DISTINCT observation_date) AS observed_dates
 FROM observations GROUP BY version_id)
SELECT o.version_id,o.series,COUNT(*) AS observations,
 MIN(o.value) AS minimum_value,MAX(o.value) AS maximum_value,
 SUM(CASE WHEN o.value=0 THEN 1 ELSE 0 END) AS zero_values,
 SUM(CASE WHEN o.value<0 THEN 1 ELSE 0 END) AS negative_values,
 g.observed_dates,g.observed_dates-COUNT(*) AS absent_on_observed_dates,
 'observed_date_grid_only' AS assessment_basis
FROM observations o JOIN grid g ON g.version_id=o.version_id
GROUP BY o.version_id,o.series,g.observed_dates ORDER BY o.version_id,o.series
"""
MISSING_CTE = """
WITH days AS (SELECT DISTINCT version_id,observation_date FROM observations),
series AS (SELECT DISTINCT version_id,series FROM observations),
missing AS (SELECT s.version_id,s.series,d.observation_date
 FROM series s JOIN days d ON d.version_id=s.version_id
 LEFT JOIN observations o ON o.version_id=s.version_id AND o.series=s.series
 AND o.observation_date=d.observation_date WHERE o.version_id IS NULL)
"""
GAPS_CTE = """
WITH ordered AS (SELECT version_id,series,observation_date,
 LAG(observation_date) OVER (PARTITION BY version_id,series ORDER BY observation_date) AS previous_date
 FROM observations), gaps AS (
 SELECT version_id,series,previous_date,observation_date,
 CAST(julianday(observation_date)-julianday(previous_date) AS INTEGER)-1 AS intervening_calendar_days
 FROM ordered WHERE julianday(observation_date)-julianday(previous_date)>1)
"""
DETAIL_LIMIT = 500

def _diagnostics(db):
    quality=[dict(r) for r in db.execute(QUALITY_SQL)]
    missing_count=sum(r['absent_on_observed_dates'] for r in quality)
    gap_count=db.execute(GAPS_CTE+'SELECT COUNT(*) FROM gaps').fetchone()[0]
    return {'quality':quality,
            'missing_observations':[dict(r) for r in db.execute(MISSING_CTE+
                'SELECT * FROM missing ORDER BY version_id,series,observation_date LIMIT ?', (DETAIL_LIMIT,))],
            'missing_observations_total':missing_count,
            'missing_observations_truncated':missing_count>DETAIL_LIMIT,
            'calendar_gaps':[dict(r) for r in db.execute(GAPS_CTE+
                'SELECT * FROM gaps ORDER BY version_id,series,observation_date LIMIT ?', (DETAIL_LIMIT,))],
            'calendar_gaps_total':gap_count,'calendar_gaps_truncated':gap_count>DETAIL_LIMIT,
            'calendar_completeness':'unknown','detail_limit':DETAIL_LIMIT}


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
                'persistent_database':False,'evaluation_enabled':False, **_diagnostics(db), **publication_reports(db)}
    finally:
        db.close()
