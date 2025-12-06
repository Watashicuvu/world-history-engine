import os
from pydantic import SecretStr
from pathlib import Path

# load dot_env can be placed there
key = os.getenv('API_KEY', '')
# LMStudio api server base_url example:
base_url = os.getenv('BASE_URL', 'http://192.168.1.127:1235/v1')
model = os.getenv('MODEL', 'mistralai/ministral-3-14b-reasoning')
#model = os.getenv('MODEL', 'qwen3-vl-8b-instruct-mlx')

fallback_template_path = Path('world_output') / 'world_final.json'

api_key = SecretStr(secret_value=key)
