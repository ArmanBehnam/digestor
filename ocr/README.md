# PDF Processor v2.2 - Document Processing Engine

A comprehensive, production-ready document processing system specifically designed for engineering and construction documents. Features multi-engine OCR with intelligent fallbacks, computer vision-based table detection, domain-specific pattern recognition, and advanced document analysis capabilities.

## Get Results

```bash
# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials (for Textract/Claude)
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

## Architecture Overview

```bash
# Run interactive interface
python main.py

PDF Input → Multi-Engine OCR → Pattern Recognition → Structured Output
    ↓              ↓                    ↓                  ↓
File Validation → Spatial Analysis → Table Detection → Export Formats
                          ↓
                Processing Pipeline (6 Stages)
```

### Core Processing Pipeline

1. **PDF Text Extraction** - Extract machine-readable text via pdfplumber
2. **Multi-Engine OCR** - 6 OCR engines with intelligent fallback system
3. **Pattern Recognition** - 80+ regex patterns for construction terminology
4. **Table Detection** - Computer vision-based table extraction
5. **Spatial Analysis** - Layout analysis and element grouping
6. **Document Classification** - Automatic document type detection

## Multi-Engine OCR System

### Supported OCR Engines (Priority Order)

| Engine | Priority | Strengths | Requirements |
|--------|----------|-----------|--------------|
| **AWS Textract** | 10 (Primary) | Excellent accuracy, table extraction, 10MB limit | AWS credentials |
| **Azure Document Intelligence** | 1 (Near-Primary) | Layout analysis, 30+ languages, 500MB limit | Azure API key |
| **Claude OCR** | 8 (AI-Powered) | Technical document reasoning, structured extraction | AWS Bedrock access |
| **Tesseract** | 20 (Local) | Offline processing, multi-language, no API costs | Local installation |
| **Mistral OCR** | 25 (Alternative) | Good accuracy, reasonable pricing | Mistral API key |
| **OpenCV** | 90 (Fallback) | Text region detection when OCR fails | Local processing |

### Intelligent Fallback System

```bash
# Automatic engine selection with fallback
aws_textract → azure_ocr → claude_ocr → tesseract → mistral → opencv
```

- **Smart Retry Logic** - Exponential backoff with configurable attempts
- **Confidence Filtering** - Automatic quality threshold enforcement
- **Error Recovery** - Graceful degradation when engines fail
- **Cost Optimization** - Prefer local engines when accuracy sufficient

## Domain-Specific Features

### Construction & Engineering Focus

**Advanced Pattern Recognition** (80+ patterns across 9 categories):
- **Building Codes**: IBC, OBC, ASCE standards, UFC blast design
- **Material Specifications**: Steel grades (A36, A992), gauge measurements, ASTM standards
- **Structural Elements**: Cold-formed metal framing, member sizes, orientations
- **Load Requirements**: Wind, seismic, deflection criteria
- **Dimensions**: Imperial/metric measurements, elevations, spacing
- **Fire Protection**: Ratings, NFPA standards, sprinkler systems
- **Project Information**: Drawing numbers, revisions, professional contacts

**Document Type Classification**:
- Architectural Plans
- Construction Specifications
- Engineering Designs
- Building Codes
- Fire Protection Documents
- Material Specifications
- Technical Manuals

## Interactive Command Interface

### Main Menu Options

1. **Upload/Select PDF File**
2. **Full Document Processing**
3. **Phase 1 Processing**
4. **OCR Text Extraction Only**
5. **Table Extraction Only**
6. **Pattern Extraction Only**
7. **Test Azure OCR**
8. **Test Claude OCR**
9. **Batch Processing**
10. **System Information**
11. **Validate Configuration**
12. **Exit**

### Enhanced Processing Features

**Keyword-Based Filtering**:
- Target specific sections: "STRUCTURAL STEEL NOTES", "DESIGN CRITERIA"
- Custom keyword support for domain-specific terms
- Fallback extraction when keywords not found
- Page-level analysis with detailed metrics

**Batch Processing**:
- Process multiple PDFs automatically
- Parallel processing support
- Comprehensive error reporting
- Progress tracking and logging


## Computer Vision Capabilities
### Table Detection (Multiple Methods)
#### Line-Based Detection:

- Morphological operations for horizontal/vertical lines
- Grid pattern recognition
- Bounding box refinement

#### Contour Analysis:

- Adaptive thresholding
- Cell grouping algorithms
- Spatial relationship analysis

#### Edge Detection:

- Canny edge detection
- Contour approximation
- Shape validation

### Image Processing Pipeline
#### Enhancement Techniques:

- Adaptive contrast enhancement (CLAHE)
- Noise reduction (bilateral filtering)
- Sharpening algorithms
- Automatic quality assessment

#### Technical Object Detection:

- Dimension lines and annotations
- Technical symbols and markers
- Arrow and pointer detection
- Drawing element classification


## Configuration System
### Multi-Level Configuration
```json
{
  "ocr": {
    "preferred_engine": "aws_textract",
    "fallback_engines": ["claude_ocr", "tesseract", "opencv"],
    "confidence_threshold": 0.5,
    "timeout_seconds": 120,
    "max_retries": 3
  },
  "processing": {
    "use_image_enhancement": true,
    "use_table_detection": true,
    "image_scale_factor": 2.0,
    "table_confidence_threshold": 0.7
  },
  "security": {
    "max_file_size_mb": 100,
    "allowed_file_extensions": [".pdf"],
    "validate_file_types": true
  }
}
```

### Configuration Sources (Priority Order):
1. Environment variables
2. Command-line config file
3. Default config.json
4. Built-in defaults

## Data Models & Output Formats
### Core Data Structures
```python
@dataclass
class ExtractedElement:
    text: str
    element_type: ElementType  # TEXT, TABLE, IMAGE, DRAWING
    page_number: int
    confidence: float
    bbox: BoundingBox
    metadata: Dict[str, Any]

