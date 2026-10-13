"""Offline validation only. Run in approved CPython 3.14 Linux; no network/storage calls."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import unittest
from io import BytesIO

if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
    raise SystemExit("BLOCKED: requires approved Linux CPython 3.14 runtime")
source = Path(os.environ.get("PHASE_A_SOURCE", "/source"))
fixtures = Path(os.environ.get("HEIC_FIXTURES", "/validation/fixtures"))
output = Path(os.environ.get("VALIDATION_OUTPUT", "/output/linux-heic-results.json"))
sys.path[:0] = [str(source), str(source / "backend")]
assert importlib.metadata.version("Pillow") == "12.3.0"
assert importlib.metadata.version("pillow-heif") == "1.8.1"
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from terraces_images import sanitise_photo, UnsafeImage

register_heif_opener(thumbnails=False)
manifest = json.loads((fixtures.parent / "fixture-manifest.json").read_text())
checks = []
for fixture in manifest:
    data = (fixtures / fixture["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == fixture["sha256"]
    with Image.open(BytesIO(data)) as raw:
        raw.load()
        assert raw.format == "HEIF"
        frames = getattr(raw, "n_frames", 1)
        expected = ImageOps.exif_transpose(raw).size
        if frames != 1:
            try:
                sanitise_photo(data)
            except UnsafeImage:
                checks.append({"file": fixture["file"], "multi_frame_rejected": True})
                continue
            raise AssertionError("Multi-image HEIC must not bypass the single-photo rule")
    processed = sanitise_photo(data)
    for name, variant, limit in (("display", processed.display, 1600), ("thumbnail", processed.thumbnail, 400)):
        assert max(variant.width, variant.height) <= limit
        with Image.open(BytesIO(variant.data)) as clean:
            clean.load()
            assert clean.format == "JPEG" and clean.size == (variant.width, variant.height)
            assert not clean.getexif()
            assert all(key not in clean.info for key in ("exif", "xmp", "icc_profile", "gps"))
        assert abs(variant.width / variant.height - expected[0] / expected[1]) < .05
    checks.append({"file": fixture["file"], "genuine_heic_decoded": True,
                   "display_dimensions": [processed.display.width, processed.display.height],
                   "thumbnail_dimensions": [processed.thumbnail.width, processed.thumbnail.height],
                   "metadata_stripped": True})
assert any(check.get("genuine_heic_decoded") for check in checks)
# Existing tests generate real HEIC with EXIF orientation/GPS, assert exact
# orientation, reject malformed/oversized/animated/unsafe files and bound output.
suite = unittest.defaultTestLoader.loadTestsFromName("backend.tests.test_terraces_images")
result = unittest.TextTestRunner(verbosity=2).run(suite)
receipt = {"status": "PASS" if result.wasSuccessful() else "FAIL",
           "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
           "Pillow": importlib.metadata.version("Pillow"), "pillow-heif": importlib.metadata.version("pillow-heif"),
           "image_tests_run": result.testsRun, "genuine_fixture_checks": checks,
           "source_sha256": hashlib.sha256((source / "backend/terraces_images.py").read_bytes()).hexdigest(),
           "network_calls": 0, "hosted_writes": 0}
output.write_text(json.dumps(receipt, indent=2) + "\n")
raise SystemExit(0 if result.wasSuccessful() else 1)
