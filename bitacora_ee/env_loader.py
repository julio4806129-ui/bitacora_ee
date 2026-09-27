"""Simple .env loader without external deps."""
import os
from pathlib import Path

def load_dotenv(path=None):
    if path is None:
        path = Path(__file__).resolve().parent.parent / '.env'
    path = Path(path)
    if not path.exists():
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

def config(key, default=None, cast=None):
    val = os.environ.get(key, default)
    if val is None:
        return default
    if cast is bool:
        return str(val).lower() in ('1', 'true', 'yes', 'on')
    if cast is int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    if cast is list or str(cast) == 'Csv':
        return [x.strip() for x in str(val).split(',') if x.strip()]
    if cast:
        return cast(val)
    return val
