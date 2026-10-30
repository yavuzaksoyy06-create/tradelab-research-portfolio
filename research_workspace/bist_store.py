"""New-folder private BIST snapshots; bounded one-pass reading, no downloads."""
import json
from pathlib import Path

from research_workspace.bist_research import MAX_BYTES, PROTOCOL, load_csv
from research_workspace.stage7_preparation_ui import _local_directory

SCHEMA = "tradelab.bist.snapshot.v1"


def register(payload, manifest, directory):
    # Invalid or reserved data cannot create even a destination directory.
    _, meta = load_csv(payload, manifest)
    if not _local_directory(str(directory)):
        raise ValueError("BIST_LOCAL_PATH_REQUIRED")
    target = Path(directory).resolve()
    if any((parent / ".git").exists() for parent in (target, *target.parents)):
        raise ValueError("BIST_PRIVATE_DESTINATION_REQUIRED")
    stored = {**meta, "schema": SCHEMA, "bytes": len(payload)}
    target.mkdir(parents=True, exist_ok=False)
    # The manifest is written last. Partial writes never form a valid snapshot.
    with (target / "bars.csv").open("xb") as stream:
        stream.write(payload)
    with (target / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(stored, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return stored


def read_snapshot(directory):
    if not _local_directory(str(directory)):
        raise ValueError("BIST_LOCAL_PATH_REQUIRED")
    folder = Path(directory)
    content = {}
    for name, limit in (("manifest.json", 100_000), ("bars.csv", MAX_BYTES)):
        with (folder / name).open("rb") as stream:
            content[name] = stream.read(limit + 1)
        if len(content[name]) > limit:
            raise ValueError("BIST_INPUT_SIZE")
    stored = json.loads(content["manifest.json"].decode("utf-8"))
    payload = content["bars.csv"]
    if (not isinstance(stored, dict) or stored.get("schema") != SCHEMA or
            type(stored.get("bytes")) is not int or stored["bytes"] != len(payload) or
            stored.get("orders_enabled") is not False):
        raise ValueError("BIST_INVALID_MANIFEST")
    frame, meta = load_csv(payload, stored)
    if (stored.get("protocol") != PROTOCOL or stored.get("canonical_sha256") != meta["canonical_sha256"] or
            stored.get("registration_sha256") != meta["registration_sha256"] or
            type(stored.get("bars")) is not int or stored["bars"] != len(frame) or
            any(stored.get(k) != meta[k] for k in ("first_session", "last_session"))):
        raise ValueError("BIST_REGISTERED_INPUT_CHANGED")
    return frame, meta
