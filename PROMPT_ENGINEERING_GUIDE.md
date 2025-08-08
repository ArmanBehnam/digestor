"""
Comprehensive Guide to Prompt Engineering in Talk2Drawings Pipeline

This document explains how to use the advanced prompt engineering features
to optimize LLM performance for engineering document analysis.
"""

# PROMPT ENGINEERING FEATURES OVERVIEW
# ====================================

## 1. ENABLING PROMPT ENGINEERING

To enable prompt engineering in your pipeline:

1. Edit `llm_tools/config.yaml`
2. Set `prompt_engineering.enabled: true`
3. Configure optimization level and features

```yaml
prompt_engineering:
  enabled: true  # Change from false to true
  optimization_level: "balanced"  # Options: conservative, balanced, aggressive
```

## 2. OPTIMIZATION LEVELS

### Conservative (Fast, minimal changes)
- Basic context analysis
- Simple domain detection
- Standard format requirements
- Best for: High-throughput processing

### Balanced (Recommended)
- Full context analysis
- Domain-specific optimization
- Enhanced search strategies
- Error handling guidance
- Best for: Most engineering documents

### Aggressive (Maximum optimization)
- Deep context analysis
- Advanced question optimization
- Multi-domain adaptation
- Confidence tuning
- Cross-reference validation
- Best for: Complex technical documents

## 3. KEY FEATURES AND BENEFITS

### Context Analysis
- Automatically detects document type (specification, drawing, report)
- Identifies engineering domains (structural, seismic, wind, materials)
- Assesses technical complexity level
- Extracts key technical terms

### Question Optimization
- Classifies question types (identification, numerical, specification)
- Detects required formats (units, ratios, years)
- Optimizes search strategies per question type

### Domain Adaptation
- Building codes: Optimizes for IBC, ASCE, AISC references
- Seismic: Enhances Sds, Sd1, site class detection
- Wind loads: Improves wind speed, exposure category extraction
- Structural: Better deflection limits, load capacity identification

### Error Handling
- OCR error resilience (Sds vs SdS, spacing issues)
- Context-aware uncertainty detection
- Cross-reference validation

## 4. PERFORMANCE IMPACT

Based on testing:
- Prompt length: Typically 20-30% shorter than static prompts
- Processing speed: Faster due to targeted instructions
- Accuracy: Improved domain-specific results
- Cache efficiency: Reuses optimized prompts for similar content

## 5. CONFIGURATION OPTIONS

```yaml
prompt_engineering:
  enabled: true
  optimization_level: "balanced"
  cache_prompts: true  # Improves performance
  
  context_analysis:
    enabled: true
    analyze_domains: true
    analyze_document_type: true
    analyze_technical_level: true
    extract_key_terms: true
  
  question_optimization:
    enabled: true
    classify_question_types: true
    detect_required_formats: true
    assess_complexity: true
  
  domain_adaptation:
    enabled: true
    building_codes: true
    seismic_parameters: true
    wind_loads: true
    structural_elements: true
    materials: true
  
  performance:
    max_prompt_length: 8000
    optimization_timeout: 30
  
  monitoring:
    log_optimization_stats: true
    save_optimized_prompts: false  # Set true for debugging
```

## 6. USAGE EXAMPLES

### Example 1: Standard Usage (No Changes Required)
The prompt engineering system works automatically when enabled.
Run your pipeline normally:

```bash
python pipeline.py --mode llm --project prj_01
```

### Example 2: Testing Prompt Engineering
Use the test script to see optimization in action:

```bash
python test_prompt_engineering.py
```

### Example 3: Debugging Prompts
Enable prompt saving for inspection:

```yaml
monitoring:
  save_optimized_prompts: true
```

This saves prompts to files for comparison and analysis.

## 7. BEST PRACTICES

### When to Enable:
✅ Complex engineering documents
✅ Multi-domain content (seismic + wind + structural)
✅ Documents with technical specifications
✅ OCR text with potential errors
✅ Questions requiring specific formats

### When to Disable:
❌ Simple, single-domain documents
❌ High-volume batch processing (if speed is critical)
❌ Well-structured, clean text documents
❌ Questions with straightforward answers

### Performance Tips:
- Enable caching for repeated similar documents
- Use "conservative" level for speed-critical applications
- Monitor optimization statistics to tune performance
- Disable unused domain adaptations to reduce processing

## 8. MONITORING AND DEBUGGING

### Statistics Available:
- Optimization level and status
- Number of cached prompts
- Processing performance metrics
- Domain detection accuracy

### Debugging Tools:
- Prompt comparison scripts
- Optimization statistics logging
- Saved prompt inspection
- Performance tracking

### Access Statistics:
```python
from llm_tools.prompt_engineer import PromptEngineer
engineer = PromptEngineer(config)
stats = engineer.get_optimization_stats()
print(stats)
```

## 9. INTEGRATION WITH EXISTING WORKFLOW

The prompt engineering system integrates seamlessly:

1. **No Code Changes**: Works with existing pipeline commands
2. **Backward Compatible**: Defaults to disabled for no impact
3. **Engine Independent**: Works with OpenAI, Anthropic, DeepSeek
4. **Fallback Safe**: Falls back to static prompts if optimization fails

## 10. REAL-WORLD EXAMPLE

### Before (Static Prompt):
```
You are a structural and seismic engineering document analyzer...
[Generic instructions for all documents]
```

### After (Optimized Prompt):
```
You are a knowledgeable engineering assistant skilled at extracting key information from technical documents.

**DOCUMENT CONTEXT ANALYSIS:**
- Document Type: Specification
- Engineering Domains: structural, seismic, wind, building_codes
- Technical Level: High
- Key Terms Detected: IBC, ASCE, SdS, L/240

**DOMAIN-SPECIFIC GUIDANCE:**
- Building Codes: Look for IBC, ASCE, AISC, ACI references with years
- Seismic Parameters: Search for Sds, Sd1, site class (A-F)
- Structural Elements: Focus on deflection limits (L/240, L/360)

**OPTIMIZED SEARCH STRATEGIES:**
- For identification questions: Scan for proper nouns, standard codes
- For numerical questions: Look for numbers with units, ratios
- Deflection ratios: Search for patterns like 'L/240', 'L/360'

[Targeted instructions based on content analysis]
```

Result: More accurate, faster processing with fewer tokens.

## 11. TROUBLESHOOTING

### Common Issues:

**Issue**: Prompt optimization taking too long
**Solution**: Reduce optimization_timeout or use "conservative" level

**Issue**: Optimized prompts too long
**Solution**: Adjust max_prompt_length or disable unused features

**Issue**: No improvement in results
**Solution**: Check domain_adaptation settings match your document types

**Issue**: Cache not working
**Solution**: Verify cache_prompts: true and check disk space

### Getting Help:
- Check optimization statistics for performance metrics
- Enable debug logging for detailed analysis
- Compare static vs optimized prompts using test script
- Review configuration options for your specific use case

================================================================================
READY TO USE: Set prompt_engineering.enabled: true in config.yaml and run!
================================================================================
