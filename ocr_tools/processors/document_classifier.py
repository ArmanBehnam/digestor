from ocr_tools.core.models import DocumentType

class DocumentClassifier:
    def classify(self, text, elements):
        return DocumentType.GENERAL

def create_document_classifier():
    return DocumentClassifier()