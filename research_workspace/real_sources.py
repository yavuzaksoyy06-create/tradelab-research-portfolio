"""Public daily reference snapshots. No broker, evaluator or point-in-time claim."""
from datetime import date, datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import ssl
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import certifi

from research_terminal.provenance import regular, identifier, write_json, require

ROOT = Path(__file__).resolve().parent
STORE = ROOT / 'real_data'
LIMIT = 4_000_000
SOURCES = {
    'ecb_fx': {
        'publisher': 'European Central Bank',
        'url': 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml',
        'documentation': 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html',
        'terms': 'https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html',
        'unit': 'quote currency per EUR', 'frequency': 'daily reference, last 90 days',
        'usage': 'Informational reference only; cite ECB. Not executable FX quotes.',
    },
    'treasury_2025': {
        'publisher': 'U.S. Department of the Treasury',
        'url': 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2025',
        'documentation': 'https://home.treasury.gov/treasury-daily-interest-rate-xml-feed',
        'terms': 'https://home.treasury.gov/footer/privacy-act',
        'unit': 'percent annualized par yield', 'frequency': 'daily, calendar year 2025',
        'usage': 'Public official XML feed; local descriptive research with attribution. No redistribution clearance asserted.',
    },
}
REGISTRY = {'schema': 1, 'sources': SOURCES, 'trust': 'local reviewed official HTTPS allowlist; not a publisher signature',
            'reviewed_on': '2026-10-26', 'scope': 'descriptive daily snapshots only; no V4.1 intake or evaluation',
            'availability': 'first local collection time; original publication and revision vintages unknown'}

def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def now():
    return datetime.now(timezone.utc)

def aware(value):
    dt = datetime.fromisoformat(value)
    require(dt.tzinfo is not None, 'Timezone required')
    return dt.astimezone(timezone.utc)

def checked_bytes(path):
    p = regular(path)
    require(p.stat().st_size <= LIMIT, 'File too large')
    return p.read_bytes()

def parse(source, raw):
    require(source in SOURCES, 'Unknown source')
    require(0 < len(raw) <= LIMIT, 'Empty or oversized XML')
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(), 'XML declarations forbidden')
    root = ET.fromstring(raw)
    rows = []
    if source == 'ecb_fx':
        require(root.tag == '{http://www.gesmes.org/xml/2002-08-01}Envelope', 'Unexpected ECB schema')
        for cube in root.iter('{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube'):
            if 'time' not in cube.attrib:
                continue
            day = date.fromisoformat(cube.attrib['time']).isoformat()
            for item in cube:
                currency = item.attrib['currency']
                require(re.fullmatch('[A-Z]{3}', currency) is not None, 'Invalid currency')
                rows.append({'date': day, 'series': 'EUR/' + currency, 'value': float(item.attrib['rate'])})
    else:
        require(root.tag == '{http://www.w3.org/2005/Atom}feed', 'Unexpected Treasury schema')
        ns = {'m': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata',
              'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices'}
        for prop in root.findall('.//m:properties', ns):
            day = date.fromisoformat(prop.find('d:NEW_DATE', ns).text[:10]).isoformat()
            require(day.startswith('2025-'), 'Unexpected Treasury year')
            for item in prop:
                field = item.tag.split('}')[-1]
                if not re.fullmatch(r'BC_\d+(MONTH|YEAR)', field):
                    continue
                if item.attrib.get('{' + ns['m'] + '}null') == 'true':
                    continue  # missing is not zero
                rows.append({'date': day, 'series': field, 'value': float(item.text)})
    require(rows, 'No observations')
    keys = [(r['date'], r['series']) for r in rows]
    require(len(keys) == len(set(keys)), 'Duplicate observation')
    for row in rows:
        require(math.isfinite(row['value']), 'Nonfinite value')
        require(row['value'] > 0 if source == 'ecb_fx' else row['value'] >= 0, 'Invalid rate')
    return sorted(rows, key=lambda r: (r['date'], r['series']))

def normalized(rows, collected):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=['date', 'series', 'value', 'available_at'], lineterminator='\n')
    writer.writeheader()
    writer.writerows({**r, 'available_at': collected} for r in rows)
    return out.getvalue().encode('utf-8')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused; review source registry before changing endpoint')

def download(source):
    require(source in SOURCES, 'Unknown source')
    url = SOURCES[source]['url']
    req = urllib.request.Request(url, headers={'User-Agent': 'TradeLab-Research/0.3.1', 'Accept': 'application/xml,text/xml', 'Accept-Encoding': 'identity'})
    context = ssl.create_default_context(cafile=certifi.where())
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    with opener.open(req, timeout=30) as response:
        require(response.status == 200 and response.url == url, 'Unexpected HTTP response')
        require(response.headers.get_content_type() in ('application/xml', 'text/xml', 'application/atom+xml'), 'Expected XML content type')
        raw = response.read(LIMIT + 1)
        require(len(raw) <= LIMIT, 'Response too large')
        return raw, {'status': 200, 'content_type': response.headers.get_content_type(),
                     'etag': response.headers.get('ETag'), 'last_modified': response.headers.get('Last-Modified')}

