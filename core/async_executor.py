"""
Async execution with LLM endpoint fallback for Hugging Face Spaces.
"""
import os
import asyncio
from typing import Optional, Any, Callable
import streamlit as st

class LLMConfig:
    """Configuration for LLM endpoints with environment-aware fallback."""

    def __init__(self):
        self.endpoint = os.getenv("LLM_ENDPOINT", "http://localhost:11434")
        self.mode = os.getenv("LLM_MODE", "local")  # local, mock, api
        self.timeout = int(os.getenv("LLM_TIMEOUT", "30"))

    def get_mode_display(self) -> str:
        """Get display string for current LLM mode."""
        modes = {
            "local": "Local Ollama",
            "mock": "Mock Mode (Demo)",
            "api": "External API"
        }
        return modes.get(self.mode, "Unknown")

    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return self.mode == "mock"

@st.cache_resource
def get_llm_config() -> LLMConfig:
    """Get cached LLM configuration."""
    return LLMConfig()

class AsyncExecutor:
    """Executes async operations with progress tracking."""

    def __init__(self):
        self.llm_config = get_llm_config()

    async def execute_with_progress(self, task_func: Callable, task_name: str, *args, **kwargs) -> Any:
        """Execute async task with Streamlit progress tracking."""
        with st.status(f"{task_name}...", expanded=True) as status:
            st.write(f"Starting {task_name.lower()}...")

            try:
                result = await task_func(*args, **kwargs)
                status.update(label=f"{task_name} complete!", state="complete")
                return result
            except Exception as e:
                status.update(label=f"{task_name} failed!", state="error")
                st.error(f"Error during {task_name.lower()}: {str(e)}")
                raise
