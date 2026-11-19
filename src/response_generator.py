import ollama
from typing import Generator

from .rdf_utils import format_rdf_text


class ResponseGenerator:
    def __init__(self, model_name: str = "qwen2.5:3b"):
        self.model_name = model_name

    def generate_response(
        self, query: str, assembled_context: str
    ) -> Generator[str, None, None]:
        """
        Streams responses directly from local Ollama using system-enforced constraints.
        """
        system_instruction = (
            "You are the Alchemist's Chimera RAG Engine. You must answer the user's query "
            "using ONLY the provided Knowledge Graph Facts and Unstructured Document Chunks below. "
            "If the information contradicts itself, prioritize Knowledge Graph Facts. "
            "Provide clean semantic citations (e.g., [Fact 1] or [Chunk 2]) for your statements. "
            "If you cannot answer using the context, state that clearly."
        )

        safe_context = format_rdf_text(assembled_context)
        prompt = (
            f"CONTEXT INFORMATION:\n\n{safe_context}\n\nUSER QUESTION: {query}"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        # Use the official local python-ollama streaming driver
        response_stream = ollama.chat(
            model=self.model_name, messages=messages, stream=True
        )

        for chunk in response_stream:
            content = chunk.get("message", {}).get("content", "")
            yield format_rdf_text(content)