@dataclass
class ExtractionResult:
    document_id: str
    extracted_text: str
    structured_data: Dict[str, List[str]]
    tables: List[SpatialTable]
    elements: List[ExtractedElement]
    confidence: float
    processing_metrics: ProcessingMetrics
```

### Export Formats

**JSON Output** (Primary):
```json
{
  "document_info": {
    "filename": "structural_plans.pdf",
    "total_pages": 25,
    "confidence": 0.87,
    "document_type": "engineering_design"
  },
  "structured_data": {
    "building_codes": ["IBC 2024", "ASCE 7-22"],
    "material_specs": ["Grade 50 steel", "16 ga deck"],
    "dimensions": ["30'-0\" span", "14 ft ceiling height"]
  },
  "filtered_pages": {
    "matching_pages": [...],
    "keywords_found": ["STRUCTURAL STEEL NOTES"],
    "fallback_used": false
  }
}
```
### DataFrame Export (Analysis):
```python
# Convert to pandas for analysis
df = parse_construction_json_to_dataframe(json_data)
summary = get_topic_summary(df)
```

## Installation & Setup
### System Requirements
```bash
# Core dependencies
Python 3.8+
OpenCV 4.x
PyMuPDF (fitz)
pdfplumber
Pillow (PIL)

# OCR engines
boto3              # AWS Textract
azure-ai-formrecognizer  # Azure Document Intelligence
pytesseract        # Tesseract OCR
mistralai          # Mistral OCR API

# Optional: GPU acceleration
torch>=2.1.0       # For advanced image processing
```
### Installation Steps
```bash
# 1. Clone repository
git clone <repository-url>
cd pdf-processor

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Tesseract (optional)
# Ubuntu/Debian: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
# Windows: Download from GitHub releases

# 5. Configure credentials
cp config.json.example config.json
# Edit config.json with your API keys
```

### Environment Variables
```bash
# AWS (Textract/Claude)
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Azure Document Intelligence
export AZURE_ENDPOINT="https://your-resource.cognitiveservices.azure.com"
export AZURE_API_KEY="your-api-key"

# Mistral AI
export MISTRAL_API_KEY="your-mistral-key"

# Tesseract (if not in PATH)
export TESSERACT_CMD="/usr/local/bin/tesseract"
```
## Usage Examples
### Basic Usage
```python
from utils.help import PDFProcessor

# Initialize processor
processor = PDFProcessor()

# Process single document
result = processor.process(
    "structural_plans.pdf",
    use_ocr=True,
    extract_tables=True,
    extract_patterns=True
)

print(f"Extracted {len(result.elements)} elements")
print(f"Found {len(result.structured_data)} pattern categories")
```
### Enhanced Processing with Keywords
```python
from utils.help import EnhancedPDFProcessor

# Initialize enhanced processor
processor = EnhancedPDFProcessor()

# Add custom keywords
processor.add_custom_keywords([
    "DESIGN CRITERIA",
    "LOAD REQUIREMENTS", 
    "STRUCTURAL STEEL NOTES"
])

# Process with page-level results
result = processor.process_with_page_results("document.pdf")

# Get summary
summary = processor.get_page_summary(result)
print(f"Found keywords on {summary['pages_with_keywords']} pages")
```

### Batch Processing
```python
# Process entire directory
results = processor.process_batch(
    input_dir="./input_pdfs",
    output_dir="./results",
    file_pattern="*.pdf"
)

print(f"Processed {results['successful']}/{results['total_files']} files")
```

## Quality Assessment & Metrics
### Confidence Scoring
#### Multi-Level Confidence:

- **OCR Confidence**: Engine-specific confidence scores
- **Pattern Confidence**: Regex match strength
- **Spatial Confidence**: Bounding box accuracy
- **Overall Confidence**: Weighted combination

#### Quality Grades:

- **Excellent**: CER ≤ 2%, WER ≤ 5%
- **Good**: CER ≤ 5%, WER ≤ 10%
- **Moderate**: CER ≤ 10%, WER ≤ 20%
- **Poor**: Above moderate thresholds

### Performance Metrics
```python
@dataclass
class ProcessingMetrics:
    total_elements: int
    avg_confidence: float
    processing_time: float
    memory_usage: float
    high_confidence_elements: int
    ocr_engine_used: str
```

## Production Deployment
### Docker Deployment
```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
```
This is perfect for: Engineering firms, construction companies, document processing services, and organizations requiring reliable extraction from technical documents.