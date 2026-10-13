import unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image
from terraces_images import sanitise_photo, UnsafeImage, MAX_INPUT_BYTES
from pillow_heif import register_heif_opener


def encoded(fmt, *, size=(32, 20), exif=None):
    image = Image.new("RGB", size, "red")
    output = BytesIO()
    kwargs = {"exif": exif} if exif else {}
    if fmt == "HEIF":
        register_heif_opener(thumbnails=False)
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


class PhotoImageTests(unittest.TestCase):
    def test_jpeg_png_heic_are_decoded_and_stripped(self):
        exif = Image.Exif()
        exif[270] = "private metadata"
        exif[315] = "private author"
        exif[274] = 6
        exif[34853] = {1: "N", 2: (51.0, 0.0, 0.0), 3: "W", 4: (0.0, 1.0, 0.0)}
        for fmt in ("JPEG", "PNG", "HEIF"):
            with self.subTest(fmt=fmt):
                result = sanitise_photo(encoded(fmt, exif=exif))
                for variant in (result.display, result.thumbnail):
                    with Image.open(BytesIO(variant.data)) as clean:
                        self.assertEqual(clean.format, "JPEG")
                        self.assertFalse(clean.getexif())
                        self.assertNotIn("exif", clean.info)
                        self.assertNotIn("xmp", clean.info)
                        self.assertNotIn("icc_profile", clean.info)
                        self.assertEqual(clean.size, (20, 32))
                    self.assertNotIn(b"private", variant.data)

    def test_variants_are_bounded_and_do_not_upscale(self):
        result = sanitise_photo(encoded("JPEG", size=(2200, 1100)))
        self.assertEqual((result.display.width, result.display.height), (1600, 800))
        self.assertEqual((result.thumbnail.width, result.thumbnail.height), (400, 200))
        self.assertEqual(sanitise_photo(encoded("PNG")).display.width, 32)

    def test_unsafe_files_rejected(self):
        for data in (b"", b"not a photo", b"<svg>script</svg>", encoded("GIF"), b"\0\0\0\x18ftypavif\0\0\0\0avifavif", b"x" * (MAX_INPUT_BYTES + 1)):
            with self.subTest(data_length=len(data)), self.assertRaises(UnsafeImage):
                sanitise_photo(data)
        with self.assertRaises(UnsafeImage):
            sanitise_photo(encoded("JPEG")[:30])

    def test_large_dimensions_checked_before_decode(self):
        with patch("terraces_images.MAX_PIXELS", 20), self.assertRaises(UnsafeImage):
            sanitise_photo(encoded("PNG"))

    def test_animation_rejected(self):
        output = BytesIO()
        Image.new("RGB", (16, 16), "red").save(output, format="PNG", save_all=True,
                                               append_images=[Image.new("RGB", (16, 16), "blue")], duration=100)
        with self.assertRaises(UnsafeImage):
            sanitise_photo(output.getvalue())
