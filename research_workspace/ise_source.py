"""Explicit UCI 247 archive collection and immutable, source-bound local snapshots."""
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
import csv
import hashlib
import json
import math
import re
import ssl
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

import certifi
from research_workspace.ise_ml import COLUMNS, SOURCE_URL, load_csv
from research_workspace.stage7_preparation_ui import _local_directory

ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/247/istanbul%2Bstock%2Bexchange.zip"
PINNED_RAW_SHA256 = "a30838316290a83a98a52a46c30174e0204c963c0877627954ebc74111668922"
ARCHIVE_LIMIT, XLSX_LIMIT, PARTS_LIMIT = 200_000, 100_000, 2_000_000
SCHEMA = "tradelab.ise-ml.snapshot.v1"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _zip(payload, limit):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= limit:
        raise ValueError("ISE_ARCHIVE_SIZE")
    archive = zipfile.ZipFile(BytesIO(payload))
    items = archive.infolist()
    if (len(items) > 64 or len({i.filename for i in items}) != len(items) or
            sum(i.file_size for i in items) > PARTS_LIMIT or any(i.flag_bits & 1 for i in items)):
        archive.close()
        raise ValueError("ISE_ARCHIVE_STRUCTURE")
    return archive


def _part(archive, name, limit=PARTS_LIMIT):
    if archive.getinfo(name).file_size > limit:
        raise ValueError("ISE_ARCHIVE_SIZE")
    with archive.open(name) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("ISE_XML_REJECTED")
    return ET.fromstring(raw)


def parse_archive(payload):
    """Return canonical CSV; no extraction, formula evaluation or model fitting."""
    with _zip(payload, ARCHIVE_LIMIT) as source:
        if set(source.namelist()) != {"data_akbilgic.xlsx"}:
            raise ValueError("ISE_ARCHIVE_STRUCTURE")
        if source.getinfo("data_akbilgic.xlsx").file_size > XLSX_LIMIT:
            raise ValueError("ISE_ARCHIVE_SIZE")
        with source.open("data_akbilgic.xlsx") as stream:
            book = stream.read(XLSX_LIMIT + 1)
    with _zip(book, XLSX_LIMIT) as archive:
        workbook = _part(archive, "xl/workbook.xml")
        props = workbook.find(NS + "workbookPr")
        if props is not None and props.get("date1904", "0").lower() not in ("0", "false"):
            raise ValueError("ISE_UNSUPPORTED_DATE_EPOCH")
        sheets = workbook.find(NS + "sheets")
        if sheets is None or len(sheets) != 1:
            raise ValueError("ISE_WORKSHEET_STRUCTURE")
        rels = _part(archive, "xl/_rels/workbook.xml.rels")
        selected = [r for r in rels if r.get("Id") == sheets[0].get(RID)]
        if len(selected) != 1 or selected[0].get("TargetMode") == "External":
            raise ValueError("ISE_WORKSHEET_STRUCTURE")
        target = selected[0].get("Target", "")
        if "\\" in target or ".." in PurePosixPath(target).parts or ":" in target:
            raise ValueError("ISE_WORKSHEET_STRUCTURE")
        name = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if not name.startswith("xl/worksheets/"):
            raise ValueError("ISE_WORKSHEET_STRUCTURE")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = _part(archive, "xl/sharedStrings.xml")
            strings = ["".join(n.itertext()) for n in shared.findall(NS + "si")]
        sheet = _part(archive, name)
        if any(True for _ in sheet.iter(NS + "f")):
            raise ValueError("ISE_FORMULAS_REJECTED")
        data = sheet.find(NS + "sheetData")
        if data is None or len(data) != 538:
            raise ValueError("ISE_ROW_COUNT")
        rows = []
        for expected_row, row in enumerate(data, 1):
            if row.get("r") != str(expected_row):
                raise ValueError("ISE_ROW_ORDER")
            cells = [""] * 10
            seen = set()
            for cell in row:
                ref = re.fullmatch(r"([A-Z]+)([0-9]+)", cell.get("r", ""))
                if ref is None or ref[2] != str(expected_row):
                    raise ValueError("ISE_CELL_REFERENCE")
                col = 0
                for ch in ref[1]:
                    col = col * 26 + ord(ch) - 64
                value = cell.find(NS + "v")
                raw = "" if value is None or value.text is None else value.text
                kind = cell.get("t", "n")
                if kind == "s":
                    raw = strings[int(raw)]
                elif kind == "inlineStr":
                    inline = cell.find(NS + "is")
                    raw = "" if inline is None else "".join(inline.itertext())
                elif kind not in ("n", "d"):
                    raise ValueError("ISE_CELL_TYPE")
                if col > 10 and not raw:
                    continue
                if not 1 <= col <= 10 or col in seen or len(raw) > 200:
                    raise ValueError("ISE_CELL_REFERENCE")
                seen.add(col)
                cells[col - 1] = raw
            rows.append(cells)
    if rows[0][:4] != ["", "TL BASED", "USD BASED", "imkb_x"] or rows[1] != [
            "date", "ISE", "ISE", "SP", "DAX", "FTSE", "NIKKEI", "BOVESPA", "EU", "EM"]:
        raise ValueError("ISE_SOURCE_HEADERS")
    # Establish all date boundaries before interpreting source returns.
    dates = []
    for row in rows[2:]:
        raw = row[0]
        if re.fullmatch(r"[0-9]+(?:\.0+)?", raw):
            stamp = datetime(1899, 12, 30) + timedelta(days=int(float(raw)))
        else:
            stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is not None or stamp.time() != datetime.min.time() or not 2009 <= stamp.year <= 2011:
            raise ValueError("ISE_SOURCE_DATES")
        dates.append(stamp.date().isoformat())
    out = StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for stamp, row in zip(dates, rows[2:]):
        values = [float(v) for v in row[1:]]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("ISE_SOURCE_NUMERICS")
        writer.writerow([stamp, *(format(v, ".17g") for v in values)])
    return out.getvalue().encode("utf-8")


