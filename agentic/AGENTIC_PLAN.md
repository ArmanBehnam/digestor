# Agentic Architecture Plan for Digestor v2.0

## What Does "Agentic" Mean?

**Agentic AI** means the system makes autonomous decisions about *how* to process a document, rather than following a fixed pipeline. Instead of "run OCR then run LLM then validate", an agentic system has intelligent agents that:

1. **Observe** - Assess the input (document quality, type, complexity)
2. **Decide** - Choose the best tool/strategy for the situation
3. **Act** - Execute with the chosen approach
4. **Reflect** - Evaluate results and decide if retry/fallback is needed
5. **Communicate** - Agents share context and coordinate with each other

### Current State vs. Agentic State

| Aspect | Current (Pipeline) | Future (Agentic) |
|--------|-------------------|-------------------|
| **Flow** | Fixed: OCR -> QA -> Validate | Dynamic: Orchestrator decides per-document |
| **OCR choice** | Always AWS Textract | Agent picks best OCR based on document type |
| **LLM choice** | Try GPT-4o, fallback to Claude, then DeepSeek | Agent picks best LLM per question type |
| **Error handling** | Catch exceptions, return failure | Agent retries with different strategy |
| **Quality check** | Post-hoc validation only | Continuous: agent checks after each step |
| **Multi-doc** | Process sequentially, merge results | Agents parallelize and cross-reference |

---

## Architecture Overview

```
                    +---------------------------+
                    |   Supervisor Agent (NEW)   |
                    |   - Monitors all agents    |
                    |   - Makes routing decisions|
                    |   - Handles escalation     |
                    +-------------|-------------+
                                  |
                    +-------------|-------------+
                    |   Orchestrator Agent       |
                    |   - Coordinates workflow   |
                    |   - Maintains state        |
                    |   - Manages agent comms    |
                    +------|-----------|--------+
                           |           |
              +------------|--+   +----|----------+
              |  OCR Agent    |   |  QA Agent     |
              |  - Doc assess |   |  - Question   |
              |  - Engine pick|   |    routing    |
              |  - Quality    |   |  - LLM pick   |
              |    check      |   |  - Confidence |
              +------|--------+   +-----|--------+
                     |                   |
              +------|--------+   +-----|--------+
              | Validation    |   | Memory Agent |
              | Agent         |   | (NEW)        |
              | - Rule check  |   | - Learn from |
              | - Conflict    |   |   past docs  |
              |   detection   |   | - Cache good |
              +---------------+   |   patterns   |
                                  +--------------+
```

---

## Phase 1: Make Existing Agents Truly Autonomous

### 1.1 - Add Decision-Making to OCR Agent

**Current**: Always calls `Phase1PDFProcessor` with the same settings.

**Agentic**: The OCR Agent should:
- **Assess document first**: Is it scanned? Digital? Mixed? What DPI?
- **Pick the best OCR engine**: Textract for tables, Claude Vision for handwritten, Tesseract for simple text
- **Check quality after OCR**: If confidence < 70%, automatically retry with a different engine
- **Report back**: Tell the Orchestrator what it found, what worked, what didn't

```python
class AgenticOCRAgent(Talk2DrawingsBaseAgent):
    """OCR Agent that makes autonomous decisions about extraction strategy."""

    async def process(self, pdf_path, context=None):
        # Step 1: OBSERVE - Assess the document
        doc_assessment = await self.assess_document(pdf_path)
        # Returns: {type: "scanned"|"digital"|"mixed", dpi: 300, pages: 12, has_tables: True}

        # Step 2: DECIDE - Pick strategy based on assessment
        strategy = self.decide_strategy(doc_assessment)
        # Returns: {primary_engine: "aws_textract", fallback: "claude_vision", enhance_images: True}

        # Step 3: ACT - Execute with chosen strategy
        result = await self.execute_ocr(pdf_path, strategy)

        # Step 4: REFLECT - Check quality, retry if needed
        if result['avg_confidence'] < 0.7:
            result = await self.retry_with_fallback(pdf_path, strategy, result)

        return result

    def decide_strategy(self, assessment):
        """Agent makes autonomous decision about OCR approach."""
        if assessment['type'] == 'scanned' and assessment['dpi'] < 200:
            return {'primary': 'claude_vision', 'enhance_images': True}
        elif assessment['has_tables']:
            return {'primary': 'aws_textract', 'extract_tables': True}
        elif assessment['type'] == 'digital':
            return {'primary': 'pdfjs', 'fast_mode': True}  # Skip heavy OCR
        else:
            return {'primary': 'aws_textract', 'fallback': 'azure'}
```

### 1.2 - Add Decision-Making to QA Agent

**Current**: Sends all text to one LLM with the same prompt.

**Agentic**: The QA Agent should:
- **Categorize questions**: Numeric extraction vs. code lookup vs. yes/no
- **Route to best LLM**: GPT-4o for table extraction, Claude for reasoning, DeepSeek for simple lookups
- **Evaluate confidence per answer**: Re-ask with different prompt if confidence is low
- **Cross-reference**: Check answers against each other for consistency

