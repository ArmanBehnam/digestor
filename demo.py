# demo.py

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import tempfile
import os
import uuid
import asyncio
from datetime import datetime
import uvicorn
from pathlib import Path
import logging
import shutil
import subprocess
import sys
from typing import List, Dict, Any, Optional
import json
from fastapi.responses import FileResponse



current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "langchain_agents"))

try:
    from batch_workflow import process_directory
    from workflow import Talk2DrawingsWorkflow

    BATCH_AVAILABLE = True
    print("Successfully imported LangChain agents")
except ImportError as e:
    print(f"Warning: Could not import batch_workflow: {e}")
    try:
        import langchain_agents.batch_workflow as batch_workflow
        import langchain_agents.workflow as workflow

        process_directory = batch_workflow.process_directory
        Talk2DrawingsWorkflow = workflow.Talk2DrawingsWorkflow
        BATCH_AVAILABLE = True
        print("Successfully imported LangChain agents (alternative path)")
    except ImportError as e2:
        print(f"Warning: Alternative import also failed: {e2}")
        BATCH_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LangChain Multi-Agent PDF Processor",
    version="1.2.0",
    description="Process engineering PDFs using multi-agent LangChain system"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean_dataframes(obj):
    if isinstance(obj, dict):
        return {k: clean_dataframes(v) for k, v in obj.items()
                if k != 'results_dataframe' and 'DataFrame' not in str(type(v))}
    elif isinstance(obj, list):
        return [clean_dataframes(item) for item in obj]
    return obj

class ProcessingResponse(BaseModel):
    batch_id: str
    total_files: int
    successful: int
    failed: int
    processing_time: float
    results: List[Dict[str, Any]]
    output_directory: str


class FileStatus(BaseModel):
    filename: str
    status: str  # "processing", "completed", "failed"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


processing_results = {}


