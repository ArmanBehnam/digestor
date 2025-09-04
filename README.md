<<<<<<< HEAD
# Digetor v1.2

LangChain Multi-Agent Architecture with Validation & Quality Control Release
## **System Flow**

```mermaid
graph TD
    A[PDF Input] --> B[OCR Agent]
    B --> C[Content Extractor Agent] 
    C --> D[Page Filter Agent]
    D --> E[Engineering QA Agent]
    E --> V[Validation Agent]
    V --> F[Orchestrator Agent]
    F --> G[Results CSV/JSON + Validated CSV]
=======
# Digetor v1.1

LangChain Multi-Agent Architecture

## **System Flow**

```mermaid
graph TD
    A[PDF Input] --> B[OCR Agent]
    B --> C[Content Extractor Agent]
    C --> D[Page Filter Agent]
    D --> E[Engineering QA Agent]
    E --> F[Orchestrator Agent]
    F --> G[Results CSV/JSON]
>>>>>>> 09d9ed020ed290b55a288a7e615cc041a7f21627
    
    H[User Config] --> F
    I[LLM Engines] --> E
    J[Prompt Engineering] --> E
<<<<<<< HEAD
    K[limits.json] --> V
=======
>>>>>>> 09d9ed020ed290b55a288a7e615cc041a7f21627
```


## **Quick Start**

### **Step 1: Environment Setup**
```bash
# Install dependencies
pip install langchain langchain-openai langchain-anthropic
pip install langchain-community langchain-experimental
pip install pydantic python-dotenv

# Install existing requirements
pip install -r requirements.txt

$env:PYTHONPATH = "$PWD;$PWD\llm_tools;$PWD\ocr_tools"
```

### **Step 2: Command Line Interface**
```bash
<<<<<<< HEAD
python merged_batch_workflow.py --directory "path/to/pdfs" --prompt-engineering

# OCR Only:
bashpython langchain_agents/merged_batch_workflow.py --directory "test" --processing-mode ocr_only

# LLM Only:
bashpython langchain_agents/merged_batch_workflow.py --directory "test" --processing-mode llm_only --ocr-data-dir "test"

# Full Pipeline:
bashpython langchain_agents/merged_batch_workflow.py --directory "test" --processing-mode full
```

## **Key Innovations & Advancements**

### **1. Merged JSON Processing**
- **Process all PDFs through OCR first**
- **Merge JSON results from multiple documents**
- **Single LLM call on combined data for efficiency**
- **Cross-document analysis capability**

### **2. Hierarchical Engine System**
- **OCR Engines**: AWS Textract, Azure, Claude, Tesseract (priority-based fallback)
- **LLM Engines**: GPT-4o (800k TPM), Claude Sonnet 4, DeepSeek R1 (automatic fallback)
- **Smart Failure Recovery**: Automatic engine switching on rate limits/failures

### **3. Engineering Domain Expertise**
- **80+ Engineering Patterns**: Building codes, materials, structural elements
- **26 Domain Questions**: Covers all major engineering disciplines
- **Automatic Deflection Defaults**: L/240, L/360 criteria applied intelligently
- **Technical Precision**: Units, ratios, code years preserved

### **4. Validation & Quality Control**
- **ValidationAgent**: Automated range checking against engineering limits
- **Unit Standardization**: Converts feet→inches, ksi→psf, mph normalization
- **Engineering Thresholds**: 20 validation rules for loads, deflection, categories
- **Quality Metrics**: OK/FAIL/SKIP status with detailed failure notes

## **System Performance & Results on Test case 1**

### **Latest Test Results with Validation (100% Success Rate)**
```bash
BATCH SUMMARY: 2/2 PDFs processed successfully
Total Pages Processed: 18 pages across 2 engineering documents
Questions Answered: 25 total
Validation Results: 13 OK, 8 FAIL, 4 SKIP
Processing Time: ~2 minutes per batch
OCR Confidence: 0.76 average
```
=======
# Standard processing (individual PDFs)
python batch_workflow.py --directory "path/to/pdfs"

# Merged JSON processing (more efficient)
python merged_batch_workflow.py --directory "path/to/pdfs" --prompt-engineering
```

## **Key Innovations & Advancements**

### **1. Merged JSON Processing**
- **Process all PDFs through OCR first**
- **Merge JSON results from multiple documents**
- **Single LLM call on combined data for efficiency**
- **Cross-document analysis capability**

### **2. Hierarchical Engine System**
- **OCR Engines**: AWS Textract, Azure, Claude, Tesseract (priority-based fallback)
- **LLM Engines**: GPT-4o (800k TPM), Claude Sonnet 4, DeepSeek R1 (automatic fallback)
- **Smart Failure Recovery**: Automatic engine switching on rate limits/failures

