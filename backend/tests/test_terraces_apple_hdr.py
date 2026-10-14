"""Synthetic Apple HDR envelope: no private photograph or metadata fixtures."""
from io import BytesIO
import struct
import unittest
import sys
import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from terraces_images import sanitise_photo, UnsafeImage


def apple_hdr(*, size=(65, 97), orientation=1, auxiliary_mode="L", auxiliary_size=None, declaration=True, xml=None):
    primary = Image.new("RGB", size, "red")
    auxiliary = Image.new(auxiliary_mode, auxiliary_size or (size[0] // 2, size[1] // 2), 90)
    exif = Image.Exif()
    exif[274] = orientation
    exif[270] = "private synthetic metadata"
    exif[34853] = {1: "N", 2: (1.0, 0.0, 0.0)}
    primary.info["exif"] = auxiliary.info["exif"] = exif.tobytes()
    stream = BytesIO()
    primary.save(stream, "MPO", save_all=True, append_images=[auxiliary], exif=exif)
    data = stream.getvalue()
    with Image.open(BytesIO(data)) as image:
        first, second = image.mpinfo[0xB002]
    split = first["Size"]
    if not declaration:
        return data
    packet = xml or (b'<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:p="http://ns.apple.com/pixeldatainfo/1.0/">'
                     b'<p:AuxiliaryImageType>urn:com:apple:photo:2020:aux:hdrgainmap</p:AuxiliaryImageType></x:xmpmeta>')
    payload = b"http://ns.adobe.com/xap/1.0/\0" + packet
    segment = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    # MP index size changes; its auxiliary offset remains unchanged.
    old_entry = struct.pack("<LLLHH", 0, second["Size"], second["DataOffset"], 0, 0)
    new_entry = struct.pack("<LLLHH", 0, second["Size"] + len(segment), second["DataOffset"], 0, 0)
    head = data[:split]
    assert head.count(old_entry) == 1
    return head.replace(old_entry, new_entry) + data[split:split + 2] + segment + data[split + 2:]


class AppleHdrTests(unittest.TestCase):
    def test_primary_variants_orientation_and_metadata(self):
        result = sanitise_photo(apple_hdr(size=(2297, 3027), orientation=6))
        self.assertEqual((result.display.width, result.display.height), (1600, 1214))
        self.assertEqual((result.thumbnail.width, result.thumbnail.height), (400, 304))
        for variant in (result.display, result.thumbnail):
            with Image.open(BytesIO(variant.data)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(getattr(image, "n_frames", 1), 1)
                self.assertFalse(image.getexif())
                for key in ("exif", "xmp", "mp", "icc_profile"):
                    self.assertNotIn(key, image.info)
                self.assertGreater(image.getpixel((10, 10))[0], 240)
            self.assertNotIn(b"private", variant.data)

    def test_unrelated_or_wrong_auxiliary_rejected(self):
        for data in (apple_hdr(declaration=False), apple_hdr(auxiliary_mode="RGB"),
                     apple_hdr(auxiliary_size=(31, 47)),
                     apple_hdr(xml=b'<wrong/>'), apple_hdr(xml=b'<broken'),
                     apple_hdr(xml=b'<!DOCTYPE x [<!ENTITY a "bad">]><x/>')):
            with self.subTest(length=len(data)), self.assertRaises(UnsafeImage):
                sanitise_photo(data)

    def test_truncation_and_trailing_bytes_rejected(self):
        data = apple_hdr()
        for invalid in (data[:-2], data + b"extra"):
            with self.assertRaises(UnsafeImage):
                sanitise_photo(invalid)

    def test_ambiguous_primary_and_offsets_rejected(self):
        data = apple_hdr()
        with Image.open(BytesIO(data)) as source:
            second = source.mpinfo[0xB002][1]
        old = struct.pack("<LLLHH", 0, second["Size"], second["DataOffset"], 0, 0)
        for attribute, offset in ((0x030000, second["DataOffset"]), (0, second["DataOffset"] - 1)):
            invalid = data.replace(old, struct.pack("<LLLHH", attribute, second["Size"], offset, 0, 0), 1)
            with self.assertRaises(UnsafeImage):
                sanitise_photo(invalid)

    def test_duplicate_auxiliary_declaration_rejected(self):
        packet = (b'<x xmlns:p="http://ns.apple.com/pixeldatainfo/1.0/" '
                  b'p:AuxiliaryImageType="urn:com:apple:photo:2020:aux:hdrgainmap">'
                  b'<p:AuxiliaryImageType>urn:com:apple:photo:2020:aux:hdrgainmap</p:AuxiliaryImageType></x>')
        with self.assertRaises(UnsafeImage):
            sanitise_photo(apple_hdr(xml=packet))

    def test_dimensions_and_memory_fail_closed(self):
        data = apple_hdr()
        with patch("terraces_images.MAX_PIXELS", 10), self.assertRaises(UnsafeImage) as caught:
            sanitise_photo(data)
        self.assertEqual(caught.exception.code, "image_resource_limit")
        with patch("terraces_images.ImageOps.exif_transpose", side_effect=MemoryError()), self.assertRaises(UnsafeImage) as caught:
            sanitise_photo(data)
        self.assertEqual(caught.exception.code, "image_resource_limit")

    def test_extra_frames_rejected(self):
        stream = BytesIO()
        Image.new("RGB", (64, 64)).save(stream, "MPO", save_all=True,
            append_images=[Image.new("L", (32, 32)), Image.new("L", (32, 32))])
        with self.assertRaises(UnsafeImage):
            sanitise_photo(stream.getvalue())

    @unittest.skipUnless(sys.platform == "linux", "Existing RLIMIT worker is Linux-only")
    def test_linux_worker_limits_and_peak_memory(self):
        worker = Path(__file__).resolve().parents[1] / "terraces_image_worker.py"
        runner = ("import runpy,resource,atexit,sys;"
                  "atexit.register(lambda:print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,file=sys.stderr));"
                  "runpy.run_path(sys.argv[1],run_name='__main__')")
        result = subprocess.run([sys.executable, "-c", runner, str(worker)],
            input=apple_hdr(size=(2297, 3027)), capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        value = json.loads(result.stdout)
        self.assertEqual((value["display"]["width"], value["display"]["height"]), (1214, 1600))
        peak = int(result.stderr.strip())
        self.assertLess(peak, 768 * 1024)
        print("Synthetic Apple HDR worker peak RSS KiB:", peak)
