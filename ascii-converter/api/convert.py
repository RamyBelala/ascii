import json
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from urllib.parse import urlparse, parse_qs

from PIL import Image, ImageEnhance, ImageOps

CHARSET = "@%#*+=-:. "   # dark -> light (for light backgrounds)
CHAR_ASPECT = 0.5        # terminal chars are ~2x taller than wide
MAX_BYTES = 4_000_000    # Vercel body limit is ~4.5MB


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


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            q = parse_qs(urlparse(self.path).query)
            width = max(20, min(250, int(q.get("width", ["100"])[0])))
            invert = q.get("invert", ["0"])[0] == "1"

            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return self._send(400, {"error": "empty upload"})
            if length > MAX_BYTES:
                return self._send(413, {"error": "file too large"})

            art = to_ascii(self.rfile.read(length), width, invert)
            self._send(200, {"ascii": art, "cols": width, "rows": art.count("\n") + 1})
        except (OSError, ValueError):
            self._send(400, {"error": "invalid image"})
        except Exception:
            self._send(500, {"error": "conversion failed"})

    def do_GET(self):
        self._send(405, {"error": "POST an image"})