### **3. Engineering Domain Expertise**
- **80+ Engineering Patterns**: Building codes, materials, structural elements
- **26 Domain Questions**: Covers all major engineering disciplines
- **Automatic Deflection Defaults**: L/240, L/360 criteria applied intelligently
- **Technical Precision**: Units, ratios, code years preserved

## **System Performance & Results on Test case 1**

### **Latest Test Results (100% Success Rate)**
```bash
BATCH SUMMARY: 3/3 PDFs processed successfully
Total Pages Processed: 53 pages across 3 engineering documents
Questions Answered: 75 total (25 questions × 3 PDFs)
Processing Time: ~5 minutes average per document
Deflection Defaults: 3 applied automatically
OCR Confidence: 0.74 average
```
### **Processing Times**
| Document Type | Pages | OCR Time | LLM Time | Total Time |
|---------------|-------|----------|----------|------------|
| Spec Book | 4 pages | 0.94s | 6.7s | ~8s |
| Quote Document | 35 pages | 229s | 12s | ~4 min |
| Structural Plans | 14 pages | 297s | 11s | ~5 min |

### **Success Rates**
- **Overall Success**: 100% (3/3 PDFs)
- **OCR Accuracy**: 74% average confidence
- **Question Coverage**: 100% (25/25 questions answered)
- **Deflection Defaults**: Applied when needed (3/25 questions)


>>>>>>> 09d9ed020ed290b55a288a7e615cc041a7f21627

## **Production Deployment**

### **File Structure**
```
langchain_agents/
├── agents/
│   ├── base_agent.py          # LangChain base class
│   ├── ocr_agent.py           # Multi-engine OCR
│   ├── qa_agent.py            # Hierarchical LLM
<<<<<<< HEAD
│   ├── validation_agent.py    # Range validation + unit standardization
│   └── orchestrator_agent.py  # Main coordinator
├── workflow.py                # Standard processing
├── batch_workflow.py          # Batch processing
├── merged_batch_workflow.py   # Merged JSON processing
limits.json                    # Validation rules
=======
│   └── orchestrator_agent.py  # Main coordinator
├── workflow.py                # Standard processing
├── batch_workflow.py          # Batch processing
├── merged_batch_workflow.py   # Merged JSON (NEW)
└── test_simple.py            # Quick testing
>>>>>>> 09d9ed020ed290b55a288a7e615cc041a7f21627
```

## **Integration with Existing Systems**

### **LangChain Components Used**
```python
from langchain.agents import BaseAgent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, SystemMessage

# Agent wrapper for existing functionality
class OCRAgent(BaseAgent):
    def __init__(self):
        self.pdf_processor = EnhancedPDFProcessor()
        self.memory = ConversationBufferMemory()
```

### **Legacy Integration**
- **OCR Tools**: Wraps existing `ocr_tools/` codebase
- **LLM Tools**: Integrates `llm_tools/` hierarchical engines
- **No Code Duplication**: Agents call existing functions
- **Backward Compatible**: Original pipeline still works



## **Agent Architecture Details**

### **1. Orchestrator Agent (LangChain Coordinator)**
```python
class OrchestratorAgent(Talk2DrawingsBaseAgent):
    def __init__(self, config):
        self.ocr_agent = OCRAgent(config)
        self.qa_agent = EngineeringQAAgent(config)
        self.memory = ConversationBufferMemory()  # LangChain integration
    
    async def process(self, input_data):
        # Step 1: OCR Processing
        ocr_result = await self.ocr_agent.safe_process(pdf_path)
        
        # Step 2: Engineering Q&A  
        qa_result = await self.qa_agent.safe_process(ocr_result)
        
        # Step 3: Apply defaults and generate results
        final_results = await self._generate_final_results(...)
        
        return final_results
```

### **2. OCR Agent (Multi-Engine Processing)**
- **Responsibilities**: PDF to Images to OCR to Filtered Pages
- **Engine Management**: Priority-based selection with fallback
- **Pattern Recognition**: 80+ engineering-specific patterns
- **Quality Control**: Confidence scoring and validation

**Input**: PDF files, processing options
**Output**: Raw extracted text per page with metadata

```python
class OCRAgent(BaseAgent):
    def __init__(self):
        self.tools = [
            AWSTractTool(),
            AzureOCRTool(), 
            ClaudeOCRTool(),
            TesseractTool()
        ]
        self.fallback_chain = OCRFallbackChain(self.tools)
```