@app.get("/", response_class=HTMLResponse)
async def main_interface():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>LangChain Multi-Agent PDF Processor</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 20px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                background: white;
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            .header { 
                text-align: center; 
                background: linear-gradient(135deg, #2c3e50, #3498db); 
                color: white; 
                padding: 30px; 
                border-radius: 15px; 
                margin-bottom: 30px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            .header h1 { margin: 0; font-size: 2.5em; }
            .header p { margin: 10px 0 0 0; opacity: 0.9; }

            .upload-area { 
                border: 3px dashed #3498db; 
                padding: 40px; 
                text-align: center; 
                border-radius: 15px; 
                margin-bottom: 20px; 
                background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                transition: all 0.3s ease;
                cursor: pointer;
            }
            .upload-area:hover { 
                border-color: #2980b9; 
                background: linear-gradient(135deg, #e9ecef, #dee2e6);
                transform: translateY(-2px);
            }
            .upload-area.dragover {
                border-color: #27ae60;
                background: linear-gradient(135deg, #d4edda, #c3e6cb);
            }

            .file-list { 
                background: #f8f9fa; 
                border-radius: 10px; 
                padding: 20px; 
                margin: 20px 0; 
            }
            .file-item { 
                background: white; 
                padding: 15px; 
                margin: 10px 0; 
                border-radius: 8px; 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                transition: all 0.3s ease;
            }
            .file-item:hover { transform: translateX(5px); }

            .btn { 
                background: linear-gradient(135deg, #3498db, #2980b9); 
                color: white; 
                border: none; 
                padding: 12px 24px; 
                border-radius: 8px; 
                cursor: pointer; 
                font-size: 16px; 
                margin: 5px; 
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
            }
            .btn:hover { 
                background: linear-gradient(135deg, #2980b9, #1f618d); 
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4);
            }
            .btn:disabled { 
                background: linear-gradient(135deg, #95a5a6, #7f8c8d); 
                cursor: not-allowed; 
                transform: none;
                box-shadow: none;
            }
            .btn-danger { 
                background: linear-gradient(135deg, #e74c3c, #c0392b); 
                box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3);
            }
            .btn-success { 
                background: linear-gradient(135deg, #27ae60, #229954); 
                box-shadow: 0 4px 15px rgba(39, 174, 96, 0.3);
            }

            .progress-container { 
                background: #f8f9fa; 
                border-radius: 10px; 
                padding: 20px; 
                margin: 20px 0; 
                display: none; 
            }
            .progress-bar { 
                width: 100%; 
                height: 8px; 
                background: #ecf0f1; 
                border-radius: 4px; 
                overflow: hidden; 
                margin: 10px 0; 
            }
            .progress-fill { 
                height: 100%; 
                background: linear-gradient(135deg, #3498db, #2980b9); 
                transition: width 0.3s ease; 
                width: 0%;
            }

            .results { 
                background: #f8f9fa; 
                padding: 25px; 
                border-radius: 15px; 
                margin-top: 20px; 
                display: none;
            }
            .result-card { 
                background: white; 
                margin: 15px 0; 
                padding: 25px; 
                border-radius: 12px; 
                border-left: 5px solid #3498db; 
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                transition: all 0.3s ease;
            }
            .result-card:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }

            .status-success { color: #27ae60; font-weight: bold; }
            .status-failed { color: #e74c3c; font-weight: bold; }
            .status-processing { color: #f39c12; font-weight: bold; }

            .stats { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px; 
            }
            .stat-card { 
                background: white; 
                padding: 25px; 
                border-radius: 12px; 
                text-align: center; 
                box-shadow: 0 5px 15px rgba(0,0,0,0.1); 
                transition: all 0.3s ease;
            }
            .stat-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(0,0,0,0.15); }
            .stat-number { font-size: 2em; font-weight: bold; color: #3498db; margin: 0; }
            .stat-label { color: #7f8c8d; margin: 10px 0 0 0; }

            .alert { 
                padding: 15px; 
                border-radius: 8px; 
                margin: 15px 0; 
                border-left: 4px solid;
            }
            .alert-success { background: #d4edda; border-color: #27ae60; color: #155724; }
            .alert-error { background: #f8d7da; border-color: #e74c3c; color: #721c24; }
            .alert-warning { background: #fff3cd; border-color: #f39c12; color: #856404; }

            .feature-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .feature-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                text-align: center;
            }
            .feature-icon { font-size: 2em; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Demo Multi-Agent PDF Processor</h1>
                <p>OCR → Content Extraction → Pattern Recognition → Engineering Q&A → Deflection Defaults</p>
            </div>

            <div class="stats" id="stats">
                <div class="stat-card">
                    <div class="stat-number" id="totalProcessed">0</div>
                    <div class="stat-label">Documents Processed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="totalQuestions">25</div>
                    <div class="stat-label">Engineering Questions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="successRate">0%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="avgTime">0s</div>
                    <div class="stat-label">Avg Processing Time</div>
                </div>
            </div>

            <div class="feature-grid">
                <div class="feature-card">
                    <div class="feature-icon">A</div>
                    <h4>OCR Agent</h4>
                    <p>Multi-engine OCR with AWS Textract, Azure, Claude, Tesseract fallback</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">B</div>
                    <h4>QA Agent</h4>
                    <p>25 engineering questions across building codes, loads, materials</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">C</div>
                    <h4>Orchestrator</h4>
                    <p>LangChain workflow coordination with intelligent error handling</p>
                </div>
            </div>

            <div class="upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click()">
                <h3>Upload Engineering PDFs</h3>
                <p>Click to select files or drag and drop PDFs here</p>
                <input type="file" id="fileInput" accept=".pdf" multiple style="display: none;">
                <p><small>Supported: Construction specs, building plans, structural drawings</small></p>
            </div>

            <div class="file-list" id="fileList" style="display: none;">
                <h4>Selected Files:</h4>
                <div id="fileItems"></div>
                <button class="btn btn-success" onclick="processFiles()" id="processBtn">Process with Multi-Agent System</button>
                <button class="btn btn-danger" onclick="clearFiles()">Clear Files</button>
            </div>

            <div class="progress-container" id="progressContainer">
                <h4>Processing Documents</h4>
                <p id="progressText">Initializing multi-agent workflow</p>
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <div id="progressDetails"></div>
            </div>

            <div class="results" id="results"></div>
        </div>

        <script>
            let selectedFiles = [];
            let processingResults = {};

            // File upload handling
            document.getElementById('fileInput').addEventListener('change', function(e) {
                const files = Array.from(e.target.files);
                selectedFiles = [...selectedFiles, ...files];
                updateFileList();
            });

            // Drag and drop handling
            const uploadArea = document.getElementById('uploadArea');

            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');

                const files = Array.from(e.dataTransfer.files).filter(file => 
                    file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
                );

                if (files.length === 0) {
                    alert('Please select only PDF files');
                    return;
                }

                selectedFiles = [...selectedFiles, ...files];
                updateFileList();
            });

            function updateFileList() {
                const fileList = document.getElementById('fileList');
                const fileItems = document.getElementById('fileItems');

                if (selectedFiles.length === 0) {
                    fileList.style.display = 'none';
                    return;
                }

                fileList.style.display = 'block';
                fileItems.innerHTML = selectedFiles.map((file, index) => `
                    <div class="file-item">
                        <span>${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)</span>
                        <button class="btn btn-danger" onclick="removeFile(${index})">Remove</button>
                    </div>
                `).join('');
            }

            function removeFile(index) {
                selectedFiles.splice(index, 1);
                updateFileList();
            }

            function clearFiles() {
                selectedFiles = [];
                document.getElementById('fileInput').value = '';
                updateFileList();
                document.getElementById('results').style.display = 'none';
                document.getElementById('progressContainer').style.display = 'none';
            }

            async function processFiles() {
                if (selectedFiles.length === 0) {
                    alert('Please select at least one PDF file');
                    return;
                }

                // Show progress
                document.getElementById('progressContainer').style.display = 'block';
                document.getElementById('results').style.display = 'none';
                document.getElementById('processBtn').disabled = true;

                const formData = new FormData();
                selectedFiles.forEach(file => {
                    formData.append('files', file);
                });

                try {
                    updateProgress(10, 'Uploading files...');

                    const response = await fetch('/process-batch/', {
                        method: 'POST',
                        body: formData
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }

                    updateProgress(100, 'Processing complete!');
                    const result = await response.json();

                    displayResults(result);
                    updateStats();

                } catch (error) {
                    console.error('Processing error:', error);
                    document.getElementById('results').innerHTML = `
                        <div class="alert alert-error">
                            <h4>Processing Failed</h4>
                            <p>${error.message}</p>
                            <p>Please check that the batch_workflow.py system is properly configured.</p>
                        </div>
                    `;
                    document.getElementById('results').style.display = 'block';
                } finally {
                    document.getElementById('processBtn').disabled = false;
                    setTimeout(() => {
                        document.getElementById('progressContainer').style.display = 'none';
                    }, 2000);
                }
            }

            function updateProgress(percent, text) {
                document.getElementById('progressFill').style.width = percent + '%';
                document.getElementById('progressText').textContent = text;
            }

            function displayResults(data) {
                const resultsDiv = document.getElementById('results');
            
                let html = `
                    <h3>Multi-Agent Processing Complete</h3>
                    <div class="alert alert-success">
                        Processed ${data.successful}/${data.total_files} files successfully in ${data.processing_time.toFixed(1)}s
                        <br>Results saved to: ${data.output_directory}
                    </div>
                `;
            
                if (data.results && data.results.length > 0) {
                    html += '<h4>Individual Results:</h4>';
            
                    data.results.forEach(result => {
                        const statusClass = result.success ? 'status-success' : 'status-failed';
                        const statusIcon = result.success ? 'Yes' : 'No';
            
                        html += `
                            <div class="result-card">
                                <h5>${statusIcon} ${result.filename || 'Unknown file'}</h5>
                                <p class="${statusClass}">Status: ${result.success ? 'Success' : 'Failed'}</p>
            
                                ${result.success ? `
                                    <div class="download-buttons" style="margin: 15px 0;">
                                        <a href="${result.csv_download}" class="btn btn-success" download>Download CSV</a>
                                        <a href="${result.json_download}" class="btn btn-success" download>Download JSON</a>
                                    </div>
                                ` : ''}
            
                                ${result.questions_answered ? `
                                    <p><strong>Questions Answered:</strong> ${result.questions_answered}/25</p>
                                ` : ''}
            
                                ${result.defaults_applied ? `
                                    <p><strong>Deflection Defaults:</strong> ${result.defaults_applied} applied</p>
                                ` : ''}
            
                                ${result.json_content ? `
                                    <details style="margin-top: 15px;">
                                        <summary style="cursor: pointer; font-weight: bold;">View JSON Results</summary>
                                        <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 400px; font-size: 12px;">${JSON.stringify(result.json_content, null, 2)}</pre>
                                    </details>
                                ` : ''}
            
                                ${result.error ? `
                                    <p class="status-failed"><strong>Error:</strong> ${result.error}</p>
                                ` : ''}
                            </div>
                        `;
                    });
                }
            
                resultsDiv.innerHTML = html;
                resultsDiv.style.display = 'block';
            }

            function updateStats() {
                const results = Object.values(processingResults);
                if (results.length === 0) return;

                const totalProcessed = results.reduce((sum, r) => sum + (r.total_files || 0), 0);
                const totalSuccessful = results.reduce((sum, r) => sum + (r.successful || 0), 0);
                const avgTime = results.reduce((sum, r) => sum + (r.processing_time || 0), 0) / results.length;
                const successRate = totalProcessed > 0 ? (totalSuccessful / totalProcessed * 100) : 0;

                document.getElementById('totalProcessed').textContent = totalProcessed;
                document.getElementById('successRate').textContent = successRate.toFixed(1) + '%';
                document.getElementById('avgTime').textContent = avgTime.toFixed(1) + 's';
            }

            // Initialize stats
            updateStats();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/process-batch/", response_model=ProcessingResponse)
async def process_batch_documents(files: List[UploadFile] = File(...)):

    if not BATCH_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Batch processing not available. Please ensure agentic/batch_workflow.py is accessible."
        )

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")

    # Validate files
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")

    batch_id = str(uuid.uuid4())
    start_time = datetime.now()

    temp_dir = Path(tempfile.mkdtemp(prefix=f"batch_{batch_id}_"))

    try:
        saved_files = []
        for file in files:
            file_path = temp_dir / file.filename
            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)
            saved_files.append(file_path)

        logger.info(f"Saved {len(saved_files)} files to {temp_dir}")

        logger.info("Starting batch processing with LangChain agents")

        try:
            results = await process_directory(str(temp_dir), prompt_engineering=True)

            processing_time = (datetime.now() - start_time).total_seconds()
            serializable_results = [clean_dataframes(result) for result in results]
            total_files = len(files)
            successful = len([r for r in serializable_results if r.get('success', False)])
            failed = total_files - successful
            enhanced_results = []
            for result in serializable_results:
                if result.get('success') and 'result' in result:
                    final_results = result['result'].get('final_results', {})
                    result['csv_download'] = f"/download-csv/{batch_id}"
                    result['json_download'] = f"/download-json/{batch_id}"
                    json_path = final_results.get('json_path')
                    if json_path and Path(json_path).exists():
                        try:
                            with open(json_path, 'r') as f:
                                result['json_content'] = json.load(f)
                        except Exception:
                            pass

                enhanced_results.append(result)
            processing_results[batch_id] = {
                'results': results,
                'temp_dir': str(temp_dir),
                'output_dir': f"batch_results_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'timestamp': datetime.now()}
            response = ProcessingResponse(
                batch_id=batch_id,
                total_files=total_files,
                successful=successful,
                failed=failed,
                processing_time=processing_time,
                results=enhanced_results,
                output_directory=str(temp_dir)
            )

            logger.info(f"Batch processing complete: {successful}/{total_files} successful")
            return response

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")

    finally:
        asyncio.create_task(cleanup_temp_dir(temp_dir, delay=300))  # 5 minutes


async def cleanup_temp_dir(temp_dir: Path, delay: int = 300):
    await asyncio.sleep(delay)
    try:
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to clean up {temp_dir}: {e}")


@app.get("/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    if batch_id not in processing_results:
        raise HTTPException(status_code=404, detail="Batch ID not found")

    return JSONResponse(content={
        "batch_id": batch_id,
        "status": "completed",
        "results": processing_results[batch_id]['results'],
        "timestamp": processing_results[batch_id]['timestamp'].isoformat()
    })


@app.get("/health")
async def health_check():
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "batch_workflow": "available" if BATCH_AVAILABLE else "unavailable",
            "langchain_agents": "available" if BATCH_AVAILABLE else "unavailable"
        },
        "features": [
            "Multi-agent LangChain processing",
            "OCR with hierarchical fallback",
            "25 engineering questions",
            "Deflection defaults application",
            "CSV and JSON output"
        ]
    })


@app.get("/download-csv/{batch_id}")
async def download_csv(batch_id: str):
    if batch_id not in processing_results:
        raise HTTPException(status_code=404, detail="Batch ID not found")

    # Find CSV file from results
    results = processing_results[batch_id]['results']
    for result in results:
        if result.get('success') and 'result' in result:
            final_results = result['result'].get('final_results', {})
            csv_path = final_results.get('csv_path')
            if csv_path and Path(csv_path).exists():
                return FileResponse(
                    path=csv_path,
                    filename=Path(csv_path).name,
                    media_type='text/csv'
                )

    raise HTTPException(status_code=404, detail="CSV file not found")


@app.get("/download-json/{batch_id}")
async def download_json(batch_id: str):
    if batch_id not in processing_results:
        raise HTTPException(status_code=404, detail="Batch ID not found")

    # Find JSON file from results
    results = processing_results[batch_id]['results']
    for result in results:
        if result.get('success') and 'result' in result:
            final_results = result['result'].get('final_results', {})
            json_path = final_results.get('json_path')
            if json_path and Path(json_path).exists():
                return FileResponse(
                    path=json_path,
                    filename=Path(json_path).name,
                    media_type='application/json'
                )

    raise HTTPException(status_code=404, detail="JSON file not found")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LangChain Multi-Agent PDF Processor Web Interface")
    parser.add_argument("--port", type=int, default=8080, help="Port to run the server on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the server to")
    args = parser.parse_args()

    print(f"Starting LangChain Multi-Agent PDF Processor")
    print(f"Web interface: http://{args.host}:{args.port}")
    print(f"API docs: http://{args.host}:{args.port}/docs")

    if not BATCH_AVAILABLE:
        print("WARNING: batch_workflow.py not found - processing will be limited")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=False
    )