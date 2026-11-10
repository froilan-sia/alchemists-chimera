from typing import List, Dict, Any


class ContextBuilder:
    @staticmethod
    def assemble_context(
        graph_results: List[str], vector_chunks: List[str], intent_info: Dict[str, Any]
    ) -> str:
        """
        Stitches graph facts and vector snippets into a structured text prompt payload.
        """
        alpha = intent_info.get("alpha", 0.5)
        query_type = intent_info.get("type", "Hybrid")

        context_blocks = []
        context_blocks.append(f"=== SYSTEM RETRIEVAL METRICS ===")
        context_blocks.append(f"Routing Profile: {query_type} (Alpha Weight: {alpha})")
        context_blocks.append(
            f"Confidence Strategy: {'Graph Dominant' if alpha >= 0.7 else 'Vector Dominant' if alpha <= 0.3 else 'Balanced Fusion'}\n"
        )

        # Inject Absolute Deterministic Facts First (The Graph Branch)
        if graph_results:
            context_blocks.append("=== DETERMINISTIC KNOWLEDGE GRAPH FACTS ===")
            for i, fact in enumerate(graph_results, 1):
                context_blocks.append(f"Fact [{i}]: {fact}")
            context_blocks.append("")

        # Inject Statistical Semantic Narrative Text (The Vector Branch)
        if vector_chunks:
            context_blocks.append("=== UNSTRUCTURED DOCUMENT NARRATIVE CHUNKS ===")
            for j, chunk in enumerate(vector_chunks, 1):
                context_blocks.append(f"Context Chunk [{j}]: {chunk.strip()}")
            context_blocks.append("")

        return "\n".join(context_blocks)
