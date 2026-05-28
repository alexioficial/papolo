import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY no esta seteada")
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _client

def model_name() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
