import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf_ocr(pdf_path: str) -> str:
    """
    Extracts text from a rasterized PDF using pypdfium2 (rendering) and pytesseract.
    Returns the concatenated OCR text.
    """
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError:
        return ""

    try:
        text = ""
        pdf = pdfium.PdfDocument(pdf_path)
        try:
            for page in pdf:
                # 200 dpi (scale 1 = 72 dpi) wie bisher bei pdf2image; Seite einzeln
                # rendern und freigeben, damit grosse Scans nicht komplett im RAM liegen.
                image = page.render(scale=200 / 72).to_pil()
                # lang='deu+eng' requires tesseract-ocr-deu to be installed
                text += pytesseract.image_to_string(image, lang="deu+eng") + "\n"
                page.close()
        finally:
            pdf.close()
        return text
    except Exception as e:
        logger.error(f"OCR failed for {pdf_path}: {e}")
        return ""
