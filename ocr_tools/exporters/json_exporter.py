import json
from pathlib import Path


class JSONExporter:
    def export(self, result, output_path):
        try:
            data = result.to_dict()
        except:
            data = {
                'document_id': result.document_id,
                'filename': result.filename,
                'extracted_text': result.extracted_text,
                'structured_data': result.structured_data,
                'confidence': result.confidence
            }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def create_json_exporter():
    return JSONExporter()