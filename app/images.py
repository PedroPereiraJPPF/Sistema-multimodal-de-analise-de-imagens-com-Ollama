"""Image normalization before sending it to the model."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

# Image.open only reads the header, so a tiny file can declare enormous
# dimensions and exhaust memory when decoded (a "decompression bomb").
# 50 MP is far above any phone photo and is checked before decoding.
MAX_PIXELS = 50_000_000


def prepare_image(data: bytes, max_side: int) -> bytes:
    """Return the upload as a compact JPEG, upright and no larger than max_side.

    Phone photos are often 4000px+ and several MB. The model sees a downscaled
    version anyway, so shrinking here saves transfer time, image tokens and VRAM.
    Raises ValueError for anything that is not a usable image.
    """
    try:
        image = Image.open(io.BytesIO(data))
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise ValueError(f"Imagem grande demais ({width}x{height} pixels).")
        image = ImageOps.exif_transpose(image)  # respect the phone's rotation
        image = image.convert("RGB")  # forces the full decode
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("O arquivo enviado não é uma imagem válida.") from exc

    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
