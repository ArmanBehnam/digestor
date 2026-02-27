# ocr/extractors/pdf_extractor.py

import logging

logger = logging.getLogger(__name__)


class PDFTextExtractor:
    def extract_text_and_metadata(self, pdf_path):
        import pdfplumber
        text = ""
        total_pages = 0
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text() or ""
                        text += page_text
                    except Exception as e:
                        # Some pages have PDFObjRef or other non-iterable objects
                        # that crash pdfplumber - skip those pages gracefully
                        logger.warning(f"pdfplumber failed on page {i+1}: {e}")
                        text += ""
        except Exception as e:
            logger.warning(f"pdfplumber failed to open PDF: {e}, falling back to fitz for page count")
            # Fallback: use fitz/PyMuPDF just to get page count
            try:
                import fitz
                doc = fitz.open(str(pdf_path))
                total_pages = len(doc)
                doc.close()
            except Exception:
                total_pages = 0

        return {
            'text': text,
            'total_pages': total_pages,
            'metadata': {},
            'tables': []
        }


def create_pdf_extractor():
    return PDFTextExtractor()
