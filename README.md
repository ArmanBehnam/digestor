<<<<<<< HEAD
﻿# Talk2Drawings Pipeline - Production Version

## 🏗️ Overview
Advanced engineering document processing pipeline that extracts technical information from PDFs using cutting-edge OCR and LLM technologies. Built specifically for structural, seismic, and civil engineering document analysis.

## ✨ Key Features

### 🔧 **OCR Processing**
- **Azure Document Intelligence** integration for high-accuracy text extraction
- **Hierarchical OCR engines** with automatic fallback support
- **Smart page filtering** using engineering keyword detection
- **Table and pattern extraction** for structured data
- **Multi-format support** (PDF, images)

### 🤖 **LLM Processing**
- **Hierarchical LLM engines**: GPT-4o → Claude Sonnet 4 → DeepSeek R1
- **Automatic fallback system** with priority-based engine selection
- **Comprehensive prompt engineering** (NEW!) with context-aware optimization
- **Domain-specific adaptation** for engineering content
- **OCR error resilience** and smart result validation

### 🎯 **Engineering Focus**
- **26 engineering questions** covering:
  - Building codes (IBC, ASCE, AISC references)
  - Deflection criteria (L/240, L/360 ratios)
  - Wind loads (speeds, exposure categories, pressure coefficients)
  - Seismic parameters (Sds, Sd1, site class, design categories)
  - Snow loads and gravity loads
- **Automatic deflection defaults** for common structural criteria
- **Technical value preservation** (units, ratios, code years)

### 🚀 **Advanced Capabilities**
- **Prompt Engineering System** (NEW!):
  - Context-aware prompt optimization
  - Document type detection (specs, drawings, reports)
  - Engineering domain recognition
  - Question type classification
  - OCR error handling strategies
- **Multi-project processing** with organized output
- **Performance caching** and optimization
- **Comprehensive error handling** and fallback mechanisms

## 🏛️ Architecture

### **Core Modules**

#### **Main Pipeline** (`pipeline.py`)
- Interactive mode selection (OCR, LLM, Both)
- User prompt engineering choices
- Project discovery and processing coordination
- Status reporting and error handling

#### **LLM Tools** (`llm_tools/`)
- **`llm_interface.py`** - Main LLM coordination interface
- **`llm_engines/`** - Hierarchical engine system:
  - `openai_engine.py` - GPT-4o (primary)
  - `anthropic_engine.py` - Claude Sonnet 4 (fallback)
  - `deepseek_engine.py` - DeepSeek R1 (fallback)
  - `llm_registry.py` - Engine coordination and fallback logic
- **`prompt_engineer.py`** - Advanced prompt optimization system
- **`utils.py`** - Document processing and result aggregation
- **`config.yaml`** - Comprehensive configuration management

#### **OCR Tools** (`ocr_tools/`)
- **Hierarchical OCR engines** with Azure Document Intelligence
- **Pattern recognition** and keyword filtering
- **Table extraction** and structured data processing
- **Multi-format document support**

### **Configuration System**
```yaml
# LLM Engines (hierarchical fallback)
llm_engines:
  preferred_engine: "openai_gpt4o"
  fallback_engines: ["anthropic_sonnet", "deepseek_r1"]

# Prompt Engineering (NEW!)
prompt_engineering:
  enabled: false  # User selectable
  optimization_level: "balanced"  # conservative/balanced/aggressive
  # Comprehensive feature controls...
```

## 🚀 **Usage**

### **Quick Start**
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys in llm_tools/config.yaml
# - OpenAI API key (required)
# - Azure OCR credentials (required)
# - Anthropic/DeepSeek keys (optional, for fallback)

# 3. Run the pipeline
python pipeline.py

# 4. Follow interactive prompts:
#    - Enter data directory
#    - Select mode (OCR/LLM/Both)
#    - Choose prompt engineering (Automatic/Static)
#    - Select optimization level
```

### **Processing Modes**

**Mode 1: OCR Only**
- Processes PDFs to generate `*_ocr_result.json` files
- Extracts and filters relevant pages
- Ideal for initial document processing

**Mode 2: LLM Only** (Recommended)
- Uses existing JSON files for question answering
- Optimized per-project processing
- Hierarchical LLM engines with fallback
- Optional prompt engineering

**Mode 3: Both**
- Complete end-to-end processing
- Skips OCR for projects with existing JSON files
- Combines OCR and LLM processing intelligently

### **Prompt Engineering Options**

**Automatic (Recommended)**
- ✅ Context-aware optimization
- ✅ Engineering domain detection
- ✅ OCR error resilience
- ✅ Better accuracy for technical content

**Static (Traditional)**
- ⚡ Faster processing
- 📝 Predictable generic prompts
- 🔧 Simple and consistent

## 📊 **Output & Results**

### **File Structure**
```
data/
├── prj_01/
│   ├── document.pdf
│   ├── document_ocr_result.json
│   └── pipeline_results_v4_prj_01_[timestamp].csv
└── prj_02/
    ├── document.pdf
    ├── document_ocr_result.json
    └── pipeline_results_v4_prj_02_[timestamp].csv
