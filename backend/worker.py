import os
import socket
import sys
import time
from pathlib import Path
from redis import Redis
from rq import SimpleWorker  # noqa: F401 - Worker, Queue used by RQ internals

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
from config.config_loader import CONFIG  # noqa: E402, F401 - triggers config loading
import tasks  # noqa: E402, F401 - registers RQ task handlers

# Aggressive TCP keepalive to prevent ElastiCache from closing idle BLPOP connections.
# Without these, the OS default keepalive interval (~2h) is too long and ElastiCache
# silently drops the connection, leaving the worker unable to dequeue jobs.
KEEPALIVE_OPTIONS = {
    socket.TCP_KEEPIDLE: 60,    # Start sending keepalives after 60s idle
    socket.TCP_KEEPINTVL: 15,   # Send a keepalive every 15s
    socket.TCP_KEEPCNT: 3,      # 3 failed keepalives = connection dead
}


def connect_to_redis(max_retries=5, retry_delay=2):
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    print(f"Connecting to Redis: {redis_url}")

    for attempt in range(1, max_retries + 1):
        try:
            if redis_url.startswith('rediss://'):
                conn = Redis.from_url(
                    redis_url,
                    ssl_cert_reqs=None,
                    socket_connect_timeout=30,
                    socket_timeout=600,
                    socket_keepalive=True,
                    socket_keepalive_options=KEEPALIVE_OPTIONS,
                    health_check_interval=30,
                    retry_on_timeout=True)
            else:
                conn = Redis.from_url(
                    redis_url,
                    socket_connect_timeout=30,
                    socket_timeout=600,
                    socket_keepalive=True,
                    socket_keepalive_options=KEEPALIVE_OPTIONS,
                    health_check_interval=30,
                    retry_on_timeout=True)

            conn.ping()
            print("Connected to Redis successfully")
            return conn

        except Exception as e:
            print(f"Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                print(f"  Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise


def run_worker():
    """Entry point called by entrypoint.py when PROCESS_TYPE=worker.

    Wraps the worker in a restart loop so it auto-recovers from Redis
    connection drops (e.g. ElastiCache closing idle connections).
    """
    print("Starting RQ worker")
    print(f"AWS Region: {os.getenv('AWS_DEFAULT_REGION')}")
    print(f"S3 Bucket: {os.getenv('S3_BUCKET')}")

    max_restarts = 100  # cap to prevent infinite crash loops
    restart_delay = 5

    for restart in range(max_restarts):
        try:
            if restart > 0:
                print(f"[Worker] Restarting (attempt {restart + 1})...")
                time.sleep(restart_delay)

            conn = connect_to_redis()
            worker = SimpleWorker(['default'], connection=conn)
            worker.work()
            # work() returns normally only on shutdown signal
            print("[Worker] Worker exited normally")
            break
        except Exception as e:
            print(f"[Worker] Crashed: {e}")
            import traceback
            traceback.print_exc()
            print(f"[Worker] Will restart in {restart_delay}s...")

    else:
        print(f"[Worker] Exceeded {max_restarts} restarts, giving up")
        sys.exit(1)


if __name__ == '__main__':
    run_worker()
