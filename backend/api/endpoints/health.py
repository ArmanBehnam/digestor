"""Health check endpoint with DB and Redis connectivity verification."""

import os
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check that verifies DB and Redis are reachable."""
    checks = {}

    # Check database connectivity
    try:
        from db.session import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)[:100]}"

    # Check Redis connectivity + queue status
    try:
        import redis as redis_lib
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        r.ping()
        # Check RQ queue length and job registry sizes
        queue_len = r.llen("rq:queue:default")
        workers = r.smembers("rq:workers")
        # Check failed/started job registries
        failed_count = r.zcard("rq:failed:default")
        started_count = r.zcard("rq:wip:default")
        scheduled_count = r.zcard("rq:scheduled:default")
        # Get first few job IDs in queue
        queue_jobs = [j.decode() if isinstance(j, bytes) else j
                      for j in r.lrange("rq:queue:default", 0, 5)]
        r.close()
        checks["redis"] = "healthy"
        checks["rq_queue"] = {
            "queue_length": queue_len,
            "workers": len(workers),
            "failed_jobs": failed_count,
            "started_jobs": started_count,
            "scheduled_jobs": scheduled_count,
            "queue_head": queue_jobs,
        }
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)[:100]}"

    # Only check string values for health (skip rq_queue dict)
    all_healthy = all(
        v == "healthy" for v in checks.values() if isinstance(v, str)
    )

    response = {
        "status": "healthy" if all_healthy else "degraded",
        "version": "2.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    if not all_healthy:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response, status_code=503)

    return response


@router.get("/health/debug")
async def health_debug():
    """Debug endpoint to inspect RQ failed jobs. NOT used for ALB health checks."""
    try:
        import redis as redis_lib
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=5)
        r.ping()

        # Get last 5 failed job IDs and their error info
        failed_details = []
        failed_job_ids = r.zrange("rq:failed:default", -5, -1)
        for jid in failed_job_ids:
            try:
                jid_str = jid.decode("utf-8", errors="replace") if isinstance(jid, bytes) else str(jid)
                job_key = f"rq:job:{jid_str}"
                exc_info = r.hget(job_key, "exc_info")
                description = r.hget(job_key, "description")
                enqueued_at = r.hget(job_key, "enqueued_at")
                status = r.hget(job_key, "status")
                # Try zlib decompression for exc_info (RQ compresses it)
                error_text = None
                if exc_info:
                    try:
                        import zlib
                        error_text = zlib.decompress(exc_info).decode("utf-8", errors="replace")[:1500]
                    except Exception:
                        error_text = exc_info.decode("utf-8", errors="replace")[:1000]
                failed_details.append({
                    "job_id": jid_str,
                    "status": status.decode("utf-8", errors="replace") if status else None,
                    "description": (description.decode("utf-8", errors="replace")[:300]
                                    if description else None),
                    "error": error_text,
                    "enqueued_at": (enqueued_at.decode("utf-8", errors="replace")
                                    if enqueued_at else None),
                })
            except Exception as je:
                failed_details.append({"job_id": str(jid), "parse_error": str(je)[:200]})

        # Check specifically for the stuck job
        target_job = "168e71d9-f381-4434-822b-79149f01f03e"
        target_info = {}
        try:
            tj_key = f"rq:job:{target_job}"
            tj_exists = r.exists(tj_key)
            if tj_exists:
                tj_data = r.hgetall(tj_key)
                target_info = {
                    k.decode("utf-8", errors="replace"): v.decode("utf-8", errors="replace")[:500]
                    for k, v in tj_data.items()
                    if k.decode("utf-8", errors="replace") in (
                        "status", "description", "exc_info", "enqueued_at",
                        "origin", "started_at", "ended_at"
                    )
                }
                target_info["job_id"] = target_job
            else:
                target_info = {"job_id": target_job, "status": "not_found_in_redis"}
        except Exception as te:
            target_info = {"job_id": target_job, "error": str(te)[:200]}

        r.close()

        # Also check document statuses in DB for the stuck project
        db_info = {}
        try:
            from db.session import engine
            from sqlalchemy import text
            async with engine.connect() as conn:
                # Get document statuses
                result = await conn.execute(text(
                    "SELECT id, status, processing_path, job_id, "
                    "CASE WHEN results IS NOT NULL THEN 'has_results' ELSE 'no_results' END as has_results "
                    "FROM document_processing "
                    "WHERE project_id = '2d4cf784-12a4-4622-bffc-ddb88fc2a869' "
                    "ORDER BY created_at"
                ))
                docs = [dict(row._mapping) for row in result]
                # Check project snapshot
                result2 = await conn.execute(text(
                    "SELECT id, status, "
                    "CASE WHEN pending_snapshot_json IS NOT NULL THEN 'has_snapshot' ELSE 'no_snapshot' END as has_snapshot "
                    "FROM projects WHERE id = '2d4cf784-12a4-4622-bffc-ddb88fc2a869'"
                ))
                proj = [dict(row._mapping) for row in result2]
                db_info = {"documents": docs, "project": proj}
        except Exception as dbe:
            db_info = {"error": str(dbe)[:300]}

        return {
            "recent_failures": failed_details,
            "target_job": target_info,
            "db_state": db_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)[:500]}


@router.post("/health/fix-stuck")
async def fix_stuck_documents():
    """Fix documents stuck in 'queued' status when their project has results."""
    try:
        from db.session import engine
        from sqlalchemy import text
        async with engine.begin() as conn:
            # Find projects that have pending_snapshot_json but have
            # documents stuck in non-complete statuses
            result = await conn.execute(text("""
                UPDATE document_processing dp
                SET status = 'complete',
                    results = p.pending_snapshot_json
                FROM projects p
                WHERE dp.project_id = p.id
                  AND p.pending_snapshot_json IS NOT NULL
                  AND dp.status IN ('queued', 'ocr_processing', 'vlm_processing', 'failed', 'error')
                RETURNING dp.id, dp.project_id, dp.status
            """))
            fixed = [{"doc_id": str(row[0]), "project_id": str(row[1])}
                     for row in result]

        return {
            "fixed_documents": fixed,
            "count": len(fixed),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)[:500]}


@router.post("/health/requeue/{project_id}")
async def requeue_project(project_id: str):
    """Re-enqueue a failed project for worker processing."""
    try:
        import redis as redis_lib
        from rq import Queue

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        conn = redis_lib.from_url(redis_url, socket_connect_timeout=5)

        # Get document info from DB
        from db.session import engine
        from sqlalchemy import text
        async with engine.begin() as db_conn:
            result = await db_conn.execute(text(
                "SELECT id, s3_key, status FROM document_processing "
                "WHERE project_id = :pid ORDER BY created_at"
            ), {"pid": project_id})
            docs = [dict(row._mapping) for row in result]

        if not docs:
            return {"error": "No documents found for project"}

        # Collect S3 keys
        s3_keys = [d["s3_key"] for d in docs if d.get("s3_key")]
        if not s3_keys:
            return {"error": "No S3 keys found for documents"}

        primary_doc_id = str(docs[0]["id"])
        bucket = os.getenv("S3_BUCKET", os.getenv("S3_BUCKET_NAME", ""))

        # Enqueue the job
        queue = Queue("default", connection=conn)
        job = queue.enqueue(
            "tasks.process_pdfs",
            kwargs={
                "file_keys": s3_keys,
                "bucket": bucket,
                "project_id": project_id,
                "document_id": primary_doc_id,
            },
            job_timeout=3600,  # 60 minutes for large PDFs
            result_ttl=86400,
        )

        # Reset document statuses and clear stale results
        async with engine.begin() as db_conn:
            await db_conn.execute(text(
                "UPDATE document_processing "
                "SET status = 'queued', job_id = :jid, results = NULL, "
                "    confidence_avg = NULL, processing_time_ms = NULL, "
                "    processing_tier = NULL "
                "WHERE project_id = :pid"
            ), {"jid": job.id, "pid": project_id})

        conn.close()
        return {
            "job_id": job.id,
            "s3_keys": s3_keys,
            "primary_doc_id": primary_doc_id,
            "documents_updated": len(docs),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)[:500]}
