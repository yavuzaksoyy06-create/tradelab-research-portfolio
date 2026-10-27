"""Local producer approval, sealed dataset publication and read-only review.

No network, credentials, broker, evaluator, clock override or permission changes.
SHA256 pins establish local custody, not a vendor's cryptographic signature.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .adapter import BASE, SYMBOLS, PROTOCOL_HASH, digest, integrity, read_json
from .intake import validate_manifest

POLICY = {"provider":"Alpaca historical", "feed":"sip", "adjustment":"split",
          "timeframe":"15min", "calendar":"XNYS"}
FILES = {"manifest.json", "receipt.json", "MSFT.csv", "SPY.csv", "QQQ.csv"}

def utcnow():
    return datetime.now(timezone.utc)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid SHA256 pin")
    return value

def identifier(value):
    require(isinstance(value,str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}",value),
            "Safe ASCII identifier required")
    require(value.upper() not in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),
                                  *(f"LPT{i}" for i in range(1,10))}, "Reserved Windows name")
    return value

def regular(path):
    path=Path(path).absolute()
    require(not any(p.is_symlink() or p.is_junction() for p in [path,*path.parents]),
            "Links and junctions are not accepted")
    require(path.is_file() and path.stat().st_nlink == 1, "Regular unlinked file required")
    return path

def timestamp(value):
    require(isinstance(value,str), "Timestamp required")
    result=datetime.fromisoformat(value.replace("Z","+00:00"))
    require(result.tzinfo is not None, "Explicit timezone required")
    require(result <= utcnow(), "Future provenance timestamp")
    return result

def exact(obj, keys):
    require(isinstance(obj,dict) and set(obj)==set(keys), "Unexpected or missing metadata fields")

def label(value):
    require(isinstance(value,str) and 1 <= len(value) <= 160 and
            all(c.isprintable() for c in value), "Short non-secret provenance label required")

def approval(record):
    exact(record, {"producer_id","collector_sha256","approved_by","approved_at","evidence_ref","policy"})
    identifier(record["producer_id"])
    sha(record["collector_sha256"])
    label(record["approved_by"]); label(record["evidence_ref"])
    timestamp(record["approved_at"])
    require(record["policy"]==POLICY, "Producer policy mismatch")
    return record

def write_json(path, value):
    # Exclusive creation, including metadata: never silently replace a version.
    with Path(path).open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(value,handle,indent=2,sort_keys=True,ensure_ascii=False)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())

def register(record_path, destination):
    record=approval(read_json(regular(record_path)))
    write_json(destination, {"schema_version":1,"trust_kind":"local_operator_attestation",
                             "producer":record})
    return {"registry":str(destination),"registry_sha256":digest(destination),
            "vendor_authenticated":False}

def registry(path, pin):
    path=regular(path)
    require(digest(path)==sha(pin), "Registry pin mismatch")
    value=read_json(path)
    exact(value,{"schema_version","trust_kind","producer"})
    require(value["schema_version"]==1 and value["trust_kind"]=="local_operator_attestation",
            "Unsupported registry")
    return approval(value["producer"])

def receipt_check(receipt, producer, window):
    exact(receipt,{"schema_version","producer_id","collector_sha256","collected_at",
                   "request_ref","policy","start","end","datasets"})
    require(receipt["schema_version"]==1, "Unsupported receipt")
    require(receipt["producer_id"]==producer["producer_id"] and
            receipt["collector_sha256"]==producer["collector_sha256"], "Unapproved producer or collector")
    collected=timestamp(receipt["collected_at"])
    require(collected >= timestamp(producer["approved_at"]), "Collection predates producer approval")
    require(collected >= datetime.fromisoformat(window["complete_after"].replace("Z","+00:00")),
            "Collection predates frozen completion gate")
    label(receipt["request_ref"])
    require(receipt["policy"]==POLICY and receipt["start"]==window["start"] and
            receipt["end"]==window["end"], "Receipt policy/window mismatch")
    exact(receipt["datasets"],SYMBOLS)
    for symbol,item in receipt["datasets"].items():
        exact(item,{"file","sha256"})
        require(item["file"]==symbol+".csv", "Canonical CSV filename required")
        sha(item["sha256"])

def review(directory, registry_path, registry_pin, seal_pin):
    """No writes. Require independent pins, then invoke the unchanged clock/data gate."""
    directory=Path(directory).absolute()
    report={"verified":False,"ready":False,"evaluated":False,"read_only":True,
            "vendor_authenticated":False,"errors":[]}
    try:
        identifier(directory.name)
        producer=registry(registry_path,registry_pin)
        protocol,_=integrity()
        seal_path=regular(directory/"seal.json")
        require(digest(seal_path)==sha(seal_pin), "Seal pin mismatch")
        seal=read_json(seal_path)
        exact(seal,{"schema_version","dataset_version","registry_sha256","created_at","files","supersedes"})
        require(seal["schema_version"]==1 and seal["dataset_version"]==directory.name,
                "Seal version mismatch")
        require(seal["registry_sha256"]==registry_pin, "Seal registry mismatch")
        created=timestamp(seal["created_at"])
        exact(seal["files"],FILES)
        require({p.name for p in directory.iterdir()}==FILES|{"seal.json"}, "Unexpected or missing package files")
        for name,expected in seal["files"].items():
            require(digest(regular(directory/name))==sha(expected), "Package hash mismatch: "+name)
        receipt=read_json(directory/"receipt.json")
        receipt_check(receipt,producer,protocol["future_window"])
        require(created >= timestamp(receipt["collected_at"]), "Seal predates collection")
        manifest=read_json(directory/"manifest.json")
        require(manifest.get("provenance")=={"registry_sha256":registry_pin,
                "receipt_sha256":seal["files"]["receipt.json"],"trust_kind":"local_operator_attestation"},
                "Manifest provenance mismatch")
        for symbol,item in receipt["datasets"].items():
            require(manifest["datasets"][symbol]["sha256"]==item["sha256"]==seal["files"][item["file"]],
                    "Receipt/manifest hash mismatch")
        previous=seal["supersedes"]
        if previous is not None:
            exact(previous,{"dataset_version","seal_sha256"})
            identifier(previous["dataset_version"]);sha(previous["seal_sha256"])
            require(previous["dataset_version"]!=directory.name, "Self revision forbidden")
        report["verified"]=True
        report["intake"]=validate_manifest(directory/"manifest.json")
        report["ready"]=report["intake"]["ready"]
        report["errors"].extend(report["intake"]["errors"])
        report["supersedes"]=previous
    except (ValueError,TypeError,KeyError,OSError,AttributeError) as exc:
        report["errors"].append(str(exc))
    return report

def build(source, store, version, registry_path, registry_pin, previous=None, previous_pin=None):
    """Publish only a complete, currently eligible package; no clock override."""
    identifier(version)
    producer=registry(registry_path,registry_pin)
    protocol,_=integrity()
    require(utcnow() >= datetime.fromisoformat(protocol["future_window"]["complete_after"].replace("Z","+00:00")),
            "Future window incomplete; publication blocked by frozen time gate")
    source=Path(source).absolute(); store=Path(store).absolute()
    require(store.is_dir() and not any(p.is_symlink() or p.is_junction() for p in [store,*store.parents]),
            "Existing non-linked dataset store required")
    target=store/version
    require(not target.exists(), "Dataset version already exists; use a new version")
    require((previous is None)==(previous_pin is None), "Revision requires previous version AND seal pin")
    supersedes=None
    if previous is not None:
        identifier(previous)
        prior=review(store/previous,registry_path,registry_pin,previous_pin)
        require(prior["ready"], "Previous revision failed review: "+str(prior["errors"]))
        supersedes={"dataset_version":previous,"seal_sha256":previous_pin}
    receipt=read_json(regular(source/"receipt.json"))
    receipt_check(receipt,producer,protocol["future_window"])
    # Staging is private to this invocation; failed stages are never published.
    with tempfile.TemporaryDirectory(prefix=".staging-",dir=store) as temporary:
        stage=Path(temporary)/version; stage.mkdir()
        write_json(stage/"receipt.json",receipt)
        manifest={"dataset_version":version,"protocol_sha256":PROTOCOL_HASH,
                  "source_sha256":protocol["source_sha256"],
                  "dependencies":read_json(BASE/"DEPENDENCIES.json")["versions"],
                  "provenance":{"registry_sha256":registry_pin,"receipt_sha256":digest(stage/"receipt.json"),
                                "trust_kind":"local_operator_attestation"},"datasets":{}}
        for symbol,item in receipt["datasets"].items():
            original=regular(source/item["file"])
            require(digest(original)==item["sha256"], "Source CSV hash mismatch: "+symbol)
            with original.open("rb") as src, (stage/item["file"]).open("xb") as dst:
                shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
            require(digest(stage/item["file"])==item["sha256"], "CSV changed during copy")
            manifest["datasets"][symbol]={**item,**POLICY,"symbol":symbol,
                "start":receipt["start"],"end":receipt["end"]}
        write_json(stage/"manifest.json",manifest)
        seal={"schema_version":1,"dataset_version":version,"registry_sha256":registry_pin,
              "created_at":utcnow().isoformat(),"files":{name:digest(stage/name) for name in sorted(FILES)},
              "supersedes":supersedes}
        write_json(stage/"seal.json",seal)
        pin=digest(stage/"seal.json")
        checked=review(stage,registry_path,registry_pin,pin)
        require(checked["ready"], "Dataset validation failed: "+str(checked["errors"]))
        # On Windows rename refuses an existing destination, including concurrent builders.
        require(os.name=="nt", "Atomic no-replace publication is Windows-only")
        os.rename(stage,target)
    return {"published":True,"dataset_version":version,"directory":str(target),"seal_sha256":pin,
            "registry_sha256":registry_pin,"evaluated":False,"vendor_authenticated":False}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    reg=sub.add_parser("register",help="Explicit local approval record -> exclusive registry file")
    reg.add_argument("--record",type=Path,required=True);reg.add_argument("--output",type=Path,required=True)
    for action in ("build","review"):
        p=sub.add_parser(action)
        p.add_argument("--registry",type=Path,required=True);p.add_argument("--registry-sha256",required=True)
        if action=="build":
            p.add_argument("--source",type=Path,required=True);p.add_argument("--store",type=Path,required=True)
            p.add_argument("--version",required=True)
            p.add_argument("--previous");p.add_argument("--previous-seal-sha256")
        else:
            p.add_argument("--directory",type=Path,required=True);p.add_argument("--seal-sha256",required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=="register":result=register(args.record,args.output)
        elif args.action=="build":result=build(args.source,args.store,args.version,args.registry,
            args.registry_sha256,args.previous,args.previous_seal_sha256)
        else:result=review(args.directory,args.registry,args.registry_sha256,args.seal_sha256)
    except (ValueError,TypeError,KeyError,OSError,AttributeError) as exc:
        result={"errors":[str(exc)],"ready":False,"evaluated":False}
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 2 if result.get("errors") or result.get("ready") is False else 0

if __name__=="__main__":
    raise SystemExit(main())
