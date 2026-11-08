"""Image normalization before sending it to the model."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError


def prepare_image(data: bytes, max_side: int) -> bytes:
    """Return the upload as a compact JPEG, upright and no larger than max_side.

    Phone photos are often 4000px+ and several MB. The model sees a downscaled
    version anyway, so shrinking here saves transfer time, image tokens and VRAM.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)  # respect the phone's rotation
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("O arquivo enviado não é uma imagem válida.") from exc

    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
