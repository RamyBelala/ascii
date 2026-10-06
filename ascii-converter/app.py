from io import BytesIO
from pathlib import Path

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException
from PIL import Image, ImageEnhance, ImageOps

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4_000_000  # Vercel body limit is ~4.5MB

CHARSET = "@%#*+=-:. "   # dark -> light (for light backgrounds)
CHAR_ASPECT = 0.5        # terminal chars are ~2x taller than wide


def to_ascii(data: bytes, width: int, invert: bool, contrast: float = 1.3) -> str:
    img = Image.open(BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    h = max(1, int(img.height / img.width * width * CHAR_ASPECT))
    img = img.resize((width, h), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)

    # white text on black: bright pixel -> dense char (unless inverted)
    chars = CHARSET if invert else CHARSET[::-1]
    n = len(chars)
    px = gray.load()
    rows = []
    for y in range(gray.height):
        row = "".join(chars[min(n - 1, px[x, y] * n // 256)] for x in range(gray.width))
        rows.append(row.rstrip())
    return "\n".join(rows)


@app.post("/api/convert")
def convert():
    try:
        width = max(20, min(250, request.args.get("width", 100, type=int)))
        invert = request.args.get("invert", "0") == "1"
        data = request.get_data()
        if not data:
            return jsonify(error="empty upload"), 400
        art = to_ascii(data, width, invert)
        return jsonify(ascii=art, cols=width, rows=art.count("\n") + 1)
    except (OSError, ValueError):
        return jsonify(error="invalid image"), 400
    except HTTPException:
        raise
    except Exception:
        return jsonify(error="conversion failed"), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="file too large"), 413


# Local fallback only: on Vercel, public/index.html is served by the CDN.
@app.get("/")
def home():
    page = Path(__file__).parent / "public" / "index.html"
    return Response(page.read_text(encoding="utf-8"), mimetype="text/html")


if __name__ == "__main__":
    app.run(port=3000, debug=True)
