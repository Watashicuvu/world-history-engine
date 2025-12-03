import os
from pydantic import SecretStr
from pathlib import Path

key = os.getenv('API_KEY', '')
base_url = 'http://192.168.1.127:1235/v1'
model = 'gemma-3-12b-it'
#model = 'qwen3-vl-8b-instruct-mlx'
#fallback_template_path = Path('world_output') / 'snapshots' / 'world_epoch_0.json'
fallback_template_path = Path('world_output') / 'world_final.json'

api_key = SecretStr(secret_value=key)