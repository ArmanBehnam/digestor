"""
WebSocket endpoints for real-time progress tracking.
Uses Redis Pub/Sub to bridge worker progress → client WebSocket.
"""

import os
import json
import asyncio
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import redis.asyncio as aioredis

logger = structlog.get_logger()
router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class ConnectionManager:
    """Manages WebSocket connections and bridges Redis pub/sub messages."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._redis: aioredis.Redis = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[job_id] = websocket
        logger.info("websocket_connected", job_id=job_id)

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]
            logger.info("websocket_disconnected", job_id=job_id)

    async def send_progress(self, job_id: str, data: dict):
        ws = self.active_connections.get(job_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(job_id)


manager = ConnectionManager()


@router.websocket("/progress/{job_id}")
async def progress_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time job progress.

    The worker publishes progress to Redis channel `job:{job_id}:progress`.
    This endpoint subscribes and forwards messages to the connected client.

    Message format:
    {
        "type": "progress" | "log" | "status" | "complete" | "error",
        "progress": 0-100,
        "message": "Human-readable status message",
        "stage": "ocr" | "llm" | "validation" | "complete",
        "data": {} // optional extra data
    }
    """
    await manager.connect(job_id, websocket)

    redis = await manager._get_redis()
    pubsub = redis.pubsub()
    channel = f"job:{job_id}:progress"

    try:
        await pubsub.subscribe(channel)
        logger.info("redis_subscribed", channel=channel)

        # Send initial status from Redis if available
        current_progress = await redis.get(f"job:{job_id}:current_progress")
        if current_progress:
            await websocket.send_json(json.loads(current_progress))

        while True:
            # Check for Redis pub/sub messages
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )

            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)

                    # If processing is complete, close gracefully
                    if data.get("type") in ("complete", "error"):
                        await websocket.send_json({"type": "close"})
                        break
                except json.JSONDecodeError:
                    logger.warning("invalid_redis_message", channel=channel)

            # Also check for client messages (heartbeat, cancel)
            try:
                client_msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.1
                )
                if client_msg == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info("client_disconnected", job_id=job_id)
    except Exception as e:
        logger.error("websocket_error", job_id=job_id, error=str(e))
    finally:
        await pubsub.unsubscribe(channel)
        manager.disconnect(job_id)


async def publish_progress(job_id: str, progress_data: dict):
    """
    Publish progress from worker to Redis (called by tasks.py).
    This bridges the worker process → WebSocket client.
    """
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        channel = f"job:{job_id}:progress"
        data_str = json.dumps(progress_data)

        # Publish to channel for WebSocket subscribers
        await redis.publish(channel, data_str)

        # Also store current state for late-joining clients
        await redis.set(
            f"job:{job_id}:current_progress", data_str, ex=7200  # 2 hour expiry
        )
    finally:
        await redis.close()