def publish(source, store=STORE):
    """Network is confined to this explicit CLI operation; no replacement of versions."""
    require(source in SOURCES, 'Unknown source')
    store = Path(store).absolute()
    require(not any(p.is_symlink() or p.is_junction() for p in (store, *store.parents)), 'Linked store forbidden')
    store.mkdir(exist_ok=True)
    raw, http = download(source)
    collected = now().isoformat()
    rows = parse(source, raw)
    require(max(r['date'] for r in rows) <= aware(collected).date().isoformat(), 'Future-dated observation')
    version = source + '_' + now().strftime('%Y%m%dT%H%M%S%fZ')
    identifier(version)
    data = {'raw.xml': raw, 'observations.csv': normalized(rows, collected), 'registry.json': encoded(REGISTRY)}
    manifest = {'schema': 1, 'version': version, 'source': source, 'source_url': SOURCES[source]['url'],
                'collected_at': collected, 'available_at': collected, 'http': http,
                'rows': len(rows), 'first_date': rows[0]['date'], 'last_date': rows[-1]['date'],
                'files': {n: sha(b) for n, b in data.items()}, 'collector_sha256': sha(Path(__file__).read_bytes()),
                'point_in_time_history': False, 'evaluation_enabled': False, 'vendor_signature_verified': False}
    with tempfile.TemporaryDirectory(prefix='.stage-', dir=store) as temporary:
        stage = Path(temporary) / version
        stage.mkdir()
        for name, content in data.items():
            with (stage / name).open('xb') as f:
                f.write(content); f.flush(); os.fsync(f.fileno())
        write_json(stage / 'manifest.json', manifest)
        pin = sha((stage / 'manifest.json').read_bytes())
        review(stage, pin)
        require(os.name == 'nt', 'No-replace publication requires Windows')
        os.rename(stage, store / version)
    # A crash before this receipt leaves an unlisted version, never a false verified view.
    write_json(store / (version + '.pin.json'), {'version': version, 'manifest_sha256': pin})
    return {'version': version, 'manifest_sha256': pin, 'rows': len(rows), 'first_date': rows[0]['date'], 'last_date': rows[-1]['date']}

def review(directory, manifest_pin, as_of=None):
    """Read and rederive from the exact hash-checked raw bytes; no network or writes."""
    directory = Path(directory)
    identifier(directory.name)
    raw_manifest = checked_bytes(directory / 'manifest.json')
    require(sha(raw_manifest) == manifest_pin, 'Manifest pin mismatch')
    m = json.loads(raw_manifest)
    require(m['schema'] == 1 and m['version'] == directory.name, 'Version/schema mismatch')
    source = m['source']
    require(source in SOURCES and m['source_url'] == SOURCES[source]['url'], 'Source mismatch')
    require(m['evaluation_enabled'] is False and m['point_in_time_history'] is False and m['vendor_signature_verified'] is False, 'Scope mismatch')
    require(set(m['files']) == {'raw.xml', 'observations.csv', 'registry.json'}, 'File set mismatch')
    require({p.name for p in directory.iterdir()} == set(m['files']) | {'manifest.json'}, 'Unexpected package file')
    files = {n: checked_bytes(directory / n) for n in m['files']}
    require(all(sha(b) == m['files'][n] for n, b in files.items()), 'File hash mismatch')
    require(files['registry.json'] == encoded(REGISTRY), 'Unreviewed registry')
    require(m['collector_sha256'] == sha(Path(__file__).read_bytes()), 'Collector changed; explicit migration review required')
    collected = aware(m['collected_at'])
    require(collected <= now() and m['available_at'] == m['collected_at'], 'Invalid collection time')
    rows = parse(source, files['raw.xml'])
    require(m['rows'] == len(rows) and m['first_date'] == rows[0]['date'] and m['last_date'] == rows[-1]['date'], 'Coverage mismatch')
    require(rows[-1]['date'] <= collected.date().isoformat(), 'Future-dated observation')
    require(files['observations.csv'] == normalized(rows, m['collected_at']), 'Normalized data differs from raw source')
    cutoff = now() if as_of is None else aware(as_of)
    require(cutoff <= now(), 'Future as-of forbidden')
    return {'manifest': m, 'source': SOURCES[source], 'rows': rows if cutoff >= collected else [],
            'verified': True, 'available': cutoff >= collected, 'evaluation_enabled': False}

def catalog(store=STORE):
    store = Path(store)
    result = []
    if not store.exists():
        return result
    for p in sorted(store.glob('*.pin.json')):
        try:
            receipt = json.loads(checked_bytes(p))
            version = identifier(receipt['version'])
            require(p.name == version + '.pin.json', 'Receipt/version mismatch')
            checked = review(store / version, receipt['manifest_sha256'])
            result.append({'version': version, 'pin': receipt['manifest_sha256'], 'status': 'verified', **checked})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as exc:
            result.append({'version': p.name, 'status': 'rejected', 'error': str(exc), 'rows': []})
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['collect', 'review'])
    parser.add_argument('--source', choices=list(SOURCES))
    args = parser.parse_args()
    if args.action == 'collect':
        require(args.source is not None, '--source required')
        result = publish(args.source)
    else:
        result = [{k: v for k, v in item.items() if k != 'rows'} for item in catalog()]
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
