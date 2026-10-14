"""Bounded, local-only sanitisation; no upload, storage client or raw-file persistence."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import warnings
from xml.etree import ElementTree

from PIL import Image, ImageOps, JpegImagePlugin, UnidentifiedImageError
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


def _apple_hdr_primary(data, source):
    """Validate the observed two-JPEG Apple gain-map envelope, not general MPO."""
    def reject():
        raise UnsafeImage("Unsupported multi-image photograph", "image_validation_failed")

    entries = source.mpinfo.get(0xB002, [])
    if source.n_frames != 2 or len(entries) != 2:
        reject()
    # Locate the MPF TIFF origin in the primary JPEG's bounded header.
    position, origins = 2, []
    while position + 4 <= len(data):
        if data[position] != 255:
            reject()
        marker = data[position + 1]
        if marker == 0xDA:
            break
        length = int.from_bytes(data[position + 2:position + 4], "big")
        end = position + 2 + length
        if length < 2 or end > len(data):
            reject()
        if marker == 0xE2 and data[position + 4:position + 8] == b"MPF\0":
            origins.append(position + 8)
        position = end
    if len(origins) != 1:
        reject()
    first, auxiliary = entries
    for entry, kind in ((first, "Baseline MP Primary Image"), (auxiliary, "Undefined")):
        attributes = entry["Attribute"]
        if (attributes["MPType"] != kind or attributes["ImageDataFormat"] != "JPEG"
                or attributes["Reserved"] or attributes["DependentParentImageFlag"]
                or attributes["DependentChildImageFlag"] or attributes["RepresentativeImageFlag"]
                or entry["EntryNo1"] or entry["EntryNo2"]):
            reject()
    split = first["Size"]
    if (first["DataOffset"] != 0 or split <= origins[0]
            or origins[0] + auxiliary["DataOffset"] != split
            or auxiliary["Size"] <= 0 or split + auxiliary["Size"] != len(data)
            or data[:2] != b"\xff\xd8" or data[split - 2:split] != b"\xff\xd9"
            or data[split:split + 2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9"):
        reject()
    width, height = source.size
    if min(width, height) < 2 or max(width, height) > MAX_INPUT_SIDE or width * height > MAX_PIXELS:
        raise UnsafeImage("Photograph dimensions exceed the safe processing limit", "image_resource_limit")
    orientation = source.getexif().get(274, 1)
    if orientation not in range(1, 9) or source.mode != "RGB":
        reject()
    source.seek(1)
    if (source.size != (width // 2, height // 2) or source.mode != "L"
            or source.getexif().get(274, 1) != orientation):
        reject()
    if any(marker == "APP2" and value.startswith(b"MPF\0") for marker, value in source.applist):
        reject()
    # Exact structured declaration; arbitrary text or MPF Undefined is insufficient.
    prefix = b"http://ns.adobe.com/xap/1.0/\0"
    packets = [value[len(prefix):] for marker, value in source.applist
               if marker == "APP1" and value.startswith(prefix)]
    if len(packets) != 1 or len(packets[0]) > 65536:
        reject()
    packet = packets[0]
    if b"\0" in packet or b"<!DOCTYPE" in packet.upper() or b"<!ENTITY" in packet.upper():
        reject()
    try:
        # The verified envelope uses UTF-8. Reject alternate encodings rather
        # than allowing encoded DTD/entity declarations to evade the bound.
        root = ElementTree.fromstring(packet.decode("utf-8"))
    except (ElementTree.ParseError, UnicodeDecodeError):
        reject()
    property_name = "{http://ns.apple.com/pixeldatainfo/1.0/}AuxiliaryImageType"
    declarations = []
    for node in root.iter():
        if property_name in node.attrib:
            declarations.append(node.attrib[property_name])
        if node.tag == property_name:
            declarations.append((node.text or "").strip())
    if declarations != ["urn:com:apple:photo:2020:aux:hdrgainmap"]:
        reject()
    source.load()  # Reject corrupt auxiliary entropy, within the existing worker limits.
    return split


def _open_photo(data, formats):
    source = Image.open(BytesIO(data), formats=formats)
    if source.format != "MPO":
        return source
    try:
        primary_size = _apple_hdr_primary(data, source)
    finally:
        source.close()
    # Explicit JPEG opening avoids MPO adoption; only validated primary bytes decode.
    return JpegImagePlugin.JpegImageFile(BytesIO(data[:primary_size]))


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
            with _open_photo(data, formats) as source:
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
