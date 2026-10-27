import json
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from research_workspace import real_sources as r

ECB = b'''<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref"><Cube><Cube time="2025-01-02"><Cube currency="USD" rate="1.1"/><Cube currency="JPY" rate="160"/></Cube></Cube></gesmes:Envelope>'''
UST = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"><entry><content><m:properties><d:NEW_DATE>2025-01-02T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.3</d:BC_10YEAR><d:BC_2YEAR m:null="true"/></m:properties></content></entry></feed>'''

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name)

    def publish(self):
        with patch.object(r, 'download', return_value=(ECB, {'status': 200})):
            result = r.publish('ecb_fx', self.store)
        return self.store / result['version'], result['manifest_sha256']

    def rewrite(self, folder, change):
        m = json.loads((folder/'manifest.json').read_text())
        change(m)
        data = r.encoded(m)
        (folder/'manifest.json').write_bytes(data)
        return r.sha(data)

    def test_ecb_units_and_values(self):
        rows = r.parse('ecb_fx', ECB)
        self.assertEqual(rows[1], {'date':'2025-01-02','series':'EUR/USD','value':1.1})

    def test_treasury_null_not_zero(self):
        self.assertEqual(r.parse('treasury_2025', UST), [{'date':'2025-01-02','series':'BC_10YEAR','value':4.3}])

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            r.parse('ecb_fx', ECB.replace(b'<Cube currency="JPY" rate="160"/>', b'<Cube currency="USD" rate="1.1"/>'))

    def test_nonfinite_rejected(self):
        for val in (b'NaN', b'Infinity', b'-1', b'0'):
            with self.assertRaises(ValueError):
                r.parse('ecb_fx', ECB.replace(b'1.1', val))

    def test_entities_and_size_rejected(self):
        for raw in (b'<!DOCTYPE x>' + ECB, b'x' * (r.LIMIT+1), b''):
            with self.assertRaises(ValueError):r.parse('ecb_fx', raw)

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):r.parse('ecb_fx', b'<html/>')

    def test_unknown_source_has_no_network(self):
        with patch.object(r.urllib.request, 'build_opener') as network:
            with self.assertRaises(ValueError):r.download('https://localhost/secret')
            network.assert_not_called()

    def test_redirect_refused(self):
        with self.assertRaises(ValueError):r.NoRedirect().redirect_request(None,None,302,None,None,'http://localhost/')

    def test_publish_readonly_review_and_asof(self):
        folder, pin = self.publish()
        before = {p.name:p.read_bytes() for p in folder.iterdir()}
        checked = r.review(folder,pin)
        self.assertTrue(checked['verified']);self.assertFalse(checked['evaluation_enabled'])
        cutoff = (r.aware(checked['manifest']['collected_at'])-timedelta(seconds=1)).isoformat()
        self.assertEqual(r.review(folder,pin,cutoff)['rows'], [])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})

    def test_future_asof_rejected(self):
        folder,pin=self.publish()
        with self.assertRaises(ValueError):r.review(folder,pin,(r.now()+timedelta(days=1)).isoformat())

    def test_raw_corruption_rejected(self):
        folder,pin=self.publish();(folder/'raw.xml').write_bytes(ECB+b' ')
        with self.assertRaisesRegex(ValueError,'hash'):r.review(folder,pin)
        self.assertEqual(r.catalog(self.store)[0]['status'],'rejected')

    def test_manifest_corruption_rejected(self):
        folder,pin=self.publish();(folder/'manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'pin'):r.review(folder,pin)

    def test_rehashed_normalization_still_rejected(self):
        folder,pin=self.publish();(folder/'observations.csv').write_bytes(b'fake')
        pin=self.rewrite(folder,lambda m:m['files'].update({'observations.csv':r.sha(b'fake')}))
        with self.assertRaisesRegex(ValueError,'Normalized'):r.review(folder,pin)

    def test_collector_hash_remains_mandatory(self):
        folder,pin=self.publish()
        pin=self.rewrite(folder,lambda m:m.update(collector_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'Collector changed'):r.review(folder,pin)

    def test_registry_rehashed_change_rejected(self):
        folder,pin=self.publish();(folder/'registry.json').write_bytes(b'{}')
        pin=self.rewrite(folder,lambda m:m['files'].update({'registry.json':r.sha(b'{}')}))
        with self.assertRaisesRegex(ValueError,'registry'):r.review(folder,pin)

    def test_extra_file_rejected(self):
        folder,pin=self.publish();(folder/'extra').write_text('extra')
        with self.assertRaises(ValueError):r.review(folder,pin)

    def test_path_traversal_receipt_rejected(self):
        (self.store/'bad.pin.json').write_text(json.dumps({'version':'../outside','manifest_sha256':'0'*64}))
        self.assertEqual(r.catalog(self.store)[0]['status'],'rejected')

    def test_failure_does_not_publish(self):
        with patch.object(r,'download',return_value=(b'bad',{})):
            with self.assertRaises(r.ET.ParseError):r.publish('ecb_fx',self.store)
        self.assertEqual(list(self.store.iterdir()),[])

    def test_repeated_collection_preserves_versions(self):
        folder,pin=self.publish();original=(folder/'manifest.json').read_bytes()
        second,_=self.publish()
        self.assertNotEqual(folder,second)
        self.assertEqual((folder/'manifest.json').read_bytes(),original)
        self.assertEqual(len(r.catalog(self.store)),2)

    def test_no_replace_on_collision(self):
        frozen=r.now()
        with patch.object(r,'now',return_value=frozen):
            folder,pin=self.publish()
            with self.assertRaises(OSError):self.publish()
        self.assertTrue(r.review(folder,pin)['verified'])

    def test_collection_failure_keeps_old_version(self):
        folder,pin=self.publish()
        with patch.object(r,'download',side_effect=OSError('offline')):
            with self.assertRaises(OSError):r.publish('ecb_fx',self.store)
        self.assertTrue(r.review(folder,pin)['verified'])

    def test_ui_empty_is_not_success(self):
        with patch('research_workspace.real_data_ui.catalog',return_value=[]):
            at=AppTest.from_file(str(r.ROOT/'app.py'),default_timeout=60).run()
            at.radio(key='page').set_value('Gerçek Veri').run()
            self.assertFalse(at.exception)
            self.assertTrue(any('sürümü yok' in w.value for w in at.warning))

    def test_ui_verified_and_rejected(self):
        self.publish();entries=r.catalog(self.store)
        entries.append({'version':'bad','status':'rejected','error':'hash mismatch','rows':[]})
        with patch('research_workspace.real_data_ui.catalog',return_value=entries):
            at=AppTest.from_file(str(r.ROOT/'app.py'),default_timeout=60).run()
            at.radio(key='page').set_value('Gerçek Veri').run()
            self.assertFalse(at.exception);self.assertEqual(at.metric[0].value,'2')
            self.assertTrue(at.error)
            self.assertTrue(any('Gözlem tarihi yayın zamanı değildir' in x.value for x in at.warning))

if __name__=='__main__':unittest.main()
