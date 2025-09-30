# Digestor v1.3  
  
LangChain Multi-Agent Architecture with Validation & Quality Control Release  
## **System Flow**  
  
```mermaid  
graph TD
    A[PDF Input] --> B[OCR Agent]
    B --> C[JSON Merger]
    C --> D[Engineering QA Agent]
    D --> E[Deflection Defaults]
    E --> F[Validation Agent]
    F --> G[Final Output]
    G --> H[CSV + JSON + Validated CSV]
 ``` 

## **Quick Start**  
  
### **Step 1: Environment Setup**  
```bash  
# Install requirements  
pip install -r requirements.txt  
  
$env:PYTHONPATH = "$PWD;$PWD\llm_tools;$PWD\ocr_tools"  
```  
  
### **Step 2: Command Line Interface**  
```bash  
python merged_batch_workflow.py --directory "path/to/pdfs" --prompt-engineering  
# OCR Only:  
bashpython langchain_agents/merged_batch_workflow.py --directory "test" --processing-mode ocr_only  
# LLM Only:  
bashpython langchain_agents/merged_batch_workflow.py --directory "test" --processing-mode llm_only --ocr-data-dir "test"  
``` 

Key Features
------------

### 1. Merged JSON Processing

*   **Batch OCR First**: Process all PDFs through OCR before LLM analysis
*   **Unified Context**: Merge JSON results for cross-document intelligence
*   **LLM**: Single analysis pass across multiple documents
*   **Answer Consolidation**: Merging of answers from different sources

### 2. Hierarchical Engine System

#### OCR Engines (Priority-based Fallback)

1.  **AWS Textract** - Primary engine (high accuracy)
2.  **Tesseract** - First fallback
3.  **Claude Vision (Bedrock)** - Second fallback
4.  **OpenCV** - Fallback for basic text

#### LLM Engines (Automatic Switching)

1.  **GPT-4o** - Primary (800k TPM capacity)
2.  **DeepSeek R1** - Cost-effective fallback
3.  **LlaMa 4** - Fallback
4.  **Claude Sonnet 4.5** - Fallback

### 3. Engineering Domain Intelligence

#### Pattern Recognition

*   **Compiled Patterns**: Building codes, materials, specifications
*   **Section Detection**
*   **Coordinate Extraction**: Precise location tracking (x, y, width, height)
*   **Confidence Scoring**: Page-level OCR quality metrics

#### Question Processing

*   **Engineering Questions**: Building codes, loads, deflection, seismic
*   **Automatic Defaults**: L/240, L/360 criteria from `deflection_defaults.csv`
*   **Unit Preservation**: Maintains PSF, MPH, inches, ratios
*   **Source Attribution**: PDF, page, section, coordinates

### 4. Validation & Quality Control

#### ValidationAgent

*   **Validation Rules**: Loads, deflection, categories, factors
*   **Unit Standardization**: feet -> inches, ksi -> psf, mph normalization
*   **Range Checking**: Min/max thresholds, enum validation
*   **Quality Scoring**: OK/FAIL/SKIP with detailed notes

#### Output Files

1.  **Results CSV**: All answers with metadata and validation columns
2.  **Results JSON**: Structured data with processing summary
  

### Performance Results on Test Case 1: 2 PDFs (18 pages total)

    Processing Summary:
    ├── OCR Processing: ~2 minutes
    │   ├── Spec Book (4 pages): 14.7s, 80% confidence
    │   └── Quote (14 pages): 109.7s, 72% confidence
    ├── LLM Processing: ~6 minutes (4 chunks)
    │   ├── Chunk 1: 6 pages, 57s
    │   ├── Chunk 2: 1 page, 52s
    │   ├── Chunk 3: 5 pages, 122s (with retry)
    │   └── Chunk 4: 6 pages, 80s (with retry)
    └── Validation: <1s
    
    Results:
    ├── Questions Answered: 22/25 (88%)
    ├── Coordinates Found: 23/25 (92%)
    ├── Sections Identified: 23/25 (92%)
    ├── Deflection Defaults: 2 applied
    └── Validation: 15 OK, 6 FAIL, 4 SKIP (60% pass)

### Accuracy Metrics

| Metric | Score | Notes |
| --- | --- | --- |
| Source PDF Matching | 100% | Sections correctly mapped to PDFs |
| Coordinate Extraction | 92% | 23/25 answers with bounding boxes |
| Section Detection | 92% | S100, S0.1, etc. identified |
| OCR Confidence | 76% avg | 80% spec book, 72% quote |
| Answer Quality | 88% | 22/25 questions answered |

System Components
-----------------

### File Structure

    agentic/
    ├── agents/
    │   ├── base_agent.py           # Base agent class
    │   ├── ocr_agent.py            # Multi-engine OCR processing
    │   ├── qa_agent.py             # Hierarchical LLM Q&A
    │   ├── validation_agent.py     # Quality control & validation
    │   └── orchestrator_agent.py   # Workflow coordination
    ├── workflow.py                  # Single document processing
    ├── merged_batch_workflow.py    # Batch merged processing
    └── config.yaml                  # System configuration
    
    llm/
    ├── llm_engines/
    │   ├── llm_registry.py         # Engine management
    │   ├── openai.py               # GPT-4o interface
    │   ├── anthropic.py            # Claude interface
    │   └── deepseek.py             # DeepSeek interface
    └── utils.py                     # Deflection defaults
    
    ocr/
    ├── ocr_engine/
    │   ├── aws_textract.py         # AWS Textract
    │   ├── azure.py                # Azure Document Intelligence
    │   └── claude.py               # Claude Vision
    └── processors/
        └── pattern.py               # Engineering patterns
    
    validation/
    ├── limits.json                  # Validation rules
    └── deflection_defaults.csv      # Default deflection values

### Agent Responsibilities

#### OCR Agent

*   **Input**: PDF files
*   **Process**: Multi-engine OCR with fallback
*   **Output**: JSON with text, confidence, coordinates per page

#### Engineering QA Agent

*   **Input**: Merged OCR JSON from multiple PDFs
*   **Process**: LLM analysis of 25 engineering questions
*   **Output**: Answers with source attribution (PDF, page, section, coordinates)

#### Validation Agent

*   **Input**: Results DataFrame
*   **Process**: Unit standardization + range validation
*   **Output**: Validated CSV with OK/FAIL/SKIP status


## Coordinate Tracking Feature

Every answer includes bounding box coordinates:

json

    {
      "Question": "What is the basic wind speed?",
      "Main_Answer": "120 MPH",
      "Page": 3,
      "Section": "S0.1",
      "Coordinates": "(640, 824, 1, 30)",
      "OCR_Confidence": 72
    }

Format: `(x, y, width, height)` in pixels

## Section Identification Feature

Automatic extraction of drawing sheet numbers

### Deflection Defaults

Automatically applied from `deflection_defaults.csv`:

csv

    Question,Default_Value
    What is the ceiling joist framing deflection limit?,L/240
    What is the maximum primary structure vertical deflection due to live load?,L/240