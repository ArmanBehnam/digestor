import os
import sys
import time
from pathlib import Path
from redis import Redis
from rq import Worker, Queue, SimpleWorker

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
from config.config_loader import CONFIG
import tasks


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
                    health_check_interval=10,
                    retry_on_timeout=True)
            else:
                conn = Redis.from_url(
                    redis_url,
                    socket_connect_timeout=30,
                    socket_timeout=600,
                    socket_keepalive=True,
                    health_check_interval=10,
                    retry_on_timeout=True)

            conn.ping()
            print(f"Connected to Redis successfully")
            return conn

        except Exception as e:
            print(f"✗ Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                print(f"  Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise


def run_worker():
    """Entry point called by entrypoint.py when PROCESS_TYPE=worker."""
    print("Starting RQ worker")
    print(f"AWS Region: {os.getenv('AWS_DEFAULT_REGION')}")
    print(f"S3 Bucket: {os.getenv('S3_BUCKET_NAME', os.getenv('S3_BUCKET'))}")

    conn = connect_to_redis()
    worker = SimpleWorker(['default'], connection=conn)
    worker.work()


if __name__ == '__main__':
    run_worker()