```

### **CSV Output Format**
- **Question**: Engineering question asked
- **Answer**: Extracted answer with technical details
- **Page**: Source page reference
- **Confidence**: LLM confidence score (0-100%)
- **Source**: Source engine and document
- **Deflection_Default**: Applied default values (if any)

### **Performance Metrics**
- **Success rates** per project and overall
- **Confidence scores** for answer quality assessment
- **Engine statistics** and fallback usage
- **Processing time** and optimization metrics

## 🔧 **Configuration**

### **API Keys Required**
```yaml
# Primary (Required)
openai_api_key: "your-openai-key"
AZURE_ENDPOINT: "your-azure-endpoint"
AZURE_API_KEY: "your-azure-key"

# Fallback (Optional)
anthropic_api_key: "your-anthropic-key"  # For Claude Sonnet
deepseek_api_key: "your-deepseek-key"    # For DeepSeek R1
```

### **Engineering Questions**
26 pre-configured questions covering:
- 🏛️ Building codes and standards
- 📏 Deflection criteria and limits
- 🌬️ Wind load parameters
- ❄️ Snow load criteria
- 🌎 Seismic design parameters
- ⚖️ Gravity loads

## 🎯 **Key Improvements**

### **Latest Version Features**
- ✅ **Hierarchical LLM engines** with automatic fallback
- ✅ **Advanced prompt engineering** with context optimization
- ✅ **User-selectable processing options** for flexibility
- ✅ **Enhanced error handling** and resilience
- ✅ **Performance optimization** with caching
- ✅ **Comprehensive status reporting** and monitoring

### **Engineering-Specific Enhancements**
- ✅ **Better technical accuracy** for complex engineering content
- ✅ **Improved code detection** (IBC 2018, ASCE 7-16, etc.)
- ✅ **Enhanced deflection ratio extraction** (L/240, L/360)
- ✅ **Robust seismic parameter detection** (Sds, Sd1, site class)
- ✅ **Wind load criteria optimization** (exposure, GCpi, speeds)

## 📚 **Documentation**

- **`PROMPT_ENGINEERING_GUIDE.md`** - Complete prompt engineering documentation
- **`PROMPT_ENGINEERING_IMPLEMENTATION_SUMMARY.md`** - Technical implementation details
- **`FINAL_VERSION_SUMMARY.md`** - Version history and changes
- **`Technical_Architecture_Report.md`** - Detailed system architecture
- **`ocr_tools/README.md`** - OCR system documentation

## 🛠️ **Development & Testing**

### **Test Scripts**
- `test_prompt_engineering.py` - Prompt optimization testing
- `test_integration_prompt_engineering.py` - End-to-end testing
- `test_llm_engines.py` - Engine hierarchy testing

### **Debug Tools**
- Comprehensive logging and error reporting
- Engine status monitoring
- Prompt optimization statistics
- Performance metrics collection

## 🏆 **Production Ready**

This pipeline is production-ready with:
- ✅ **Robust error handling** and fallback mechanisms
- ✅ **Scalable architecture** for multiple projects
- ✅ **Comprehensive testing** and validation
- ✅ **Flexible configuration** for different use cases
- ✅ **Performance optimization** for efficiency
- ✅ **Engineering domain expertise** built-in

---

**Ready to extract engineering data with unprecedented accuracy and reliability!** 🚀
- Confidence scores
- Processing metadata
=======
# Introduction 
TODO: Give a short introduction of your project. Let this section explain the objectives or the motivation behind this project. 

# Getting Started
TODO: Guide users through getting your code up and running on their own system. In this section you can talk about:
1.	Installation process
2.	Software dependencies
3.	Latest releases
4.	API references

# Build and Test
TODO: Describe and show how to build your code and run the tests. 

# Contribute
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)
>>>>>>> f5d1974b337958616cd39bd143c02b747f3539be
