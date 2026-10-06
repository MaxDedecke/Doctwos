"""OCR-Pfad Ende-zu-Ende: Bild-PDF ohne Text-Layer -> pypdfium2 -> Tesseract.

Die uebrigen PDF-Tests mocken extract_text_from_pdf_ocr; dieser Test prueft das
echte Rendering (kein poppler mehr, siehe docs/OSS-CLEARING.md) und wird
uebersprungen, wenn Tesseract oder pypdfium2 lokal fehlen.
"""

import shutil

import pytest

pytest.importorskip("pypdfium2")
pytest.importorskip("pytesseract")
pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract fehlt")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from utils import extract_text_from_pdf_ocr  # noqa: E402


def _scan_pdf(path, pages):
    images = []
    for text in pages:
        img = Image.new("RGB", (1240, 400), "white")
        font = ImageFont.load_default(size=64)
        ImageDraw.Draw(img).text((60, 150), text, fill="black", font=font)
        images.append(img)
    images[0].save(path, save_all=True, append_images=images[1:])


def test_ocr_reads_text_from_image_only_pdf(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _scan_pdf(pdf, ["Rechnung Seite Eins", "Zahlung Seite Zwei"])

    text = extract_text_from_pdf_ocr(str(pdf))

    assert "Rechnung" in text
    assert "Zwei" in text


def test_ocr_returns_empty_string_for_unreadable_pdf(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"kein pdf")

    assert extract_text_from_pdf_ocr(str(broken)) == ""
