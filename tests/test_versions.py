import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("versions", ROOT / "scripts/versions.py")
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.config = versions.load_config(ROOT / "versions.json")
        self.lock = {"schema": 1}
        for technology in ("php", "composer"):
            self.lock[technology] = {
                version: f"docker.io/library/{technology}:{versions.source_tag(technology, version)}@sha256:" + "a" * 64
                for version in self.config[technology]
            }

    def load_modified_config(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "versions.json"
            path.write_text(json.dumps(config))
            return versions.load_config(path)

    def test_cartesian_matrix_and_default_aliases(self):
        matrix = versions.build_matrix(self.config, self.lock)["include"]
        self.assertEqual(len(matrix), len(self.config["php"]) * len(self.config["composer"]))
        tags = [tag for row in matrix for tag in row["tags"].splitlines()]
        self.assertEqual(len(tags), len(set(tags)))
        for row in matrix:
            expected = [f"{self.config['repository']}:{row['composer']}-php{row['php']}"]
            if row["composer"] == self.config["default_composer"]:
                expected.append(f"{self.config['repository']}:php{row['php']}")
            if (row["php"] == max(self.config["php"], key=versions.version_key)
                    and row["composer"] == max(self.config["composer"], key=versions.version_key)):
                expected.append(f"{self.config['repository']}:latest")
            self.assertEqual(row["tags"].splitlines(), expected)
            self.assertEqual(row["local_tag"], f"composer-custom:{row['composer']}-php{row['php']}")

    def test_latest_alias_uses_highest_configured_versions(self):
        config = {
            **self.config,
            "php": ["8.9", "8.10"],
            "composer": ["2.9", "2.10"],
        }
        lock = {
            "schema": 1,
            **{
                technology: {
                    version: f"docker.io/library/{technology}:{versions.source_tag(technology, version)}@sha256:" + "a" * 64
                    for version in config[technology]
                }
                for technology in ("php", "composer")
            },
        }

        matrix = versions.build_matrix(config, lock)["include"]
        latest_rows = [row for row in matrix if f"{config['repository']}:latest" in row["tags"].splitlines()]

        self.assertEqual(len(latest_rows), 1)
        self.assertEqual((latest_rows[0]["php"], latest_rows[0]["composer"]), ("8.10", "2.10"))

    def test_reject_patch_versions_duplicates_and_invalid_defaults(self):
        for field, value in (("php", ["8.2.1"]), ("composer", ["2.10.3"]),
                             ("php", ["8.2", "8.2"]), ("default_composer", "9.9"),
                             ("repository", "bad/repo:tag"), ("platforms", ["linux/unknown"])):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    self.load_modified_config({**self.config, field: value})

    def test_reject_missing_stale_and_invalid_locks(self):
        for image in (None, "php:8.2-cli-alpine", "docker.io/library/php:8.3-cli-alpine@sha256:" + "a" * 64):
            with self.subTest(image=image):
                self.lock["php"]["8.2"] = image
                with self.assertRaises(ValueError):
                    versions.build_matrix(self.config, self.lock)
        del self.lock["php"]["8.2"]
        with self.assertRaises(ValueError):
            versions.build_matrix(self.config, self.lock)

    def test_resolver_checks_manifest_integrity_and_platforms(self):
        payload = json.dumps({"manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
        ]}).encode()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        with patch.object(versions, "request", return_value=(payload, {"Docker-Content-Digest": digest})):
            image = versions.resolve_digest("php", "8.2", self.config["platforms"], "token")
            self.assertEqual(image, f"docker.io/library/php:8.2-cli-alpine@{digest}")
            with self.assertRaises(ValueError):
                versions.resolve_digest("php", "8.2", ["linux/s390x"], "token")
        with patch.object(versions, "request", return_value=(payload, {"Docker-Content-Digest": "sha256:" + "b" * 64})):
            with self.assertRaises(ValueError):
                versions.resolve_digest("php", "8.2", self.config["platforms"], "token")

    def test_refresh_is_idempotent_and_atomic_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            with patch.object(versions, "request", return_value=(b'{"token":"token"}', {})), \
                    patch.object(versions, "resolve_digest", side_effect=lambda technology, version, *_: self.lock[technology][version]):
                self.assertTrue(versions.refresh(self.config, path))
                self.assertFalse(versions.refresh(self.config, path))
            before = path.read_text()
            with patch.object(versions, "request", return_value=(b'{"token":"token"}', {})), \
                    patch.object(versions, "resolve_digest", side_effect=ValueError("Upstream unavailable")):
                with self.assertRaises(ValueError):
                    versions.refresh(self.config, path)
            self.assertEqual(path.read_text(), before)


if __name__ == "__main__":
    unittest.main()