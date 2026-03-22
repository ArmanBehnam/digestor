# tasks.py
import os
import boto3
import asyncio
import gc
from pathlib import Path
import fitz
import json
import re
from datetime import datetime
from core.batch_processor import merge_json_results, chunk_pages_by_tokens, generate_final_results_merged
from agents.validation import ValidationAgent
from rq import get_current_job
from redis import Redis
from PIL import Image
import io


def _resolve_database_url():
    """Resolve DATABASE_URL the same way db/session.py does:
    1. Explicit DATABASE_URL env var
    2. RDS_SECRET_ARN + RDS_ENDPOINT + RDS_DB_NAME (Secrets Manager)
    3. Fallback to empty string (skip DB updates)
    """
    url = os.getenv("DATABASE_URL", "")
    if url and "PLACEHOLDER" not in url:
        # Ensure sync driver for psycopg2
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        if not url.startswith("postgresql://"):
            url = "postgresql://" + url.split("://", 1)[-1]
        return url

    secret_arn = os.getenv("RDS_SECRET_ARN")
    endpoint = os.getenv("RDS_ENDPOINT")
    db_name = os.getenv("RDS_DB_NAME")

    if secret_arn and endpoint and db_name:
        try:
            client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])
            username = secret.get("username", "digestor")
            password = secret.get("password", "")
            built = f"postgresql://{username}:{password}@{endpoint}:5432/{db_name}"
            print(f"[DB] Resolved DATABASE_URL from Secrets Manager (endpoint={endpoint}, db={db_name})")
            return built
        except Exception as e:
            print(f"[DB] Failed to resolve DATABASE_URL from Secrets Manager: {e}")

    return ""


# Resolve once at import time so all functions can use it
_DATABASE_URL = _resolve_database_url()


