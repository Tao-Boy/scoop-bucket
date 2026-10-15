import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_pebrel", ROOT / "scripts/update_pebrel.py")
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdatePebrelTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "bucket/pebrel.json").read_text(encoding="utf-8"))
        self.manifest["version"] = "1.9.1"
        for arch, name in (("64bit", "x64"), ("arm64", "arm64")):
            self.manifest["architecture"][arch]["url"] = (
                f"https://github.com/Kuddev/pebrel/releases/download/v1.9.1/"
                f"Pebrel-v1.9.1-windows-{name}.zip"
            )
            self.manifest["architecture"][arch]["hash"] = "0" * 64
        self.release = {
            "tag_name": "v2.2.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": f"Pebrel-v2.2.0-windows-{arch}.zip",
                    "browser_download_url": (
                        "https://github.com/Kuddev/pebrel/releases/download/v2.2.0/"
                        f"Pebrel-v2.2.0-windows-{arch}.zip"
                    ),
                    "state": "uploaded",
                    "size": 7,
                    "digest": "sha256:" + digest * 64,
                }
                for arch, digest in (("x64", "a"), ("arm64", "b"))
            ],
        }

    def test_updates_both_architectures_and_preserves_installation_fields(self):
        original = copy.deepcopy(self.manifest)
        with patch.object(updater, "open_url", side_effect=AssertionError("Unexpected download")):
            result = updater.updated_manifest(self.manifest, self.release)
        self.assertEqual(result["version"], "2.2.0")
        self.assertEqual(result["architecture"]["64bit"]["hash"], "a" * 64)
        self.assertEqual(result["architecture"]["arm64"]["hash"], "b" * 64)
        self.assertEqual(
            result["architecture"]["arm64"]["url"],
            "https://github.com/Kuddev/pebrel/releases/download/v2.2.0/Pebrel-v2.2.0-windows-arm64.zip",
        )
        for key in set(original) - {"version", "architecture"}:
            self.assertEqual(result[key], original[key])
        self.assertEqual(self.manifest, original)

    def test_incomplete_release_leaves_file_unchanged(self):
        self.release["assets"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pebrel.json"
            before = json.dumps(self.manifest).encode()
            path.write_bytes(before)
            with self.assertRaises(ValueError):
                updater.update(path, self.release)
            self.assertEqual(path.read_bytes(), before)

    def test_download_failure_leaves_file_unchanged(self):
        self.release["assets"][1]["digest"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pebrel.json"
            before = json.dumps(self.manifest).encode()
            path.write_bytes(before)
            with patch.object(updater, "open_url", side_effect=OSError("Network unavailable")):
                with self.assertRaises(OSError):
                    updater.update(path, self.release)
            self.assertEqual(path.read_bytes(), before)

    def test_unchanged_release_does_not_rewrite_json(self):
        current = updater.updated_manifest(self.manifest, self.release)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pebrel.json"
            before = json.dumps(current, separators=(",", ":")).encode()
            path.write_bytes(before)
            self.assertFalse(updater.update(path, self.release))
            self.assertEqual(path.read_bytes(), before)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pebrel.json"
            before = json.dumps(self.manifest).encode()
            path.write_bytes(before)
            self.assertTrue(updater.update(path, self.release, dry_run=True))
            self.assertEqual(path.read_bytes(), before)

    def test_success_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pebrel.json"
            path.write_text(json.dumps(self.manifest), encoding="utf-8")
            self.assertTrue(updater.update(path, self.release))
            result = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["version"], "2.2.0")
            self.assertEqual(result["architecture"]["arm64"]["hash"], "b" * 64)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_draft_prerelease_and_unsupported_tags_are_rejected(self):
        for change in ({"draft": True}, {"prerelease": True}, {"tag_name": "v2.2.0-rc1"}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    updater.updated_manifest(self.manifest, self.release | change)

    def test_downgrades_are_skipped(self):
        self.manifest["version"] = "3.0.0"
        with patch.object(updater, "asset_sha256", side_effect=AssertionError("Unexpected hash")):
            self.assertEqual(updater.updated_manifest(self.manifest, self.release), self.manifest)

    def test_unready_or_duplicate_asset_is_rejected(self):
        for change in ({"state": "new"}, {"size": 0}):
            with self.subTest(change=change):
                release = copy.deepcopy(self.release)
                release["assets"][0].update(change)
                with self.assertRaises(ValueError):
                    updater.updated_manifest(self.manifest, release)
        self.release["assets"].append(self.release["assets"][0])
        with self.assertRaises(ValueError):
            updater.updated_manifest(self.manifest, self.release)

    def test_unexpected_download_host_is_rejected(self):
        self.manifest["autoupdate"]["architecture"]["64bit"]["url"] = "https://example.com/$version.zip"
        with self.assertRaises(ValueError):
            updater.updated_manifest(self.manifest, self.release)

    def test_missing_digest_falls_back_to_hashing_zip(self):
        asset = self.release["assets"][0] | {"digest": None}
        with patch.object(updater, "open_url", return_value=io.BytesIO(b"zipdata")) as download:
            self.assertEqual(updater.asset_sha256(asset), hashlib.sha256(b"zipdata").hexdigest())
            download.assert_called_once_with(asset["browser_download_url"])

    def test_truncated_download_is_rejected(self):
        asset = self.release["assets"][0] | {"digest": None}
        with patch.object(updater, "open_url", return_value=io.BytesIO(b"zip")):
            with self.assertRaises(ValueError):
                updater.asset_sha256(asset)


if __name__ == "__main__":
    unittest.main()
