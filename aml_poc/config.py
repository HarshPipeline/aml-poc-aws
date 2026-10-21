import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def agent_mode() -> str:
    mode = os.environ.get("AML_AGENT_MODE", "demo")
    if mode not in {"demo", "claude", "openai"}:
        raise ValueError("AML_AGENT_MODE must be demo, claude, or openai")
    return mode


def app_schema() -> str:
    return os.environ.get("AML_APP_SCHEMA", "aml_app")