def register_source(zip_bytes, directory):
    if not isinstance(zip_bytes, bytes) or hashlib.sha256(zip_bytes).hexdigest() != PINNED_RAW_SHA256:
        raise ValueError("ISE_SOURCE_ARCHIVE_CHANGED")
    payload = parse_archive(zip_bytes)
    _, meta = load_csv(payload, {"source_id": "uci247", "license": "CC-BY-4.0", "source_url": SOURCE_URL,
                                "raw_source_sha256": hashlib.sha256(zip_bytes).hexdigest(),
                                "csv_sha256": hashlib.sha256(payload).hexdigest()})
    if not _local_directory(str(directory)):
        raise ValueError("ISE_LOCAL_PATH_REQUIRED")
    target = Path(directory).resolve()
    if any((p / ".git").exists() for p in (target, *target.parents)):
        raise ValueError("ISE_PRIVATE_DESTINATION_REQUIRED")
    stored = {**meta, "schema": SCHEMA, "archive_url": ARCHIVE_URL, "archive_bytes": len(zip_bytes),
              "attribution": "Akbilgic, O. (2013). ISTANBUL STOCK EXCHANGE. UCI. DOI 10.24432/C54P4J"}
    target.mkdir(parents=True, exist_ok=False)
    for filename, content in (("source.zip", zip_bytes), ("bars.csv", payload)):
        with (target / filename).open("xb") as stream:
            stream.write(content)
    with (target / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(stored, stream, indent=2, allow_nan=False)
    return stored


def read_snapshot(directory):
    if not _local_directory(str(directory)):
        raise ValueError("ISE_LOCAL_PATH_REQUIRED")
    folder = Path(directory)
    source = folder / "source.zip"
    if source.is_symlink() or source.is_junction():
        raise ValueError("ISE_LOCAL_PATH_REQUIRED")
    content = {}
    for filename, limit in (("manifest.json", 100_000), ("source.zip", ARCHIVE_LIMIT), ("bars.csv", 500_000)):
        with (folder / filename).open("rb") as stream:
            content[filename] = stream.read(limit + 1)
        if len(content[filename]) > limit:
            raise ValueError("ISE_INPUT_SIZE")
    stored = json.loads(content["manifest.json"].decode("utf-8"))
    raw, payload = content["source.zip"], content["bars.csv"]
    if (not isinstance(stored, dict) or stored.get("schema") != SCHEMA or stored.get("archive_url") != ARCHIVE_URL or
            stored.get("orders_enabled") is not False or type(stored.get("archive_bytes")) is not int or
            stored["archive_bytes"] != len(raw) or hashlib.sha256(raw).hexdigest() != PINNED_RAW_SHA256 or
            hashlib.sha256(raw).hexdigest() != stored.get("raw_source_sha256") or
            parse_archive(raw) != payload):
        raise ValueError("ISE_SOURCE_MISMATCH")
    frame, meta = load_csv(payload, stored)
    for field in ("protocol", "canonical_sha256", "registration_sha256", "rows", "validation_start", "holdout_start", "bytes"):
        if type(stored.get(field)) is not type(meta[field]) or stored[field] != meta[field]:
            raise ValueError("ISE_REGISTERED_INPUT_CHANGED")
    return frame, meta


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("ISE_REDIRECT_REJECTED")


def fetch_snapshot(directory, *, explicit_download=False):
    if explicit_download is not True:
        raise ValueError("ISE_EXPLICIT_DOWNLOAD_REQUIRED")
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(
        context=ssl.create_default_context(cafile=certifi.where())))
    request = urllib.request.Request(ARCHIVE_URL, headers={"Accept": "application/zip",
                                                        "User-Agent": "TradeLab-UCI-Research/1.0"})
    with opener.open(request, timeout=20) as response:
        raw = response.read(ARCHIVE_LIMIT + 1)
    if len(raw) > ARCHIVE_LIMIT or hashlib.sha256(raw).hexdigest() != PINNED_RAW_SHA256:
        raise ValueError("ISE_SOURCE_ARCHIVE_CHANGED")
    return register_source(raw, directory)