```python
class AgenticQAAgent(Talk2DrawingsBaseAgent):
    """QA Agent that routes questions to optimal LLM and validates answers."""

    QUESTION_CATEGORIES = {
        'numeric_extraction': [9, 13, 14, 15, 24, 25],   # Wind speed, loads, Sds, Sd1
        'code_lookup': [1, 2, 10, 11, 20, 23],            # Building code, risk category, site class
        'ratio_extraction': [3, 4, 5, 6, 7, 8],           # Deflection limits L/xxx
        'factor_extraction': [12, 16, 17, 18, 19, 21, 22] # Coefficients and factors
    }

    async def process(self, ocr_data, context=None):
        # Group questions by category
        for category, question_ids in self.QUESTION_CATEGORIES.items():
            # Pick best LLM for this category
            llm = self.select_llm_for_category(category)
            # Use category-specific prompt
            prompt = self.get_prompt_for_category(category)
            # Process batch
            answers = await llm.answer(ocr_data, question_ids, prompt)
            # Validate each answer
            for qid, answer in answers.items():
                if answer['confidence'] < 60:
                    # Retry with different LLM and more specific prompt
                    answer = await self.retry_single_question(qid, ocr_data)
        return all_answers
```

### 1.3 - Upgrade Validation Agent with Conflict Resolution

**Current**: Validates answers against static rules.

**Agentic**: The Validation Agent should:
- **Detect contradictions** between answers (e.g., Seismic Category D but Site Class A)
- **Flag suspicious patterns** (e.g., all "Not Found" for a section that clearly has data)
- **Suggest corrections** by re-querying specific pages
- **Learn from feedback**: Store correction patterns for future documents

---

## Phase 2: Add New Agents

### 2.1 - Supervisor Agent (NEW)

The Supervisor Agent sits above the Orchestrator and makes high-level decisions:

```python
class SupervisorAgent(Talk2DrawingsBaseAgent):
    """Top-level agent that monitors pipeline and makes routing decisions."""

    async def process(self, input_data, context=None):
        # Decide processing path
        if input_data.get('mode') == 'batch':
            return await self.batch_strategy(input_data)

        # Monitor agent performance
        while not self.is_complete():
            status = self.check_agent_status()
            if status['stuck_agent']:
                await self.intervene(status['stuck_agent'])
            if status['quality_below_threshold']:
                await self.escalate_to_human(status)

        return self.compile_final_results()
```

### 2.2 - Memory Agent (NEW)

Learns from past documents to improve future processing:

```python
class MemoryAgent(Talk2DrawingsBaseAgent):
    """Agent that maintains processing memory across documents."""

    async def process(self, input_data, context=None):
        # Check if we've seen similar documents before
        similar_docs = self.find_similar_documents(input_data['document_info'])

        if similar_docs:
            # Use past successful strategies
            return {
                'suggested_ocr_engine': similar_docs[0]['best_ocr'],
                'suggested_llm': similar_docs[0]['best_llm'],
                'known_answer_patterns': similar_docs[0]['patterns']
            }

        return {'no_prior_knowledge': True}

    def learn_from_result(self, document_info, processing_result):
        """Store what worked for this document type."""
        self.memory_store.save({
            'doc_fingerprint': self.fingerprint(document_info),
            'best_ocr': processing_result['ocr_engine_used'],
            'best_llm': processing_result['llm_used'],
            'patterns': processing_result['answer_patterns'],
            'success_rate': processing_result['confidence_avg']
        })
```

### 2.3 - Document Triage Agent (NEW)

Pre-processes documents before the main pipeline:

- Classifies document type (structural drawings, specs, general notes)
- Splits multi-section PDFs into logical chunks
- Identifies the most relevant pages upfront (smarter than keyword filtering)
- Estimates processing time and complexity

---

## Phase 3: Agent Communication Protocol

### 3.1 - Shared State / Blackboard Pattern

Agents communicate through a shared state object instead of direct calls:

```python
class AgentBlackboard:
    """Shared state that all agents can read/write."""

    def __init__(self):
        self.state = {
            'document_info': {},
            'ocr_results': {},
            'qa_results': {},
            'validation_results': {},
            'agent_messages': [],      # Agent-to-agent messages
            'decisions_log': [],       # Audit trail of agent decisions
            'quality_metrics': {},     # Running quality scores
        }

    def post_message(self, from_agent, to_agent, message_type, content):
        """Agent communication via blackboard."""
        self.state['agent_messages'].append({
            'from': from_agent,
            'to': to_agent,
            'type': message_type,  # 'request', 'result', 'alert', 'suggestion'
            'content': content,
            'timestamp': datetime.now()
        })

    def log_decision(self, agent_name, decision, reasoning):
        """Audit trail for agent decisions."""
        self.state['decisions_log'].append({
            'agent': agent_name,
            'decision': decision,
            'reasoning': reasoning,
            'timestamp': datetime.now()
        })
```

### 3.2 - Event-Driven Agent Triggers

Instead of sequential "Step 1, Step 2, Step 3", agents react to events:

