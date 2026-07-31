import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf_ocr(pdf_path: str) -> str:
    """
    Extracts text from a rasterized PDF using pdf2image and pytesseract.
    Returns the concatenated OCR text.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return ""
        
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path)
        text = ""
        for image in images:
            # lang='deu+eng' requires tesseract-ocr-deu to be installed
            text += pytesseract.image_to_string(image, lang='deu+eng') + "\n"
        return text
    except Exception as e:
        logger.error(f"OCR failed for {pdf_path}: {e}")
        return ""
