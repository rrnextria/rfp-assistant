from __future__ import annotations

SYSTEM_PROMPT = """You are an expert RFP (Request for Proposal) response specialist. Your role is to provide accurate, professional, and well-structured answers to RFP questions based on the provided context from approved enterprise documents.

Guidelines:
- Base your answers ONLY on the provided context documents
- Always cite specific documents when making claims
- If the context doesn't contain sufficient information, clearly state what is and isn't covered
- Be concise but comprehensive
- Use professional business language appropriate for RFP responses
- If information is partial, acknowledge this explicitly"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_prompt(
    question: str,
    context_chunks: list[dict],
    mode: str = "answer",
    detail_level: str = "balanced",
) -> str:
    """Build the user-facing prompt based on mode and detail_level."""
    context_text = "\n\n".join(
        f"[Document: {c.get('doc_id', 'unknown')}]\n{c.get('text', '')}"
        for c in context_chunks
    )

    detail_instructions = {
        "minimal": "Provide a concise bullet-point answer. Be brief and direct.",
        "balanced": "Provide a structured paragraph answer with clear citations.",
        "detailed": "Provide a comprehensive technical narrative with detailed citations, examples, and full explanation.",
    }
    detail_instruction = detail_instructions.get(detail_level, detail_instructions["balanced"])

    mode_prefixes = {
        "answer": "",
        "draft": (
            "TASK: Draft a formal RFP response for the following question. "
            "Use professional proposal language with clear structure.\n\n"
        ),
        "review": (
            "TASK: Review the following RFP question and identify any gaps, "
            "ambiguities, or risks in our ability to answer it based on the context.\n\n"
        ),
        "gap": (
            "TASK: Identify what information is MISSING from the provided context "
            "that would be needed to fully answer this question. List specific gaps.\n\n"
        ),
    }
    mode_prefix = mode_prefixes.get(mode, "")

    return (
        f"{mode_prefix}"
        f"Context Documents:\n{context_text}\n\n"
        f"Question: {question}\n\n"
        f"Instructions: {detail_instruction}"
    )
