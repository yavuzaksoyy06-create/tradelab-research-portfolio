"""Synthetic custody tests. Clock mocks never enter production CLI or research."""
import contextlib
from datetime import datetime,timezone
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research_terminal import provenance as p
from research_terminal.adapter import ROOT,digest
from research_sr_v4.data import expected_grid

FUTURE=datetime(2027,1,22,tzinfo=timezone.utc)
class FutureClock:
    @staticmethod
    def now(tz=None):return FUTURE

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"temp");self.root=Path(self.temp.name)
        self.source=self.root/"source";self.source.mkdir()
        self.store=self.root/"versions";self.store.mkdir()
        self.reg=self.root/"registry.json";self.record=self.root/"approval.json"
        self.save(self.record,{"producer_id":"synthetic_test","collector_sha256":"a"*64,
            "approved_by":"test-only","approved_at":"2026-01-01T00:00:00Z",
            "evidence_ref":"SYNTHETIC_NOT_VENDOR_EVIDENCE","policy":p.POLICY.copy()})
        self.pin=p.register(self.record,self.reg)["registry_sha256"]
        self.receipt={"schema_version":1,"producer_id":"synthetic_test","collector_sha256":"a"*64,
            "collected_at":"2027-01-21T22:00:00Z","request_ref":"synthetic-no-real-request",
            "policy":p.POLICY.copy(),"start":"2026-10-26","end":"2027-01-21","datasets":{}}
        frame=expected_grid("2026-10-26","2027-01-21")[["timestamp"]].copy()
        for k,v in {"open":100.,"high":101.,"low":99.,"close":100.5,"volume":1000}.items():frame[k]=v
        for s in p.SYMBOLS:
            path=self.source/(s+".csv");frame.to_csv(path,index=False)
            self.receipt["datasets"][s]={"file":path.name,"sha256":digest(path)}
        self.save_receipt()
        self.clock=patch.object(p,"utcnow",return_value=FUTURE);self.clock.start()
        self.gate=patch("research_terminal.intake.datetime",FutureClock);self.gate.start()
    def tearDown(self):self.gate.stop();self.clock.stop();self.temp.cleanup()
    def save(self,path,obj):path.write_text(json.dumps(obj),encoding="utf-8")
    def save_receipt(self):self.save(self.source/"receipt.json",self.receipt)
    def build(self,version="dataset_v1",**kw):return p.build(self.source,self.store,version,self.reg,self.pin,**kw)
    def review(self,r):return p.review(r["directory"],self.reg,self.pin,r["seal_sha256"])
    def hashes(self,path):return {x.name:digest(x) for x in path.iterdir() if x.is_file()}
    def test_build_review_readonly_no_evaluation(self):
        original=self.hashes(self.source);r=self.build();before=self.hashes(Path(r["directory"]))
        report=self.review(r);self.assertTrue(report["ready"],report)
        self.assertFalse(report["evaluated"]);self.assertFalse(report["vendor_authenticated"])
        self.assertEqual(report["intake"]["datasets"]["SPY"]["sessions"],60)
        self.assertEqual(before,self.hashes(Path(r["directory"])));self.assertEqual(original,self.hashes(self.source))
    def test_duplicate_version_never_overwrites(self):
        r=self.build();before=self.hashes(Path(r["directory"]))
        with self.assertRaisesRegex(ValueError,"already exists"):self.build()
        self.assertEqual(before,self.hashes(Path(r["directory"])))
    def test_revision_chain_preserves_original(self):
        first=self.build();before=self.hashes(Path(first["directory"]))
        second=self.build("dataset_v2",previous="dataset_v1",previous_pin=first["seal_sha256"])
        report=self.review(second);self.assertTrue(report["ready"],report)
        self.assertEqual(report["supersedes"]["seal_sha256"],first["seal_sha256"])
        self.assertEqual(before,self.hashes(Path(first["directory"])))
    def test_bad_revision_pin(self):
        self.build()
        with self.assertRaisesRegex(ValueError,"Previous revision failed"):
            self.build("dataset_v2",previous="dataset_v1",previous_pin="0"*64)
    def test_incomplete_revision_arguments(self):
        with self.assertRaisesRegex(ValueError,"requires previous"):self.build(previous="dataset_v0")
    def test_registry_no_overwrite(self):
        before=digest(self.reg)
        with self.assertRaises(FileExistsError):p.register(self.record,self.reg)
        self.assertEqual(before,digest(self.reg))
    def test_registry_tampering(self):
        self.reg.write_text("{}")
        with self.assertRaisesRegex(ValueError,"Registry pin mismatch"):self.build()
    def test_unapproved_collector(self):
        self.receipt["collector_sha256"]="b"*64;self.save_receipt()
        with self.assertRaisesRegex(ValueError,"Unapproved"):self.build()
    def test_wrong_feed(self):
        self.receipt["policy"]["feed"]="iex";self.save_receipt()
        with self.assertRaisesRegex(ValueError,"policy/window mismatch"):self.build()
    def test_receipt_time_validation(self):
        for value in ("2028-01-01T00:00:00Z","2026-10-23T00:00:00Z","2027-01-21T22:00:00"):
            self.receipt["collected_at"]=value;self.save_receipt()
            with self.subTest(value=value),self.assertRaises(ValueError):self.build()
    def test_frozen_early_gate_blocks_before_writes(self):
        with patch.object(p,"utcnow",return_value=datetime(2026,10,24,tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ValueError,"time gate"):self.build()
        self.assertEqual(list(self.store.iterdir()),[])
    def test_unknown_sensitive_field(self):
        self.receipt["api_key"]="dummy";self.save_receipt()
        with self.assertRaisesRegex(ValueError,"Unexpected"):self.build()
    def test_path_escape(self):
        self.receipt["datasets"]["SPY"]["file"]="../SPY.csv";self.save_receipt()
        with self.assertRaisesRegex(ValueError,"Canonical"):self.build()
    def test_unsafe_version_names(self):
        for version in ("..","../x","CON","NUL","a.b",".staging-x"):
            with self.subTest(version=version),self.assertRaises(ValueError):self.build(version)
    def test_source_hash_and_cleanup(self):
        (self.source/"SPY.csv").write_text("corrupt")
        with self.assertRaisesRegex(ValueError,"Source CSV hash"):self.build()
        self.assertEqual(list(self.store.iterdir()),[])
    def test_incomplete_data_with_matching_hash(self):
        path=self.source/"SPY.csv";path.write_text("\n".join(path.read_text().splitlines()[:-1])+"\n")
        self.receipt["datasets"]["SPY"]["sha256"]=digest(path);self.save_receipt()
        with self.assertRaisesRegex(ValueError,"Missing"):self.build()
        self.assertEqual(list(self.store.iterdir()),[])
    def test_package_tampering(self):
        result=self.build();(Path(result["directory"])/"SPY.csv").write_text("corrupt")
        self.assertFalse(self.review(result)["verified"])
    def test_recomputed_seal_cannot_bypass_external_pin(self):
        r=self.build();path=Path(r["directory"]);(path/"SPY.csv").write_text("corrupt")
        seal=json.loads((path/"seal.json").read_text());seal["files"]["SPY.csv"]=digest(path/"SPY.csv")
        self.save(path/"seal.json",seal)
        self.assertIn("Seal pin mismatch",self.review(r)["errors"])
    def test_missing_or_extra_file_rejected(self):
        r=self.build();path=Path(r["directory"]);(path/"extra.csv").write_text("x")
        self.assertFalse(self.review(r)["verified"])
        (path/"extra.csv").unlink();(path/"QQQ.csv").unlink()
        self.assertFalse(self.review(r)["verified"])
    def test_version_rename_rejected(self):
        r=self.build();path=Path(r["directory"]);new=path.with_name("renamed");path.rename(new)
        r["directory"]=str(new);self.assertFalse(self.review(r)["verified"])
    def test_failed_publication_cleanup_and_retry(self):
        with patch.object(p.os,"rename",side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):self.build()
        self.assertEqual(list(self.store.iterdir()),[])
        self.assertTrue(self.review(self.build())["ready"])
    def test_concurrent_builder_cannot_overwrite(self):
        original=p.os.rename
        def race(src,dst):
            Path(dst).mkdir();(Path(dst)/"owner.txt").write_text("other builder");original(src,dst)
        with patch.object(p.os,"rename",side_effect=race),self.assertRaises(OSError):self.build()
        self.assertEqual((self.store/"dataset_v1/owner.txt").read_text(),"other builder")
        self.assertEqual(len(list(self.store.iterdir())),1)
    def test_abandoned_stage_not_accepted(self):
        path=self.store/".staging-abandoned";path.mkdir()
        self.assertFalse(p.review(path,self.reg,self.pin,"0"*64)["verified"])
    def test_cli_no_clock_override(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            p.main(["review","--directory",str(self.store),"--registry",str(self.reg),
                    "--registry-sha256",self.pin,"--seal-sha256","0"*64,"--now","2027-01-22"])
    def test_cli_review(self):
        r=self.build()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status=p.main(["review","--directory",r["directory"],"--registry",str(self.reg),
                           "--registry-sha256",self.pin,"--seal-sha256",r["seal_sha256"]])
        self.assertEqual(status,0);self.assertFalse(json.loads(output.getvalue())["evaluated"])
