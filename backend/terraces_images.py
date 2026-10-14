"""Bounded, local-only sanitisation; no upload, storage client or raw-file persistence."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

MAX_INPUT_BYTES = 10_000_000  # 10 MB, decimal.
MAX_PIXELS = 24_000_000
MAX_INPUT_SIDE = 10_000
DISPLAY_SIDE = 1600
THUMBNAIL_SIDE = 400


class UnsafeImage(ValueError):
    def __init__(self, message, code="image_validation_failed", guard=None):
        super().__init__(message)
        self.code = code
        self.guard = guard


@dataclass(frozen=True)
class ImageVariant:
    data: bytes
    width: int
    height: int
    content_type: str = "image/jpeg"


@dataclass(frozen=True)
class SanitisedPhoto:
    source_sha256: str
    source_bytes: int
    display: ImageVariant
    thumbnail: ImageVariant


def sanitise_photo(data: bytes) -> SanitisedPhoto:
    """Reject unsupported/multi-frame files; create fresh pixels without metadata.

    The future HTTP caller must also bound the request while reading it; this
    function cannot undo an already unbounded request-body allocation.
    """
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_INPUT_BYTES:
        raise UnsafeImage("Photographs must be non-empty and no larger than 10 MB")
    if data.startswith(b"\xff\xd8\xff"):
        formats = ["JPEG"]
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        formats = ["PNG"]
    elif len(data) >= 20 and data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1"}:
        # Load the optional native codec only for its container; failure stays closed.
        box_size = int.from_bytes(data[:4], "big")
        if not 20 <= box_size <= len(data) or box_size % 4:
            raise UnsafeImage("Invalid HEIC container")
        if data[8:12] == b"mif1" and not any(data[pos:pos+4] in {b"heic", b"heix", b"hevc", b"hevx"} for pos in range(16, box_size, 4)):
            raise UnsafeImage("Only HEIC image containers are supported", "unsupported_image_encoding", "heif_compatible_codec")
        register_heif_opener(thumbnails=False)
        formats = ["HEIF"]
    else:
        raise UnsafeImage("Only JPEG, PNG and HEIC photographs are supported", "unsupported_image_encoding", "signature_or_major_brand")
    clean = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=formats) as source:
                if source.format not in {"JPEG", "PNG", "HEIF"}:
                    raise UnsafeImage("Only JPEG, PNG and HEIC photographs are supported", "unsupported_image_encoding", "decoded_format")
                width, height = source.size
                if min(width, height) < 1 or max(width, height) > MAX_INPUT_SIDE or width * height > MAX_PIXELS:
                    raise UnsafeImage("Photograph dimensions exceed the safe processing limit", "image_resource_limit")
                if getattr(source, "n_frames", 1) != 1:
                    raise UnsafeImage("Only one still photograph per file is supported")
                source.load()
                ImageOps.exif_transpose(source, in_place=True)
                # Do not copy info, EXIF, XMP, ICC, GPS or embedded thumbnails.
                with source.convert("RGBA") as rgba:
                    clean = Image.new("RGB", rgba.size, "white")
                    with rgba.getchannel("A") as alpha:
                        clean.paste(rgba, mask=alpha)
            # Release decoder-owned data and full-resolution intermediates
            # before allocating either variant. Closing the HEIF image alone
            # can leave plugin data referenced by the local source object.
            del source
            variants = []
            for side in (DISPLAY_SIDE, THUMBNAIL_SIDE):
                with clean.copy() as variant:
                    variant.thumbnail((side, side), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    variant.save(output, format="JPEG", quality=85, progressive=True)
                    variants.append(ImageVariant(output.getvalue(), *variant.size))
    except UnsafeImage:
        raise
    except (MemoryError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise UnsafeImage("Photograph exceeds the safe processing memory limit", "image_resource_limit") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise UnsafeImage("The photograph could not be safely decoded", "image_decode_failed") from error
    finally:
        if clean is not None:
            clean.close()
    return SanitisedPhoto(sha256(data).hexdigest(), len(data), *variants)
