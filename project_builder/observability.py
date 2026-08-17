import os

from dotenv import load_dotenv
from agents import add_trace_processor
from langsmith.integrations.openai_agents_sdk import OpenAIAgentsTracingProcessor


_configured = False


def configure_observability() -> None:
    global _configured

    if _configured:
        return

    load_dotenv()

    if not os.getenv("LANGSMITH_API_KEY"):
        print("[OBSERVABILITY] LangSmith desativado: LANGSMITH_API_KEY ausente.")
        return

    add_trace_processor(OpenAIAgentsTracingProcessor())

    _configured = True

    print("[OBSERVABILITY] OpenAI Tracing + LangSmith habilitados.")