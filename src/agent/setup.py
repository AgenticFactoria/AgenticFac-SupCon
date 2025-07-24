import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import set_default_openai_client
from agents import set_tracing_disabled

load_dotenv()

set_tracing_disabled(True)
custom_client = AsyncOpenAI(
    base_url="https://api.moonshot.cn/v1", api_key=os.getenv("MOONSHOT_API_KEY")
)
set_default_openai_client(custom_client)