### **3. Engineering QA Agent (Hierarchical LLM)**
- **Question Processing**: 26 engineering questions in parallel
- **LLM Hierarchy**: GPT-4o to Claude to DeepSeek with automatic fallback
- **Prompt Engineering**: Context-aware optimization (optional)
- **Result Validation**: Confidence scoring and answer formatting

**Input**: Raw OCR text and images
**Output**: Structured data (tables, patterns, clean text)

```python
class ContentExtractorAgent(BaseAgent):
    def __init__(self):
        self.pattern_processor = EngineeringPatternProcessor()
        self.table_detector = TableDetectionTool()
        self.text_cleaner = TextCleaningChain()
```


### **4. Engineering QA Agent**
**Purpose**: Answer engineering questions using hierarchical LLM processing

**LangChain Components**:
- `BaseAgent` - Question processing
- `LLMChain` - Hierarchical LLM engines  
- `PromptTemplate` - Dynamic prompt engineering
- `OutputParser` - Structured answer extraction



<<<<<<< HEAD
### **5. ValidationAgent (Quality Control)**
- **Responsibilities**: Unit standardization and range validation
- **Engineering Rules**: 20 validation rules from limits.json
- **Unit Conversion**: Feet→inches, ksi→psf, mph normalization
- **Quality Scoring**: OK/FAIL/SKIP with detailed failure analysis

**Input**: Results DataFrame with answers
**Output**: Validated CSV with quality metrics

```python
class ValidationAgent(BaseAgent):
    def __init__(self):
        self.rules = load_validation_rules()
        self.unit_converters = UnitStandardization()
    
    async def process(self, results_dataframe):
        # Step 1: Standardize units
        # Step 2: Validate ranges
        # Step 3: Generate quality report
```


=======
>>>>>>> 09d9ed020ed290b55a288a7e615cc041a7f21627
## **LangChain Integration Details**

```python
from langchain.agents import BaseAgent, Tool, AgentExecutor
from langchain.tools import BaseTool

# Custom OCR Tools
class AWSTractTool(BaseTool):
    name = "aws_textract"
    description = "High-accuracy OCR using AWS Textract"
    
    def _run(self, pdf_path: str) -> str:
        # Integration with existing aws_textract engine
        return self.textract_engine.process(pdf_path)

# Agent Executor with multiple tools
agent_executor = AgentExecutor(
    agent=ocr_agent,
    tools=[AWSTractTool(), AzureOCRTool(), ClaudeOCRTool()],
    memory=memory,
    verbose=True
)
```


## **Workflow Execution**

### **Sequential Processing Flow**
```python
async def execute_workflow(pdf_path: str, user_config: dict):
    workflow = Talk2DrawingsWorkflow()
    
    # Initialize orchestrator with memory
    orchestrator = workflow.orchestrator
    orchestrator.memory.clear()
    
    # Execute multi-agent workflow
    result = await workflow.process_document(pdf_path, user_config)
    
    # Generate outputs
    csv_path = generate_csv_output(result)
    json_path = generate_json_output(result)
    
    return {
        'success': True,
        'csv_output': csv_path,
        'json_output': json_path,
        'metrics': result['processing_metrics']
    }
```

### **Parallel Processing Capabilities**
```python
import asyncio
from langchain.agents import AgentExecutor

async def parallel_domain_processing(filtered_pages, questions):
    # Group questions by engineering domain
    domain_groups = {
        'building_codes': questions[0:3],
        'deflection': questions[3:9], 
        'wind_loads': questions[9:13],
        'seismic': questions[20:25]
    }
    
    # Process domains in parallel
    tasks = []
    for domain, domain_questions in domain_groups.items():
        task = process_domain_questions(filtered_pages, domain_questions)
        tasks.append(task)
    
    # Wait for all domains to complete
    results = await asyncio.gather(*tasks)
    
    # Combine results
    combined_answers = {}
    for domain_result in results:
        combined_answers.update(domain_result)
    
    return combined_answers
```



## **Benefits of Multi-Agent Architecture**

### **1. Scalability**
- **Parallel Processing**: Multiple agents work simultaneously
- **Load Distribution**: Each agent handles specific responsibilities  
- **Easy Extension**: Add new agents for additional capabilities

### **2. Maintainability**
- **Separation of Concerns**: Each agent has single responsibility
- **Modular Design**: Agents can be developed and tested independently
- **Clear Interfaces**: Standardized input/output between agents

### **3. Reliability**
- **Fault Isolation**: Agent failures don't crash entire system
- **Graceful Degradation**: System continues with reduced functionality
- **Error Recovery**: Individual agents can retry and recover

### **4. Flexibility**
- **Configurable Workflows**: Easy to modify agent sequences
- **Pluggable Components**: Swap agents without changing others
- **Custom Agents**: Add domain-specific agents as needed


