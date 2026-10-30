"""Bounded, read-only snapshot review; never fits a model or constructs outcomes."""
from pathlib import Path
import hashlib
from research_workspace.stage7_history import load_private
from research_workspace.stage7_events import research_partition


def _digests(folder):
    result = {}
    for name, limit in (("manifest.json", 100_000), ("bars.csv", 5_000_000)):
        with (folder / name).open("rb") as stream:
            payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("Snapshot exceeds bounded input size")
        result[name] = hashlib.sha256(payload).hexdigest()
    return result


def review_snapshot(directory):
    # Expose controlled codes, not paths, provider messages or arbitrary metadata.
    errors = {
        "Snapshot exceeds bounded input size": "INPUT_TOO_LARGE",
        "Unsupported source manifest": "UNSUPPORTED_MANIFEST",
        "Snapshot fingerprint mismatch": "HASH_MISMATCH",
        "Manifest coverage mismatch": "COVERAGE_MISMATCH",
        "Manifest byte count mismatch": "MANIFEST_MISMATCH",
        "Registered snapshot partition mismatch": "PARTITION_MISMATCH",
        "Registered snapshot changed; research partition cannot move": "PARTITION_MISMATCH",
        "Sealed period is not eligible": "SEALED_PERIOD",
    }
    try:
        folder = Path(directory)
        # Pin both metadata and prices; reject changes during the review.
        before = _digests(folder)
        frame, meta = load_private(folder, expected_digests=before)
        after = _digests(folder)
        if before != after:
            raise ValueError("Snapshot changed during review")
        partition = research_partition(frame)
        registered = meta.get("research_partition") == partition
        reserved = partition["holdout_first_session"] is not None
        return {"schema": "tradelab.stage7.snapshot-review.v1", "status": "verified_structure",
                "symbol": meta["symbol"], "feed": meta["feed"], "adjustment": meta["adjustment"],
                "csv_sha256": before["bars.csv"], "manifest_sha256": before["manifest.json"],
                "bars": len(frame), "sessions": int(frame.session.nunique()),
                "first_session": str(frame.session.iloc[0]), "last_session": str(frame.session.iloc[-1]),
                "partition_registered": registered, "holdout_reserved": reserved,
                "development_bars": partition["holdout_start"] if reserved else None,
                "holdout_first_session": partition["holdout_first_session"],
                "diagnostic_eligible": registered and reserved,
                "eligibility_reason": "REGISTERED_HISTORY" if registered and reserved else
                                      "MISSING_REGISTRATION" if not registered else "INSUFFICIENT_SESSIONS",
                "model_evaluated": False, "outcomes_computed": False,
                "independent_provenance_verified": False, "probabilities_publishable": False,
                "orders_enabled": False}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        reason = "MISSING_OR_UNREADABLE_FILES" if isinstance(exc, OSError) else errors.get(
            str(exc), "SNAPSHOT_CHANGED" if str(exc) == "Snapshot changed during review" else "INVALID_SNAPSHOT")
        return {"schema": "tradelab.stage7.snapshot-review.v1", "status": "rejected", "reason": reason}
