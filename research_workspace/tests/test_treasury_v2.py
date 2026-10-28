from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research_workspace import real_sources as old, treasury_v2 as v2

def xml(fields=None,day='2025-02-18'):
    fields=fields if fields is not None else ''.join('<d:'+s+'>4.2</d:'+s+'>' for s in v2.TENORS)
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="'+v2.M+'" xmlns:d="'+v2.D+'"><entry><content><m:properties><d:NEW_DATE>'+day+'T00:00:00</d:NEW_DATE>'+fields+'</m:properties></content></entry></feed>').encode()

class RevisionTests(unittest.TestCase):
    def test_exact_legacy_defect(self):
        raw=xml();self.assertEqual(len(old.parse('treasury_2025',raw)),13)
        rows,missing=v2.parse(raw);self.assertEqual(len(rows),14);self.assertEqual(missing,[])
        self.assertEqual({r['series'] for r in rows},set(v2.TENORS))
    def test_display_not_tenor(self):
        rows,_=v2.parse(xml('<d:BC_10YEAR>4</d:BC_10YEAR><d:BC_30YEARDISPLAY>5</d:BC_30YEARDISPLAY>'))
        self.assertEqual(len(rows),1)
    def test_activation(self):
        with self.assertRaisesRegex(ValueError,'activation'):v2.parse(xml(day='2025-02-17'))
    def test_null_vs_absent(self):
        rows,missing=v2.parse(xml('<d:BC_10YEAR>4</d:BC_10YEAR><d:BC_2YEAR m:null="true"/>'))
        by={x['series']:x['reason'] for x in missing}
        self.assertEqual(by['BC_2YEAR'],'publisher_null');self.assertEqual(by['BC_3MONTH'],'publisher_field_absent')
    def test_duplicate(self):
        with self.assertRaises(ValueError):v2.parse(xml('<d:BC_10YEAR>4</d:BC_10YEAR>'*2))
    def test_bad_numbers(self):
        for value in ['NaN','Infinity','-1','bad']:
            with self.assertRaises(ValueError):v2.parse(xml('<d:BC_10YEAR>'+value+'</d:BC_10YEAR>'))
    def test_bad_date(self):
        for day in ['2025-02-30','2026-02-18']:
            with self.assertRaises(ValueError):v2.parse(xml(day=day))
    def test_unknown_tenor(self):
        with self.assertRaises(ValueError):v2.parse(xml('<d:BC_99YEAR>4</d:BC_99YEAR>'))
    def test_immutable_lineage_and_asof(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            with patch.object(old,'download',return_value=(xml(),{'status':200})):
                parent=old.publish('treasury_2025',base/'legacy')
            folder=base/'legacy'/parent['version'];before={p.name:p.read_bytes() for p in folder.iterdir()}
            with patch.object(old,'download',side_effect=AssertionError('No network')):
                child=v2.derive(folder,parent['manifest_sha256'],base/'v2')
            target=base/'v2'/child['version'];review=v2.review(target,child['manifest_sha256'])
            self.assertEqual(len(review['rows']),14)
            self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
            self.assertEqual(len(old.review(folder,parent['manifest_sha256'])['rows']),13)
            hidden=v2.review(target,child['manifest_sha256'],as_of=review['manifest']['collected_at'])
            self.assertFalse(hidden['available']);self.assertEqual(hidden['rows'],[])
            (target/'observations.csv').write_bytes(b'changed')
            with self.assertRaises(ValueError):v2.review(target,child['manifest_sha256'])
    def test_unit_and_code_pin(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            with patch.object(old,'download',return_value=(xml(),{'status':200})):
                p=old.publish('treasury_2025',base/'old')
            c=v2.derive(base/'old'/p['version'],p['manifest_sha256'],base/'new');target=base/'new'/c['version']
            with patch.object(v2,'code_hashes',return_value={}):
                with self.assertRaisesRegex(ValueError,'Collector changed'):v2.review(target,c['manifest_sha256'])
            import json
            m=json.loads((target/'manifest.json').read_text());m['unit']='price'
            raw=old.encoded(m);(target/'manifest.json').write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Unit'):v2.review(target,old.sha(raw))
