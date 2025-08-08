from ocr_tools.utils.help import EnhancedPDFProcessor

class OCRProcessor:
    def __init__(self, config):
        self.config = config
        self.processor = EnhancedPDFProcessor()

    def process_pdf(self, pdf_file):
        return self.processor.process_with_page_results(
            pdf_file,
            use_ocr=self.config['use_ocr'],
            extract_tables=self.config['extract_tables'],
            extract_patterns=self.config['extract_patterns'],
            enhance_images=self.config['enhance_images']
        )