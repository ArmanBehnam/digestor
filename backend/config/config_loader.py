# config_loader.py
import os
import json
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_secrets_from_aws():
    """
    Fetch secrets from AWS Secrets Manager.
    Returns a dict of secret key-value pairs, or empty dict on failure.
    """
    secret_name = os.getenv('SECRETS_MANAGER_SECRET_NAME', 'digetor/production/secrets')
    region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

    try:
        import boto3
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response.get('SecretString', '{}')
        secrets = json.loads(secret_string)
        print(f"Loaded {len(secrets)} secrets from AWS Secrets Manager ({secret_name})")
        return secrets
    except ImportError:
        print("WARNING: boto3 not available, skipping Secrets Manager")
        return {}
    except Exception as e:
        print(f"WARNING: Could not load from Secrets Manager: {e}")
        return {}


def load_config():
    try:
        # ------------------------------------------------------------------
        # 1. Load base config from YAML (non-secret settings only)
        # ------------------------------------------------------------------
        config_path = Path(__file__).parent / 'config.yaml'

        if not config_path.exists():
            print(f"WARNING: config.yaml not found at {config_path}")
            config = {}
        else:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            print(f"Config loaded from {config_path}")

        # ------------------------------------------------------------------
        # 2. Load secrets from AWS Secrets Manager (if enabled)
        # ------------------------------------------------------------------
        use_secrets_manager = os.getenv('USE_SECRETS_MANAGER', 'false').lower() == 'true'
        sm_secrets = {}

        if use_secrets_manager:
            sm_secrets = _load_secrets_from_aws()

        # ------------------------------------------------------------------
        # 3. Merge: env vars > Secrets Manager > config.yaml defaults
        #    Environment variables always win (highest priority).
        # ------------------------------------------------------------------
        # Mapping: config_key -> (env_var_name, secrets_manager_key)
        secret_mappings = {
            'AWS_ACCESS_KEY_ID':     ('AWS_ACCESS_KEY_ID',     'AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': ('AWS_SECRET_ACCESS_KEY', 'AWS_SECRET_ACCESS_KEY'),
            'AWS_DEFAULT_REGION':    ('AWS_DEFAULT_REGION',    'AWS_DEFAULT_REGION'),
            'S3_BUCKET_NAME':        ('S3_BUCKET_NAME',        'S3_BUCKET_NAME'),
            'REDIS_URL':             ('REDIS_URL',             'REDIS_URL'),
            'openai_api_key':        ('OPENAI_API_KEY',        'OPENAI_API_KEY'),
            'anthropic_api_key':     ('ANTHROPIC_API_KEY',     'ANTHROPIC_API_KEY'),
            'deepseek_api_key':      ('DEEPSEEK_API_KEY',      'DEEPSEEK_API_KEY'),
            'AZURE_ENDPOINT':        ('AZURE_ENDPOINT',        'AZURE_ENDPOINT'),
            'AZURE_API_KEY':         ('AZURE_API_KEY',         'AZURE_API_KEY'),
        }

        for config_key, (env_key, sm_key) in secret_mappings.items():
            # Priority: env var > Secrets Manager > yaml default
            env_value = os.getenv(env_key)
            if env_value:
                config[config_key] = env_value
                print(f"  [{config_key}] loaded from env var")
            elif sm_key in sm_secrets and sm_secrets[sm_key]:
                config[config_key] = sm_secrets[sm_key]
                print(f"  [{config_key}] loaded from Secrets Manager")
            elif config.get(config_key):
                print(f"  [{config_key}] using config.yaml default")
            else:
                print(f"  [{config_key}] NOT SET")

        # ------------------------------------------------------------------
        # 4. Push resolved values into os.environ so boto3, Azure SDK,
        #    and other libraries that read env vars directly can find them.
        # ------------------------------------------------------------------
        env_push = {
            'AWS_ACCESS_KEY_ID':     config.get('AWS_ACCESS_KEY_ID', ''),
            'AWS_SECRET_ACCESS_KEY': config.get('AWS_SECRET_ACCESS_KEY', ''),
            'AWS_DEFAULT_REGION':    config.get('AWS_DEFAULT_REGION', 'us-east-1'),
            'AZURE_ENDPOINT':        config.get('AZURE_ENDPOINT', ''),
            'AZURE_API_KEY':         config.get('AZURE_API_KEY', ''),
            'S3_BUCKET_NAME':        config.get('S3_BUCKET_NAME', ''),
        }

        for key, value in env_push.items():
            if value:
                os.environ[key] = value

        print("Configuration loaded successfully")
        return config

    except Exception as e:
        print(f"ERROR loading config: {e}")
        import traceback
        traceback.print_exc()
        return {}


print("Loading configuration...")
CONFIG = load_config()
print(f"Configuration ready. Keys: {list(CONFIG.keys())}")