def _get_fallback_status(document_id):
    """Check if a document already has PDF.js results saved (fallback path).
    If it does, return 'complete' so those results are shown instead of an error.
    Otherwise return 'failed'."""
    if not document_id:
        return "failed"
    db_url = _DATABASE_URL
    if not db_url:
        return "failed"
    sync_url = db_url
    try:
        import psycopg2
        conn = psycopg2.connect(sync_url)
        cur = conn.cursor()
        cur.execute("SELECT results FROM document_processing WHERE id = %s", (document_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            print(f"[DB] Document {document_id} has existing results, reverting to 'complete'")
            return "complete"
    except Exception as e:
        print(f"[DB] Failed to check fallback status: {e}")
    return "failed"


def update_document_status(document_id, status, results=None, confidence_avg=None,
                           processing_time_ms=None, processing_tier=None, project_id=None):
    """Update DocumentProcessing record in RDS (synchronous, for worker use).
    Also updates project.pending_snapshot_json and ALL project docs when results are final.
    This handles combined multi-document jobs where one job processes all project PDFs."""
    if not document_id:
        print("[DB] No document_id provided, skipping DB status update")
        return
    db_url = _DATABASE_URL
    if not db_url:
        print("[DB] No DATABASE_URL set, skipping DB status update")
        return
    sync_url = db_url
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(sync_url)
        cur = conn.cursor()
        if results is not None:
            # Update the primary document
            cur.execute(
                """UPDATE document_processing
                   SET status = %s, results = %s, confidence_avg = %s,
                       processing_time_ms = %s, processing_tier = %s
                   WHERE id = %s::uuid""",
                (status, psycopg2.extras.Json(results), confidence_avg,
                 processing_time_ms, processing_tier, document_id)
            )
            print(f"[DB] Primary doc update: {cur.rowcount} row(s)")
            # Commit primary update immediately so it's not lost
            # if subsequent updates fail
            conn.commit()

            if project_id and status == "complete":
                results_json = psycopg2.extras.Json(results)
                # Update project snapshot
                try:
                    cur.execute(
                        """UPDATE projects SET pending_snapshot_json = %s
                           WHERE id = %s::uuid""",
                        (results_json, project_id)
                    )
                    print(f"[DB] Project snapshot update: {cur.rowcount} row(s)")
                    conn.commit()
                except Exception as pe:
                    print(f"[DB] Failed to update project snapshot: {pe}")
                    conn.rollback()

                # Also update ALL other documents in this project to "complete"
                # so the frontend doesn't show "processing" for the non-primary docs
                try:
                    cur.execute(
                        """UPDATE document_processing
                           SET status = %s, results = %s, confidence_avg = %s,
                               processing_time_ms = %s, processing_tier = %s
                           WHERE project_id = %s::uuid AND id != %s::uuid""",
                        (status, results_json, confidence_avg,
                         processing_time_ms, processing_tier, project_id, document_id)
                    )
                    updated = cur.rowcount
                    print(f"[DB] Other project docs update: {updated} row(s) "
                          f"(project={project_id}, excluding={document_id})")
                    conn.commit()
                    if updated == 0:
                        print("[DB] WARNING: 0 other docs updated! Check project_id match.")
                except Exception as pe:
                    print(f"[DB] Failed to update other project documents: {pe}")
                    conn.rollback()
        else:
            cur.execute(
                "UPDATE document_processing SET status = %s WHERE id = %s::uuid",
                (status, document_id)
            )
            conn.commit()
        cur.close()
        conn.close()
        print(f"[DB] Updated document {document_id} status to '{status}'"
              + (f" (tier {processing_tier})" if processing_tier else ""))
    except Exception as e:
        print(f"[DB] Failed to update document status: {e}")
        import traceback
        traceback.print_exc()


QUESTION_METADATA = [
    {"category": "Building Code", "question": "What is the building code and its version year?"},
    {"category": "Building Code", "question": "Is ASCE 7-XX referred?"},
    {"category": "Deflection Criteria", "question": "What are the exterior wall deflection limits?"},
    {"category": "Deflection Criteria", "question": "What is the interior wall deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the floor joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the roof rafter framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "What is the ceiling joist framing deflection limit?"},
    {"category": "Deflection Criteria", "question": "Maximum primary structure vertical deflection due to live load?"},
    {"category": "Wind Load Criteria", "question": "What is the basic wind speed (Vult)?"},
    {"category": "Wind Load Criteria", "question": "What is the building risk category?"},
    {"category": "Wind Load Criteria", "question": "What is the exposure category?"},
    {"category": "Wind Load Criteria", "question": "What is the internal pressure coefficient (GCpi)?"},
    {"category": "Gravity Loads", "question": "What is the roof live load?"},
    {"category": "Gravity Loads", "question": "What is the roof dead load?"},
    {"category": "Snow Load Criteria", "question": "What is the ground snow load (Pg)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow load importance factor (Is)?"},
    {"category": "Snow Load Criteria", "question": "What is the snow exposure factor (Ce)?"},
    {"category": "Snow Load Criteria", "question": "What is the thermal factor (Ct)?"},
    {"category": "Snow Load Criteria", "question": "What is the flat roof snow load (Pf)?"},
    {"category": "Seismic Load Criteria", "question": "What is the seismic design category?"},
    {"category": "Seismic Load Criteria", "question": "What is the seismic importance factor (Ie)?"},
    {"category": "Seismic Load Criteria", "question": "What is the component importance factor (Ip)?"},
    {"category": "Seismic Load Criteria", "question": "What is the site class?"},
    {"category": "Seismic Load Criteria", "question": "What is the SDS value?"},
    {"category": "Seismic Load Criteria", "question": "What is the SD1 value?"},
]


def convert_worker_results_to_analysis_format(worker_results):
    """Convert worker flat results into AnalysisResult[] format for frontend.

    Input: list of dicts with Question_Number, Question, Main_Answer, OCR_Confidence, Page, etc.
    Output: list of dicts with category, question, pairs: [{answer, reference, confidence, feedback}]
    """
    if not worker_results:
        return []

    analysis_results = []
    # Index worker results by question number (1-based)
    results_by_num = {}
    for r in worker_results:
        qnum = r.get("Question_Number")
        if qnum is not None:
            results_by_num[int(qnum)] = r

    for i, meta in enumerate(QUESTION_METADATA):
        qnum = i + 1
        worker_r = results_by_num.get(qnum, {})

        answer = worker_r.get("Main_Answer", "Not Found")
        answer_str = str(answer).strip() if answer else "Not Found"
        confidence = worker_r.get("OCR_Confidence", 0)
        if isinstance(confidence, (int, float)) and confidence > 1:
            confidence = confidence / 100.0
        page = worker_r.get("Page", "N/A")

        # Fix reference mapping: if answer is "Not Found", reference should also be "Not Found"
        # regardless of what page the LLM returned. Conversely, if we have a real answer,
        # preserve the page reference.
        answer_is_missing = answer_str.lower() in (
            "not found", "n/a", "na", "none", "not specified",
            "not available", "not provided", "unknown", "",
        )
        if answer_is_missing:
            reference = "Not Found"
            answer_str = "Not Found"
        elif page and str(page) not in ("N/A", "n/a", "None", "none", "unknown", ""):
            reference = f"Page {page}" if not str(page).startswith("Page") else str(page)
        else:
            reference = "Not Found"

        analysis_results.append({
            "category": meta["category"],
            "question": meta["question"],
            "pairs": [{
                "answer": answer_str,
                "reference": reference,
                "confidence": float(confidence) if confidence else 0.0,
                "feedback": "up",
            }],
        })

    return analysis_results


def update_progress(redis_conn, job_id, stage, progress, step_description):
    progress_key = f"job:{job_id}:progress"
    log_key = f"job:{job_id}:logs"
    progress_data = {'stage': stage, 'progress': progress, 'current_step': step_description,
                     'timestamp': datetime.now().isoformat()}
    redis_conn.set(progress_key, json.dumps(progress_data), ex=3600)
    redis_conn.rpush(log_key, f"[{stage.upper()}] {step_description}")
    redis_conn.expire(log_key, 3600)
    print(f"[PROGRESS] {progress}% - {step_description}")


def run_vlm_processing(file_keys, bucket, missing_questions, s3_client, work_dir):
    """Tier 3: Convert PDF pages to images, send to Gemini VLM with missing questions only."""
    from llm.vlm_engine import VLMEngine

    vlm = VLMEngine()
    if not vlm.is_available:
        raise RuntimeError("VLM engine not available (no GOOGLE_API_KEY)")

    # Convert all PDF pages to images
    page_images = []
    for key in file_keys:
        local_path = f"{work_dir}/{Path(key).name}"
        if not Path(local_path).exists():
            s3_client.download_file(bucket, key, local_path)

        doc = fitz.open(local_path)
        for page_num in range(len(doc)):
            pix = doc[page_num].get_pixmap(dpi=150)
            page_images.append({
                "page_number": page_num + 1,
                "image_bytes": pix.tobytes("png"),
                "width": pix.width,
                "height": pix.height,
            })
        doc.close()

    print(f"[VLM] Sending {len(page_images)} page images + {len(missing_questions)} questions to Gemini")
    return vlm.answer_questions_from_images(page_images, missing_questions)


def enrich_with_bboxes(analysis_results, all_ocr_results):
    """Map answer text to OCR bounding boxes, normalize coordinates to 0-1 range."""
    # Build flat list of page_results from all OCR data
    page_results = []
    for ocr in all_ocr_results:
        ocr_data = ocr.get("ocr_data", {})
        for page in ocr_data.get("page_results", []):
            page_results.append(page)

    if not page_results:
        return analysis_results

    from llm.coordinate_mapper import CoordinateMapper
    mapper = CoordinateMapper()

    enriched_count = 0
    for r in analysis_results:
        for pair in r.get("pairs", []):
            if pair.get("bbox"):  # Already has bbox (e.g., from VLM)
                continue
            answer = pair.get("answer", "")
            ref = pair.get("reference", "")

            # Parse page number from reference
            match = re.search(r'Page\s+(\d+)', ref, re.IGNORECASE)
            page_num = int(match.group(1)) if match else None

            coord = mapper.find_answer_coordinates(answer, page_results, page_num)
            if coord:
                bbox = coord["bounding_box"]
                # Get page dimensions for normalization
                pg = next((p for p in page_results
                           if p.get("page_number") == page_num), None)
                pw = pg.get("page_width", 1000) if pg else 1000
                ph = pg.get("page_height", 1000) if pg else 1000
                pair["bbox"] = {
                    "x": round(bbox["x"] / pw, 4),
                    "y": round(bbox["y"] / ph, 4),
                    "width": round(bbox["width"] / pw, 4),
                    "height": round(bbox["height"] / ph, 4),
                }
                enriched_count += 1

    print(f"[BBOX] Enriched {enriched_count} answers with bounding box coordinates")
    return analysis_results


def process_pdfs(file_keys, bucket, project_id=None, document_id=None):
    job = get_current_job()
    job_id = job.id if job else "unknown"
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    if redis_url.startswith('rediss://'):
        redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)
    else:
        redis_conn = Redis.from_url(redis_url)

    # --- Check if agentic mode is enabled ---
    try:
        from config.config_loader import CONFIG
        agentic_enabled = CONFIG.get('agentic', {}).get('enabled', False) if CONFIG else False
    except Exception:
        agentic_enabled = False

    if agentic_enabled:
        return _process_pdfs_agentic(
            file_keys, bucket, project_id, document_id, job_id, redis_conn)

    try:
        update_progress(redis_conn, job_id, "initializing", 5, "Starting PDF processing")
        s3 = boto3.client('s3', aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                          aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                          region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
        work_dir = "/tmp/work"
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        for old_file in Path(work_dir).glob("*"):
            try:
                old_file.unlink()
            except:
                pass

        # Copy deflection_defaults.csv to work_dir
        import shutil
        defaults_file = Path(__file__).parent / 'config' / 'deflection_defaults.csv'
        if defaults_file.exists():
            shutil.copy(defaults_file, Path(work_dir) / 'deflection_defaults.csv')
            print("Copied deflection_defaults.csv to work directory")
        update_progress(redis_conn, job_id, "setup", 10, f"Processing {len(file_keys)} PDF(s)")
        print(f"Project ID: {project_id or 'No project'}")
        print(f"Files: {len(file_keys)}")
        project_version = "N/A"
        if project_id:
            try:
                metadata_key = f"projects/{project_id}/metadata.json"
                response = s3.get_object(Bucket=bucket, Key=metadata_key)
                project_meta = json.loads(response['Body'].read().decode('utf-8'))
                project_version = project_meta.get('version', '1.0')
            except:
                pass
        processing_metadata = {'timestamp': datetime.now().isoformat(),
                               'source_files': [Path(key).name for key in file_keys], 'file_count': len(file_keys),
                               'project_id': project_id, 'project_version': project_version}
        all_ocr_results = []
        for pdf_index, key in enumerate(file_keys):
            pdf_progress = 15 + (pdf_index * 15 // len(file_keys))
            update_progress(redis_conn, job_id, "downloading", pdf_progress, f"Downloading {Path(key).name}")
            print(f"\nProcessing PDF {pdf_index + 1}/{len(file_keys)}: {Path(key).name}")
            local_path = f"{work_dir}/{Path(key).name}"
            # Check local storage first (development mode)
            local_source = Path(os.getenv("LOCAL_UPLOAD_DIR", "/app/local_uploads")) / key
            if local_source.exists():
                import shutil as _shutil
                _shutil.copy(str(local_source), local_path)
            else:
                s3.download_file(bucket, key, local_path)
            pdf_file = Path(local_path)
            doc = fitz.open(pdf_file)
            page_count = len(doc)
            doc.close()

            BATCH_SIZE = 3
            print(f"PDF has {page_count} pages, processing in batches of {BATCH_SIZE}")
            from core.workflow import Talk2DrawingsWorkflow
            workflow = Talk2DrawingsWorkflow()
            pdf_batches = []
            total_batches = (page_count + BATCH_SIZE - 1) // BATCH_SIZE
            for batch_start in range(0, page_count, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, page_count)
                batch_num = batch_start // BATCH_SIZE + 1
                batch_progress = 30 + (batch_num * 20 // total_batches)
                update_progress(redis_conn, job_id, "ocr", batch_progress,
                                f"OCR batch {batch_num}/{total_batches} - Pages {batch_start + 1}-{batch_end}")
                print(f"\nOCR Batch {batch_num}: Pages {batch_start + 1}-{batch_end}")
                doc = fitz.open(pdf_file)
                batch_pdf = fitz.open()
                for i in range(batch_start, batch_end):
                    batch_pdf.insert_pdf(doc, from_page=i, to_page=i)
                batch_path = f"{work_dir}/batch_{pdf_index}_{batch_start}.pdf"
                batch_pdf.save(batch_path)
                doc.close()
                batch_pdf.close()
                gc.collect()
                if Path(batch_path).stat().st_size > 80_000_000:
                    original_size = Path(batch_path).stat().st_size / 1_000_000
                    print(f"Batch {batch_num} is {original_size:.1f}MB, compressing")
                    doc = fitz.open(batch_path)
                    compressed = fitz.open()
                    for page in doc:
                        pix = page.get_pixmap(dpi=96)
                        img_data = pix.tobytes("ppm")
                        img = Image.frombytes("RGB", (pix.width, pix.height), img_data)
                        img_io = io.BytesIO()
                        img.save(img_io, format='JPEG', quality=70, optimize=True)
                        img_bytes = img_io.getvalue()
                        compressed.new_page(width=pix.width, height=pix.height)
                        compressed[-1].insert_image(compressed[-1].rect, stream=img_bytes)
                    compressed.save(batch_path, garbage=4, deflate=True, clean=True)
                    doc.close()
                    compressed.close()
                    new_size = Path(batch_path).stat().st_size / 1_000_000
                    reduction = ((original_size - new_size) / original_size) * 100
                    print(f"Compressed: {original_size:.1f}MB → {new_size:.1f}MB ({reduction:.1f}% reduction)")
                    if new_size > 95:
                        print(f"batch {batch_num} still too large ({new_size:.1f}MB), skipping")
                        Path(batch_path).unlink()
                        continue
                    gc.collect()
                try:
                    ocr_result = asyncio.run(workflow.orchestrator.ocr_agent.safe_process(batch_path))
                    if ocr_result['success']:
                        # Only keep essential data: page_results for merging
                        slim_result = {
                            'page_results': ocr_result.get('page_results', []),
                            'success': True,
                        }
                        pdf_batches.append({'batch_num': batch_num, 'pages': batch_start + 1, 'pages_end': batch_end,
                                            'ocr_data': slim_result,
                                            'page_count': len(slim_result.get('page_results', []))})
                        del ocr_result
                        print(f"Batch {batch_num} OCR complete")
                except Exception as e:
                    print(f"Batch {batch_num} failed, skipping: {e}")
                finally:
                    try:
                        Path(batch_path).unlink()
                    except:
                        pass
                    gc.collect()
                # Log memory every 5 batches for large PDFs
                if batch_num % 5 == 0 or batch_num == total_batches:
                    try:
                        import psutil
                        mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
                        print(f"Memory at batch {batch_num}/{total_batches}: {mem_mb:.1f} MB")
                    except:
                        pass
            if pdf_batches:
                print(f"\nMerging {len(pdf_batches)} batches for {Path(key).name}")
                merged_pdf_ocr = merge_batches_for_pdf(pdf_batches, Path(key).name)
                pdf_ocr_path = f"{work_dir}/{Path(key).stem}_ocr_result.json"
                with open(pdf_ocr_path, 'w') as f:
                    json.dump(merged_pdf_ocr, f, indent=2, ensure_ascii=False)
                print(f"Saved merged OCR JSON: {pdf_ocr_path}")
                for batch_json in Path(work_dir).glob(f"batch_{pdf_index}_*_ocr_result.json"):
                    batch_json.unlink()
                    print(f"Deleted batch JSON: {batch_json.name}")
                all_ocr_results.append(
                    {'source_pdf': Path(key).name, 'pdf_path': str(pdf_file), 'ocr_data': merged_pdf_ocr,
                     'page_count': sum(b['page_count'] for b in pdf_batches),
                     'filtered_pages': merged_pdf_ocr.get('filtered_pages', {})})
                gc.collect()
                try:
                    import psutil
                    process = psutil.Process()
                    mem_mb = process.memory_info().rss / 1024 / 1024
                    print(f"Memory after PDF {pdf_index + 1}: {mem_mb:.1f} MB")
                except:
                    pass

        if not all_ocr_results:
            raise Exception("No PDFs were successfully processed")

        update_progress(redis_conn, job_id, "merging", 55, "Merging all OCR results")
        print("\nMerging OCR results from all PDFs")
        merged_data = merge_json_results(all_ocr_results)

        update_progress(redis_conn, job_id, "chunking", 60, "Preparing LLM chunks")
        print("\nPreparing chunks for LLM")
        all_filtered_pages = merged_data.get('filtered_pages', {}).get('matching_pages', [])
        chunks = chunk_pages_by_tokens(all_filtered_pages, max_tokens=20000)
        print(f"Split into {len(chunks)} chunks for parallel LLM processing")

        all_qa_results = {}

        async def process_single_chunk(chunk_index, chunk):
            chunk_workflow = Talk2DrawingsWorkflow()
            chunk_data = {'filtered_pages': {'matching_pages': chunk}}
            print(f"Starting chunk {chunk_index + 1}/{len(chunks)} ({len(chunk)} pages)")
            result = await chunk_workflow.orchestrator.qa_agent.safe_process(chunk_data)
            print(f"Completed chunk {chunk_index + 1}/{len(chunks)}")
            return result

        async def process_all_chunks():
            tasks = [process_single_chunk(i, chunk) for i, chunk in enumerate(chunks)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        update_progress(redis_conn, job_id, "llm", 65, f"Running LLM on {len(chunks)} chunks")
        print("\nProcessing all chunks in parallel")
        chunk_results = asyncio.run(process_all_chunks())
        for i, chunk_result in enumerate(chunk_results):
            if isinstance(chunk_result, Exception):
                print(f"Chunk {i + 1} error: {chunk_result}")
                continue

            if chunk_result and chunk_result.get('success'):
                for qid, answer in chunk_result['qa_results'].items():
                    if not isinstance(answer, dict):
                        print(f"WARNING: Answer for {qid} is {type(answer)}, converting to dict")
                        answer = {'answer': str(answer), 'page': 'N/A', 'confidence': 0, 'source_pdf': 'unknown'}
                    if qid not in all_qa_results:
                        all_qa_results[qid] = answer
                    else:
                        old_answer = all_qa_results[qid].get('answer', 'Not Found')
                        new_answer = answer.get('answer', 'Not Found')
                        if old_answer == 'Not Found' and new_answer != 'Not Found':
                            all_qa_results[qid] = answer
                        elif new_answer != 'Not Found':
                            old_conf = all_qa_results[qid].get('confidence', 0)
                            new_conf = answer.get('confidence', 0)
                            if new_conf > old_conf:
                                all_qa_results[qid] = answer

        qa_result = {'success': len(all_qa_results) > 0, 'qa_results': all_qa_results}
        print(f"\nLLM complete: {len(all_qa_results)} questions answered")
        gc.collect()
        try:
            import psutil
            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024
            print(f"Memory after LLM: {mem_mb:.1f} MB")
        except:
            pass

        update_progress(redis_conn, job_id, "generating", 75, "Generating final results")
        print("\nGenerating Results")
        final_results = asyncio.run(generate_final_results_merged(workflow, merged_data, qa_result, work_dir,
                                                                  {'prompt_engineering': True,
                                                                   'metadata': processing_metadata}, all_ocr_results))

        update_progress(redis_conn, job_id, "validation", 80, "Validating results")
        print("\nValidation")
        validation_agent = ValidationAgent(workflow.config)
        if validation_agent.is_available:
            validation_result = asyncio.run(validation_agent.safe_process({
                'results_dataframe': final_results['results_dataframe']}))
            if validation_result['success']:
                validated_csv = f"{work_dir}/validated.csv"
                validation_result['validated_dataframe'].to_csv(validated_csv, index=False)
        update_progress(redis_conn, job_id, "uploading", 90, "Uploading results to S3")
        print("\nUploading to S3")
        try:
            uploaded_files = upload_results(s3, bucket, work_dir, project_id, processing_metadata)
            print(f"[OK] Upload complete: {len(uploaded_files)} items")
        except Exception as upload_error:
            print(f"[ERROR] S3 Upload Error: {upload_error}")
            import traceback
            traceback.print_exc()
            uploaded_files = {'error': str(upload_error)}

        # Read results JSON before cleanup and convert to AnalysisResult format for DB
        analysis_results = []
        avg_confidence = None
        json_files = list(Path(work_dir).glob("pipeline_results_merged_*.json"))
        if json_files:
            try:
                with open(json_files[0], 'r', encoding='utf-8') as rf:
                    merged_data = json.load(rf)
                worker_results = merged_data.get('results', [])
                analysis_results = convert_worker_results_to_analysis_format(worker_results)
                # Calculate average confidence
                confs = [p['pairs'][0]['confidence'] for p in analysis_results if p.get('pairs') and p['pairs'][0].get('confidence')]
                avg_confidence = sum(confs) / len(confs) if confs else None
                print(f"[DB] Converted {len(worker_results)} worker results to {len(analysis_results)} AnalysisResult entries")
            except Exception as conv_err:
                print(f"[DB] Warning: Could not convert results for DB: {conv_err}")

        # --- TIER 2 QUALITY CHECK: Should we escalate to VLM (Tier 3)? ---
        processing_tier = 2
        if analysis_results:
            from services.fallback_detector import FallbackDetector, NOT_FOUND_THRESHOLD
            tier2_detector = FallbackDetector()
            tier2_answers = tier2_detector._extract_answers(analysis_results)
            tier2_not_found = sum(1 for a in tier2_answers if tier2_detector._is_not_found(a["answer"]))
            print(f"[TIER2] Quality check: {tier2_not_found} answers missing (threshold: {NOT_FOUND_THRESHOLD})")

            if tier2_not_found > NOT_FOUND_THRESHOLD:
                # Identify which questions are still missing
                missing_questions = []
                for i, r in enumerate(analysis_results):
                    if r.get("pairs") and tier2_detector._is_not_found(r["pairs"][0].get("answer", "")):
                        missing_questions.append({
                            "index": i,
                            "category": r["category"],
                            "question": r["question"],
                        })

                update_progress(redis_conn, job_id, "vlm", 85,
                                f"Running VLM on {len(missing_questions)} unanswered questions")
                print(f"\n[TIER3] Escalating to VLM: {len(missing_questions)} missing questions")

                # --- TIER 3: VLM PROCESSING ---
                try:
                    vlm_answers = run_vlm_processing(
                        file_keys, bucket, missing_questions, s3, work_dir
                    )
                    # Merge VLM answers into analysis_results
                    vlm_filled = 0
                    for va in vlm_answers:
                        idx = va["index"]
                        if idx < len(analysis_results) and analysis_results[idx].get("pairs"):
                            analysis_results[idx]["pairs"][0]["answer"] = va["answer"]
                            analysis_results[idx]["pairs"][0]["confidence"] = va["confidence"]
                            analysis_results[idx]["pairs"][0]["reference"] = va.get("reference", "Not Found")
                            if va.get("bbox"):
                                analysis_results[idx]["pairs"][0]["bbox"] = va["bbox"]
                            vlm_filled += 1
                    processing_tier = 3
                    print(f"[TIER3] VLM filled {vlm_filled}/{len(missing_questions)} missing answers")
                except Exception as vlm_err:
                    print(f"[TIER3] VLM failed, keeping Tier 2 results: {vlm_err}")
                    import traceback
                    traceback.print_exc()

        # --- BBOX COORDINATE MAPPING ---
        if analysis_results and all_ocr_results:
            analysis_results = enrich_with_bboxes(analysis_results, all_ocr_results)

        # Recalculate confidence after potential VLM merge
        if analysis_results:
            confs = [p['pairs'][0]['confidence'] for p in analysis_results
                     if p.get('pairs') and p['pairs'][0].get('confidence')]
            avg_confidence = sum(confs) / len(confs) if confs else avg_confidence

        for f in Path(work_dir).glob("*"):
            try:
                f.unlink()
            except:
                pass
        gc.collect()
        update_progress(redis_conn, job_id, "complete", 100, "Processing complete!")
        # Update RDS document status to 'complete' with results
        update_document_status(document_id, "complete",
                               results=analysis_results or None,
                               confidence_avg=avg_confidence,
                               processing_tier=processing_tier,
                               project_id=project_id)
        return {'success': True, 'batches_processed': len(all_ocr_results), 'bucket': bucket, 'project_id': project_id,
                **uploaded_files}
    except Exception as e:
        update_progress(redis_conn, job_id, "failed", 0, f"Error: {str(e)}")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        # Update RDS document status
        # If the document already has PDF.js results (fallback path), revert to
        # "complete" so the user still sees those results rather than an error
        fallback_status = _get_fallback_status(document_id)
        update_document_status(document_id, fallback_status)
        return {'success': False, 'error': str(e)}


def _process_pdfs_agentic(file_keys, bucket, project_id, document_id, job_id, redis_conn):
    """Process PDFs using the LangGraph agentic pipeline with 3-tier fallback.

    Flow: Tier 1 (PDF.js+LLM) -> Tier 2 (OCR+LLM) -> Tier 3 (VLM/Gemini)
    The graph handles routing automatically based on quality thresholds.
    """
    try:
        update_progress(redis_conn, job_id, "initializing", 5, "Starting agentic PDF processing")

        work_dir = "/tmp/work"
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        for old_file in Path(work_dir).glob("*"):
            try:
                old_file.unlink()
            except:
                pass

        import shutil
        defaults_file = Path(__file__).parent / 'config' / 'deflection_defaults.csv'
        if defaults_file.exists():
            shutil.copy(defaults_file, Path(work_dir) / 'deflection_defaults.csv')

        # Download PDFs (local storage first, then S3)
        update_progress(redis_conn, job_id, "setup", 10, f"Downloading {len(file_keys)} PDF(s)")
        local_upload_dir = Path(os.getenv("LOCAL_UPLOAD_DIR", "/app/local_uploads"))
        local_paths = []
        for key in file_keys:
            local_path = f"{work_dir}/{Path(key).name}"
            # Check local storage first (development mode)
            local_source = local_upload_dir / key
            if local_source.exists():
                shutil.copy(str(local_source), local_path)
                print(f"[DOWNLOAD] Using local file: {local_source}")
            else:
                # Fall back to S3
                s3 = boto3.client('s3', aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                                  aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                                  region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
                s3.download_file(bucket, key, local_path)
                print(f"[DOWNLOAD] Downloaded from S3: {key}")
            local_paths.append(local_path)

        # Process each PDF through the agentic graph
        update_progress(redis_conn, job_id, "agentic", 15,
                        "Running agentic pipeline (Tier 1: PDF text extraction)")
        from core.workflow import Talk2DrawingsWorkflow
        workflow = Talk2DrawingsWorkflow()

        all_results = []
        for i, pdf_path in enumerate(local_paths):
            progress = 15 + (i * 70 // len(local_paths))
            update_progress(redis_conn, job_id, "agentic", progress,
                            f"Processing {Path(pdf_path).name} ({i+1}/{len(local_paths)})")

            print(f"\n{'='*60}")
            print(f"[AGENTIC] Processing: {Path(pdf_path).name}")
            print(f"{'='*60}")

            result = asyncio.run(workflow.process_document(pdf_path))

            if result.get('success'):
                all_results.append(result)
                # Log decisions
                decisions = result.get('decisions_log', [])
                for td in decisions:
                    if 'Tier' in td.get('decision', '') or 'tier' in td.get('decision', '').lower() \
                       or td.get('decision_type') in ('escalation_triggered', 'quality_threshold_met'):
                        print(f"  [DECISION] {td.get('agent', '?')}: {td.get('decision', '')}")
            else:
                print(f"  [ERROR] Pipeline failed: {result.get('error', 'unknown')}")

        if not all_results:
            raise Exception("No PDFs were successfully processed by the agentic pipeline")

        # Extract analysis_results from the agentic pipeline output
        analysis_results = []
        processing_tier = 1
        for result in all_results:
            ar = result.get('analysis_results', [])
            if ar:
                if isinstance(ar[0], dict) and 'Question_Number' in ar[0]:
                    analysis_results = convert_worker_results_to_analysis_format(ar)
                else:
                    analysis_results = ar
                # Get the tier from the pipeline result
                final = result.get('final_results', {})
                processing_tier = final.get('processing_tier',
                                  result.get('processing_tier', 1))
                break

        # Calculate average confidence
        avg_confidence = None
        if analysis_results:
            confs = []
            for p in analysis_results:
                if p.get('pairs') and p['pairs'][0].get('confidence'):
                    conf = p['pairs'][0]['confidence']
                    if isinstance(conf, (int, float)):
                        confs.append(conf)
            avg_confidence = sum(confs) / len(confs) if confs else None

        print(f"\n[AGENTIC] Results: {len(analysis_results)} answers, "
              f"avg_confidence={avg_confidence}")

        # Cleanup
        for f in Path(work_dir).glob("*"):
            try:
                f.unlink()
            except:
                pass

        update_progress(redis_conn, job_id, "complete", 100,
                        f"Agentic processing complete!")
        update_document_status(document_id, "complete",
                               results=analysis_results or None,
                               confidence_avg=avg_confidence,
                               processing_tier=processing_tier,
                               project_id=project_id)
        return {'success': True, 'mode': 'agentic', 'project_id': project_id}

    except Exception as e:
        update_progress(redis_conn, job_id, "failed", 0, f"Agentic error: {str(e)}")
        print(f"Agentic pipeline error: {e}")
        import traceback
        traceback.print_exc()
        fallback_status = _get_fallback_status(document_id)
        update_document_status(document_id, fallback_status)
        return {'success': False, 'error': str(e)}


def merge_batches_for_pdf(batches, pdf_name):
    all_pages = []
    all_filtered = []
    page_offset = 0
    total_confidence = 0
    total_pages = 0
    for batch in batches:
        ocr_data = batch['ocr_data']
        batch_conf = ocr_data.get('document_info', {}).get('confidence', 0.9)
        batch_pages = batch['page_count']
        total_confidence += batch_conf * batch_pages
        total_pages += batch_pages
        pages = ocr_data.get('page_results', [])
        for page in pages:
            page['page_number'] = page['page_number'] + page_offset
        all_pages.extend(pages)
        filtered = ocr_data.get('filtered_pages', {}).get('matching_pages', [])
        for page in filtered:
            page['page_number'] = page['page_number'] + page_offset
        all_filtered.extend(filtered)
        page_offset += batch_pages
    avg_confidence = total_confidence / total_pages if total_pages > 0 else 0.9

    return {'document_info': {'filename': pdf_name, 'total_pages': total_pages,
                              'processing_time': sum(b['ocr_data'].get('processing_time', 0) for b in batches),
                              'confidence': avg_confidence}, 'filtered_pages_only': all_filtered,
            'page_results': all_pages,
            'filtered_pages': {'matching_pages': all_filtered, 'total_matching_pages': len(all_filtered)}}


def merge_ocr_chunks(chunk_files):
    """Merge multiple OCR JSON files from split PDFs into one"""
    all_pages = []
    all_filtered = []
    total_confidence = 0
    total_pages = 0
    filename = None

    # Sort by part number
    def get_part_num(path):
        match = re.search(r'_part(\d+)_', path.stem)
        return int(match.group(1)) if match else 0

    sorted_files = sorted(chunk_files, key=get_part_num)

    for file_path in sorted_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)

        if filename is None:
            # Use first file's name (remove chunk suffix)
            filename = re.sub(r'_part\d+_pages\d+-\d+', '', file_path.stem.replace('_ocr_result', ''))

        doc_info = ocr_data.get('document_info', {})
        pages = ocr_data.get('page_results', [])
        filtered = ocr_data.get('filtered_pages', {}).get('matching_pages', [])

        # Accumulate confidence
        page_count = doc_info.get('total_pages', len(pages))
        confidence = doc_info.get('confidence', 0.9)
        total_confidence += confidence * page_count
        total_pages += page_count

        all_pages.extend(pages)
        all_filtered.extend(filtered)

    avg_confidence = total_confidence / total_pages if total_pages > 0 else 0.9

    return {
        'document_info': {
            'filename': f"{filename}.pdf",
            'total_pages': total_pages,
            'confidence': avg_confidence,
            'merged_from_chunks': len(sorted_files)
        },
        'page_results': all_pages,
        'filtered_pages': {
            'matching_pages': all_filtered,
            'total_matching_pages': len(all_filtered)
        }
    }


def upload_results(s3, bucket, work_dir, project_id=None, metadata=None):
    timestamp = metadata.get('timestamp', '').replace(':', '-').split('.')[0] if metadata else ''
    version = metadata.get('project_version', '') if metadata else ''

    # Get project name from S3 metadata
    project_name = None
    if project_id:
        try:
            metadata_key = f"projects/{project_id}/metadata.json"
            response = s3.get_object(Bucket=bucket, Key=metadata_key)
            project_meta = json.loads(response['Body'].read().decode('utf-8'))
            project_name = project_meta.get('name', project_id)
            print(f"Upload: project='{project_name}', version={version}")
        except Exception:
            project_name = project_id
            print("Upload: Using project_id as name")

    uploaded = {}
    if project_id:
        base_path = f"projects/{project_id}/results"
    else:
        base_path = "results"

    # Upload validated CSV with project name
    val_files = list(Path(work_dir).glob("*validated.csv"))
    for file_path in val_files:
        if project_name:
            key = f"{base_path}/{project_name}.csv"
        else:
            key = f"{base_path}/validated_v{version}_{timestamp}.csv"
        print(f"Uploading: {key}")
        s3.upload_file(str(file_path), bucket, key)
        uploaded['validated_csv_s3_key'] = key

    # Upload merged JSON with project name
    json_files = list(Path(work_dir).glob("pipeline_results_merged_*.json"))
    for file_path in json_files:
        if project_name:
            key = f"{base_path}/{project_name}.json"
        else:
            key = f"{base_path}/merged_result_v{version}_{timestamp}.json"
        print(f"Uploading: {key}")
        s3.upload_file(str(file_path), bucket, key)
        uploaded['merged_json_s3_key'] = key

    # Process OCR files - merge chunks from the same original PDF
    ocr_files = list(Path(work_dir).glob("*_ocr_result.json"))

    # Group OCR files by original PDF name (detect and merge chunks)
    ocr_groups = {}
    chunk_pattern = re.compile(r'^(.+)_part\d+_pages\d+-\d+$')

    for file_path in ocr_files:
        pdf_name = file_path.stem.replace('_ocr_result', '')

        # Check if this is a chunk (e.g., "filename_part1_pages1-50")
        match = chunk_pattern.match(pdf_name)
        if match:
            original_name = match.group(1)
            if original_name not in ocr_groups:
                ocr_groups[original_name] = []
            ocr_groups[original_name].append(file_path)
        else:
            # Not a chunk, treat as standalone
            if pdf_name not in ocr_groups:
                ocr_groups[pdf_name] = []
            ocr_groups[pdf_name].append(file_path)

    # Merge and upload OCR files
    for original_name, chunk_files in ocr_groups.items():
        if len(chunk_files) == 1:
            # Single file, upload as-is
            file_path = chunk_files[0]
            key = f"{base_path}/ocr/{original_name}.json"
            print(f"Uploading: {key}")
            s3.upload_file(str(file_path), bucket, key)
        else:
            # Multiple chunks, merge them
            print(f"Merging {len(chunk_files)} OCR chunks for '{original_name}'")
            merged_ocr = merge_ocr_chunks(chunk_files)

            # Save merged file
            merged_path = Path(work_dir) / f"{original_name}_merged_ocr.json"
            with open(merged_path, 'w', encoding='utf-8') as f:
                json.dump(merged_ocr, f, indent=2, ensure_ascii=False)

            # Upload merged file
            key = f"{base_path}/ocr/{original_name}.json"
            print(f"Uploading merged: {key}")
            s3.upload_file(str(merged_path), bucket, key)

        if 'ocr_json_keys' not in uploaded:
            uploaded['ocr_json_keys'] = []
        uploaded['ocr_json_keys'].append(f"{base_path}/ocr/{original_name}.json")

    print(f"Uploaded files: {list(uploaded.keys())}")
    return uploaded
