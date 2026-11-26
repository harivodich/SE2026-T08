"""Fresh-root receiver, provenance and fail-closed negative controls."""

import hashlib
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from vietdoc.data import pilot_packet as packet
from vietdoc.data.generator import d22, integration
from vietdoc.data.generator.templates.families import catalog, render_family
from vietdoc.data.generator.values import CONFIG
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.data.splits import assert_disjoint

ROOT = Path(__file__).resolve().parents[2]


class FamilySelectionTest(unittest.TestCase):
    def test_renderer_overflow_raises_instead_of_dropping_text(self):
        record = dict(d22.plan(read_json(d22.DEFAULT_CONFIG), 1)[0], row_count=1)
        payload = d22.payload_for(record, read_json(CONFIG))
        payload["items"][0]["description"] = "hàng hóa " * 1000
        with self.assertRaisesRegex(ValueError, "overflow/clipping"):
            render_family(payload, catalog()[0], integration.resolve_font())

    def test_default_unchanged_and_explicit_pilot_support(self):
        config = read_json(d22.DEFAULT_CONFIG)
        self.assertEqual(len(d22.plan(config, 1)), 20)
        config.update(
            bases_per_family=5,
            family_ids=[
                f"{k}-f{i:02}" for k in ("receipt", "invoice") for i in (0, 1, 6, 7)
            ],
        )
        rows = d22.plan(d22.validate_config(config), 20261126)
        self.assertEqual(len(rows), 40)
        self.assertEqual({r["split"] for r in rows}, {"train", "dev"})
        self.assertEqual({r["row_count"] for r in rows}, {0, 1, 3, 12, 30})
        assert_disjoint(rows)

    def test_invalid_families(self):
        for ids in ([], ["unknown"], ["receipt-f00"] * 2, [1]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                d22.validate_config(dict(read_json(d22.DEFAULT_CONFIG), family_ids=ids))

    def test_final_and_capacity_rejected_before_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = base / "config.json"
            config.write_bytes(encoded(read_json(d22.DEFAULT_CONFIG)))
            with self.assertRaisesRegex(ValueError, "final family"):
                packet.build(ROOT, base / "out", config, integration.resolve_font())
            self.assertFalse((base / "out").exists())
            config.write_bytes(
                encoded(
                    dict(
                        read_json(d22.DEFAULT_CONFIG),
                        bases_per_family=41,
                        family_ids=["receipt-f00"],
                    )
                )
            )
            with self.assertRaisesRegex(ValueError, "population bound"):
                packet.build(ROOT, base / "out", config, integration.resolve_font())
            self.assertFalse((base / "out").exists())


class ReceiverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        font = integration.resolve_font()
        config = dict(
            read_json(d22.DEFAULT_CONFIG),
            rows=[0],
            augmentations=[],
            dataset_version="packet-unit-v1",
            font_sha256=sha(font),
            family_ids=["receipt-f00", "receipt-f06", "invoice-f00", "invoice-f06"],
        )
        path = cls.base / "config.json"
        path.write_bytes(encoded(config))
        packet.build(ROOT, cls.base / "built", path, font)

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.case.cleanup)
        self.work = Path(self.case.name)
        self.bundle = self.work / "bundle"
        shutil.copytree(self.base / "built/packet", self.bundle)

    def rewrite(self, change):
        archive = self.bundle / packet.ARCHIVE
        with zipfile.ZipFile(archive) as zf:
            members = [(i, zf.read(i)) for i in zf.infolist()]
        members = change(members)
        with zipfile.ZipFile(archive, "w") as zf:
            for info, content in members:
                zf.writestr(info, content)
        transfer = read_json(self.bundle / "transfer.json")
        transfer["archive_sha256"] = sha(archive)
        (self.bundle / "transfer.json").write_bytes(encoded(transfer))

    def test_relocated_semantic_records_and_pixels(self):
        result = packet.verify(self.bundle, self.work / "received")
        self.assertTrue(result["verified"])
        self.assertEqual(result["counts"]["samples"], 4)
        self.assertFalse(result["training_clearance"])
        self.assertEqual(result["approval"], "not_granted")
        with self.assertRaisesRegex(ValueError, "already exists"):
            packet.verify(self.bundle, self.work / "received")

    def test_corrupt_member_with_rebound_archive_hash(self):
        self.rewrite(
            lambda rows: [
                (i, b"x" * len(b) if i.filename.endswith(".png") else b)
                for i, b in rows
            ]
        )
        with self.assertRaisesRegex(ValueError, "checksum"):
            packet.verify(self.bundle, self.work / "received")
        self.assertFalse((self.work / "received").exists())

    def test_traversal_and_casefold_archive_members(self):
        for name in ("../escape", "records.JSON"):
            with self.subTest(name=name):
                for member in (packet.ARCHIVE, "transfer.json"):
                    shutil.copyfile(
                        self.base / "built/packet" / member, self.bundle / member
                    )
                info = zipfile.ZipInfo(name)
                self.rewrite(lambda rows, extra=info: rows + [(extra, b"bad")])
                with self.assertRaises(ValueError):
                    packet.verify(self.bundle, self.work / "received")
        self.assertFalse((self.work / "escape").exists())

    def test_inventory_traversal_casefold_windows_alias(self):
        for names in (
            ["../x"],
            ["a", "A"],
            ["NUL.txt"],
            ["x."],
            ["C:/x"],
            ["a\\b"],
            ["a?b"],
            ["x\x7f"],
        ):
            with self.subTest(names=names), self.assertRaises(ValueError):
                packet._safe_names(names)

    def test_records_status_join_rejects_drift(self):
        source = self.work / "source"
        shutil.copytree(self.base / "built/snapshot", source)
        records = read_json(source / "records.json")
        records["records"][0]["labels"]["fields"][0]["status"] = "unlabeled"
        (source / "records.json").write_bytes(encoded(records))
        with self.assertRaisesRegex(ValueError, "records join"):
            packet.pack(source, self.work / "bad")

    def test_unknown_label_status_rejected_after_hash_rebinding(self):
        source = self.work / "source"
        shutil.copytree(self.base / "built/snapshot", source)
        manifest = read_json(source / "dataset/manifest.json")
        sample = manifest["samples"][0]
        label_path = source / "dataset" / sample["assets"]["labels.json"]["path"]
        labels = read_json(label_path)
        labels[next(iter(labels))]["status"] = "invented"
        label_path.write_bytes(encoded(labels))
        sample["assets"]["labels.json"]["sha256"] = sha(label_path)
        (source / "dataset/manifest.json").write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError, "label status mismatch"):
            packet.pack(source, self.work / "bad")

    def test_group_leakage_and_final_member_rejected(self):
        for mutation in ("group", "final"):
            source = self.work / mutation
            shutil.copytree(self.base / "built/snapshot", source)
            manifest = read_json(source / "dataset/manifest.json")
            if mutation == "group":
                manifest["samples"][1]["source_group"] = manifest["samples"][0][
                    "source_group"
                ]
            else:
                manifest["samples"][0]["split"] = "final"
            (source / "dataset/manifest.json").write_bytes(encoded(manifest))
            with self.assertRaisesRegex(ValueError, "cross-split|final family"):
                packet.pack(source, self.work / ("bad-" + mutation))

    def test_pixel_and_unexpected_file_rejected(self):
        source = self.work / "source"
        shutil.copytree(self.base / "built/snapshot", source)
        qa = read_json(source / "qa.json")
        qa["pixels"][0]["pixel_sha256"] = hashlib.sha256(b"wrong").hexdigest()
        (source / "qa.json").write_bytes(encoded(qa))
        with self.assertRaisesRegex(ValueError, "pixel drift"):
            packet.pack(source, self.work / "bad")
        (source / "qa.json").write_bytes(
            (self.base / "built/snapshot/qa.json").read_bytes()
        )
        (source / "unknown-final.png").write_bytes(b"forbidden extra")
        with self.assertRaisesRegex(ValueError, "unexpected/missing"):
            packet.pack(source, self.work / "bad")


if __name__ == "__main__":
    unittest.main()
