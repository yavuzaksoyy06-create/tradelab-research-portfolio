"""Synthetic archive fixtures verify UCI transport/parse/store mechanics only."""
from contextlib import redirect_stderr
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
import hashlib
import json
import math
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from research_workspace.ise_source import (ARCHIVE_LIMIT, ARCHIVE_URL, NS, _NoRedirect,
                                          fetch_snapshot, parse_archive, read_snapshot, register_source)
from tools.ise_ml_research import main


def archive_fixture(*, formula=False, epoch1904=False, doctype=False):
    """Build an XLSX-shaped simulated dataset; never label it real market data."""
    sheet = ET.Element(NS + "worksheet")
    table = ET.SubElement(sheet, NS + "sheetData")
    records = [["", "TL BASED", "USD BASED", "imkb_x", "", "", "", "", "", ""],
               ["date", "ISE", "ISE", "SP", "DAX", "FTSE", "NIKKEI", "BOVESPA", "EU", "EM"]]
    current = datetime(2009, 1, 5)
    for i in range(536):
        while current.weekday() >= 5:
            current += timedelta(days=1)
        records.append([(current - datetime(1899, 12, 30)).days,
                        *(math.sin(i / 13 + j) * .01 for j in range(9))])
        current += timedelta(days=1)
    for rowno, values in enumerate(records, 1):
        row = ET.SubElement(table, NS + "row", r=str(rowno))
        for colno, value in enumerate(values):
            cell = ET.SubElement(row, NS + "c", r=f"{chr(65 + colno)}{rowno}")
            if isinstance(value, str):
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, NS + "is"), NS + "t").text = value
            else:
                ET.SubElement(cell, NS + "v").text = str(value)
        if formula and rowno == 3:
            ET.SubElement(cell, NS + "f").text = "1+1"
    workbook = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<workbookPr date1904="{int(epoch1904)}"/><sheets>'
                '<sheet name="data" sheetId="1" r:id="rId1"/></sheets></workbook>')
    if doctype:
        workbook = '<!DOCTYPE workbook [<!ENTITY x "blocked">]>' + workbook
    relationships = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
    book = BytesIO()
    with zipfile.ZipFile(book, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", relationships)
        z.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))
    outer = BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("data_akbilgic.xlsx", book.getvalue())
    return outer.getvalue()


class ISESourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = archive_fixture()
        cls.pin = hashlib.sha256(cls.source).hexdigest()

    def setUp(self):
        pin = patch("research_workspace.ise_source.PINNED_RAW_SHA256", self.pin)
        pin.start()
        self.addCleanup(pin.stop)

    def test_parser_preserves_schema_and_rejects_active_or_changed_epoch_content(self):
        payload = parse_archive(self.source)
        self.assertEqual(len(payload.splitlines()), 537)
        self.assertTrue(payload.startswith(b"date,ise_try,ise_usd,sp,dax,ftse,nikkei,bovespa,eu,em\n2009-01-05,"))
        for bad in (archive_fixture(formula=True), archive_fixture(epoch1904=True), archive_fixture(doctype=True)):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                parse_archive(bad)
        with self.assertRaises(ValueError):
            parse_archive(b"x" * (ARCHIVE_LIMIT + 1))

    def test_collection_requires_explicit_action_before_transport(self):
        with patch("research_workspace.ise_source.urllib.request.build_opener") as builder:
            for flag in (False, None, 1, "true"):
                with self.subTest(flag=flag), self.assertRaises(ValueError):
                    fetch_snapshot("IGNORED", explicit_download=flag)
            builder.assert_not_called()

    def test_transport_is_one_bounded_fixed_get_and_rejects_redirects(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_source.urllib.request.build_opener") as builder:
            response = builder.return_value.open.return_value.__enter__.return_value
            response.read.return_value = self.source
            result = fetch_snapshot(Path(tmp) / "snapshot", explicit_download=True)
            self.assertEqual(result["raw_source_sha256"], self.pin)
            request = builder.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, ARCHIVE_URL)
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            builder.return_value.open.assert_called_once()
            response.read.assert_called_once_with(ARCHIVE_LIMIT + 1)
        with self.assertRaisesRegex(ValueError, "REDIRECT"):
            _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://invalid.test")

    def test_registration_is_exclusive_and_forbids_git_or_unpinned_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "snapshot"
            registered = register_source(self.source, folder)
            before = {f.name: f.read_bytes() for f in folder.iterdir()}
            self.assertEqual(registered["rows"], 536)
            with self.assertRaises(FileExistsError):
                register_source(self.source, folder)
            self.assertEqual(before, {f.name: f.read_bytes() for f in folder.iterdir()})
            git = root / "repo"
            (git / ".git").mkdir(parents=True)
            with self.assertRaises(ValueError):
                register_source(self.source, git / "private")
            self.assertFalse((git / "private").exists())
            with self.assertRaises(ValueError):
                register_source(self.source + b"changed", root / "invalid")
            self.assertFalse((root / "invalid").exists())

    def test_readback_binds_csv_and_metadata_to_raw_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "snapshot"
            register_source(self.source, folder)
            before = {f.name: f.read_bytes() for f in folder.iterdir()}
            frame, meta = read_snapshot(folder)
            self.assertEqual(len(frame), 536)
            self.assertFalse(meta["orders_enabled"])
            self.assertEqual(before, {f.name: f.read_bytes() for f in folder.iterdir()})
            manifest = folder / "manifest.json"
            source = json.loads(before["manifest.json"])
            manifest.write_text(json.dumps({**source, "registration_sha256": "0" * 64}), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_snapshot(folder)
            manifest.write_bytes(before["manifest.json"])
            changed = before["bars.csv"].replace(b"2009-01-05", b"2009-01-06", 1)
            (folder / "bars.csv").write_bytes(changed)
            manifest.write_text(json.dumps({**source, "csv_sha256": hashlib.sha256(changed).hexdigest()}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SOURCE_MISMATCH"):
                read_snapshot(folder)

    def test_cli_rejection_has_no_raw_paths_or_provider_body(self):
        error = StringIO()
        with patch("sys.argv", ["ise_ml_research.py", "collect", "--output", "SECRET_DESTINATION"]), \
             patch("research_workspace.ise_source.urllib.request.build_opener") as builder, redirect_stderr(error):
            self.assertEqual(main(), 1)
            builder.assert_not_called()
        self.assertNotIn("SECRET", error.getvalue())
