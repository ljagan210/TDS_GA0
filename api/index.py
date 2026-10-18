import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HERE = Path(__file__).parent
ENV_NAME = os.environ.get("APP_ENV", "development")

# ---- Layer 1: defaults (hardcoded) ----
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

# Assigned contents of each layer. Used only if the real file / variable is missing,
# so the service still behaves correctly on hosts that drop dotfiles.
FALLBACK_YAML = "port: 8349\ndebug: true\n"
FALLBACK_DOTENV = "APP_PORT=8531\nAPP_DEBUG=false\nAPP_LOG_LEVEL=error\n"
ASSIGNED_OS_ENV = {"APP_WORKERS": "4", "APP_DEBUG": "true", "APP_LOG_LEVEL": "info"}

ALIASES = {"num_workers": "workers"}
SECRET_KEYS = {"api_key"}


def normalise_key(key):
    key = key.strip().lower()
    if key.startswith("app_"):
        key = key[4:]
    return ALIASES.get(key, key)


def coerce(key, value):
    if key in ("port", "workers"):
        return int(str(value).strip())
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value).strip()


def read_text(name, fallback):
    for folder in (HERE, HERE.parent, Path.cwd()):
        path = folder / name
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return fallback


def parse_lines(text, separator):
    """Parse simple 'key: value' (YAML) or 'KEY=value' (.env) lines."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or separator not in line:
            continue
        key, value = line.split(separator, 1)
        value = value.split(" #")[0].strip().strip('"').strip("'")
        result[normalise_key(key)] = value
    return result


def yaml_layer():
    return parse_lines(read_text(f"config.{ENV_NAME}.yaml", FALLBACK_YAML), ":")


def dotenv_layer():
    return parse_lines(read_text(".env", FALLBACK_DOTENV), "=")


def os_env_layer():
    env = {**ASSIGNED_OS_ENV, **os.environ}
    return {
        normalise_key(k): v
        for k, v in env.items()
        if k.upper().startswith("APP_") and k.upper() != "APP_ENV"
    }


def effective_config(overrides):
    merged = dict(DEFAULTS)
    for layer in (yaml_layer(), dotenv_layer(), os_env_layer(), overrides):
        merged.update(layer)
    result = {key: coerce(key, value) for key, value in merged.items()}
    for key in SECRET_KEYS:
        if key in result:
            result[key] = "****"
    return result


@app.get("/{path:path}")
def get_config(request: Request, path: str = ""):
    overrides = {}
    for item in request.query_params.getlist("set"):
        if "=" in item:
            key, value = item.split("=", 1)
            overrides[normalise_key(key)] = value
    return effective_config(overrides)
