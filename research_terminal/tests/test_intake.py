"""Synthetic future fixtures are software tests, never research observations."""
import json,tempfile,unittest
from pathlib import Path
from research_terminal.adapter import ROOT,BASE,PROTOCOL_HASH,read_json,digest
from research_terminal.intake import validate_manifest
from research_sr_v4.data import expected_grid

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"temp")
        self.path=Path(self.temp.name)/"synthetic_test_v1"
        self.path.mkdir()
        protocol=read_json(BASE/"PORTFOLIO_EXPERIMENT_CONFIG.json")
        self.manifest={"dataset_version":self.path.name,"protocol_sha256":PROTOCOL_HASH,
            "source_sha256":protocol["source_sha256"],"dependencies":read_json(BASE/"DEPENDENCIES.json")["versions"],
            "datasets":{}}
        grid=expected_grid("2026-10-26","2027-01-21")
        for s in ("MSFT","SPY","QQQ"):
            f=grid[["timestamp"]].copy()
            for k,v in {"open":100.0,"high":101.0,"low":99.0,"close":100.5,"volume":1000}.items():f[k]=v
            f.to_csv(self.path/f"{s}.csv",index=False)
            self.manifest["datasets"][s]={"file":f"{s}.csv","sha256":digest(self.path/f"{s}.csv"),
                "symbol":s,"provider":"Alpaca historical","feed":"sip","adjustment":"split",
                "timeframe":"15min","calendar":"XNYS","start":"2026-10-26","end":"2027-01-21"}
        self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):
        (self.path/"manifest.json").write_text(json.dumps(self.manifest))
    def check(self,now="2027-01-22T00:00Z"):
        return validate_manifest(self.path/"manifest.json",now)
    def mutate_csv(self,fn):
        import pandas as pd
        p=self.path/"MSFT.csv"
        f=fn(pd.read_csv(p));f.to_csv(p,index=False)
        self.manifest["datasets"]["MSFT"]["sha256"]=digest(p);self.save()
    def test_complete_synthetic_manifest_validates_without_evaluation(self):
        r=self.check()
        self.assertTrue(r["ready"],r["errors"])
        self.assertFalse(r["evaluated"])
        self.assertEqual(r["datasets"]["SPY"]["sessions"],60)
    def test_early_clock_rejects_complete_future_fixture(self):
        r=self.check("2026-10-23T22:00Z")
        self.assertFalse(r["ready"])
        self.assertFalse(r["data_valid"])
    def test_iex_rejected(self):
        self.manifest["datasets"]["MSFT"]["feed"]="iex";self.save()
        self.assertIn("metadata mismatch"," ".join(self.check()["errors"]))
    def test_hash_mismatch_rejected(self):
        self.manifest["datasets"]["MSFT"]["sha256"]="bad";self.save()
        self.assertIn("SHA256 mismatch"," ".join(self.check()["errors"]))
    def test_source_mismatch_rejected(self):
        self.manifest["source_sha256"]={};self.save()
        self.assertIn("source hashes mismatch"," ".join(self.check()["errors"]))
    def test_missing_bar(self):
        self.mutate_csv(lambda f:f.iloc[1:])
        self.assertIn("Missing"," ".join(self.check()["errors"]))
    def test_duplicate_bar(self):
        import pandas as pd
        self.mutate_csv(lambda f:pd.concat([f.iloc[:1],f],ignore_index=True))
        self.assertIn("duplicate"," ".join(self.check()["errors"]))
    def test_unsorted(self):
        self.mutate_csv(lambda f:f.iloc[::-1])
        self.assertIn("not ordered"," ".join(self.check()["errors"]))
    def test_invalid_ohlc(self):
        def change(f): f.loc[0,"high"]=1;return f
        self.mutate_csv(change)
        self.assertIn("OHLC"," ".join(self.check()["errors"]))
    def test_escape_path(self):
        self.manifest["datasets"]["MSFT"]["file"]="../MSFT.csv";self.save()
        self.assertIn("inside"," ".join(self.check()["errors"]))
    def test_no_overwrite(self):
        before={p.name:digest(p) for p in self.path.iterdir()}
        self.check()
        self.assertEqual(before,{p.name:digest(p) for p in self.path.iterdir()})

