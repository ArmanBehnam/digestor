class PDFTextExtractor:
    def extract_text_and_metadata(self, pdf_path):
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return {
                'text': text,
                'total_pages': len(pdf.pages),
                'metadata': {},
                'tables': []
            }

def create_pdf_extractor():
    return PDFTextExtractor()