```
EVENT: "document_uploaded"
  -> Document Triage Agent: classify, split, estimate
  -> Memory Agent: check for similar docs

EVENT: "triage_complete"
  -> OCR Agent: start extraction with suggested strategy
  -> Supervisor: log triage results

EVENT: "ocr_complete"
  -> QA Agent: start answering with OCR results
  -> Validation Agent: pre-check OCR quality

EVENT: "qa_complete"
  -> Validation Agent: validate all answers
  -> Memory Agent: store patterns

EVENT: "validation_complete"
  -> Supervisor: compile results, check overall quality
  -> Memory Agent: learn from this run
```

---

## Phase 4: Integration with LangChain/LangGraph

### Why LangChain?

The current `agentic/` code already imports from `langchain.schema`. To make it fully agentic:

1. **LangGraph** for stateful agent workflows with cycles (retry, re-route)
2. **LangChain Tools** to wrap OCR engines and LLMs as callable tools
3. **LangChain Memory** for conversation-like agent context

```python
from langgraph.graph import StateGraph, END

# Define the agentic workflow as a graph (not a pipeline)
workflow = StateGraph(ProcessingState)

workflow.add_node("triage", triage_agent)
workflow.add_node("ocr", ocr_agent)
workflow.add_node("qa", qa_agent)
workflow.add_node("validate", validation_agent)
workflow.add_node("supervisor", supervisor_agent)

# Conditional routing - this is what makes it AGENTIC
workflow.add_conditional_edges("triage", route_after_triage)
workflow.add_conditional_edges("ocr", route_after_ocr)       # May loop back to ocr with different engine
workflow.add_conditional_edges("qa", route_after_qa)          # May loop back to qa with different LLM
workflow.add_conditional_edges("validate", route_after_validate)  # May flag for re-processing

workflow.set_entry_point("triage")
app = workflow.compile()
```

---

## Phase 5: Implementation Roadmap

### Step 1 (Week 1-2): Refactor Current Agents
- [ ] Add `assess_document()` to OCR Agent
- [ ] Add `decide_strategy()` to OCR Agent
- [ ] Add question categorization to QA Agent
- [ ] Add per-question LLM routing to QA Agent
- [ ] Update imports to use `backend.ocr` and `backend.llm` properly

### Step 2 (Week 3-4): Add Communication Layer
- [ ] Implement AgentBlackboard
- [ ] Convert agents to read/write from blackboard
- [ ] Add decision logging/audit trail
- [ ] Add event-driven triggers

### Step 3 (Week 5-6): New Agents
- [ ] Implement Supervisor Agent
- [ ] Implement Memory Agent (Redis-backed)
- [ ] Implement Document Triage Agent
- [ ] Integration tests for multi-agent coordination

### Step 4 (Week 7-8): LangGraph Integration
- [ ] Install LangGraph, define StateGraph
- [ ] Wrap agents as LangGraph nodes
- [ ] Define conditional edges (retry/re-route logic)
- [ ] Integrate with existing FastAPI backend

### Step 5 (Week 9-10): Production Hardening
- [ ] Agent health monitoring dashboard
- [ ] Timeout and circuit-breaker patterns
- [ ] Cost tracking per agent/LLM call
- [ ] A/B testing: pipeline vs agentic mode

---

## Key Differences: Pipeline vs. Agentic

### Pipeline (Current)
```
PDF -> OCR (always Textract) -> LLM (try 3 in order) -> Validate -> Done
```
- Predictable, easy to debug
- No adaptation to document type
- Wastes resources on easy documents
- Can't recover from mid-pipeline failures intelligently

### Agentic (Future)
```
PDF -> Triage Agent assesses document
    -> OCR Agent picks best engine for this doc type
       -> If quality low: retry with different engine
    -> QA Agent routes questions to best LLM
       -> If confidence low: re-ask with better prompt
    -> Validation Agent checks consistency
       -> If conflicts: ask QA Agent to re-process specific questions
    -> Supervisor compiles results
    -> Memory Agent stores what worked
```
- Adapts to each document
- Self-healing: retries with different strategies
- Learns from past processing
- More efficient: skips heavy OCR for digital PDFs

---

## Files in This Directory

| File | Purpose | Status |
|------|---------|--------|
| `agents/base_agent.py` | Base agent class (abstract) | Keep as foundation |
| `agents/ocr_agent.py` | OCR Agent prototype | Upgrade with decision-making |
| `agents/qa_agent.py` | QA Agent prototype | Upgrade with question routing |
| `agents/validation_agent.py` | Validation Agent | Upgrade with conflict resolution |
| `agents/orchestrator_agent.py` | Orchestrator | Upgrade to event-driven |
| `workflow.py` | Single-doc workflow | Refactor to use LangGraph |
| `batch_workflow.py` | Batch processing | Merge into workflow.py |
| `merged_batch_workflow.py` | Multi-PDF merge + process | Merge into workflow.py |
| `fancy_vis.py` | Architecture visualization | Update for new architecture |
| `config.yaml` | Agent configuration | Keep and extend |
