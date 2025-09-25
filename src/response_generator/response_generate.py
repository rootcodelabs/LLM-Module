from __future__ import annotations
from typing import List, Dict, Any, Tuple
import json
import re
import dspy
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HumanizeRAGSig(dspy.Signature):
    """Produce a grounded answer from the provided context ONLY.

    OUTPUT STRICTLY AS COMPACT JSON:
    {
      "answer": string,                     # human-friendly answer without citations
      # (no citations in answer; they are in separate field)
      "questionOutOfLLMScope": boolean      # true if context insufficient to answer
    }

    Rules:
    - Use ONLY the provided context blocks; do not invent facts.
    - If the context is insufficient, set questionOutOfLLMScope=true and say so briefly.
    - Do not reference context blocks that do not support your answer.
    - Keep the answer concise and clear; bullets are fine.
    - Respond in JSON only (no extra prose).
    """

    question = dspy.InputField()
    context_blocks = dspy.InputField()
    citations = dspy.InputField()
    answer_json = dspy.OutputField(
        desc="A JSON object string with keys: answer, questionOutOfLLMScope."
    )


def build_context_and_citations(
    chunks: List[Dict[str, Any]], use_top_k: int = 10
) -> Tuple[List[str], List[str], bool]:
    """
    Turn retriever chunks -> numbered context blocks and source labels.
    Returns (blocks, labels, has_real_context).
    """
    logger.info(f"Building context from {len(chunks)} chunks (top_k={use_top_k}).")
    blocks: List[str] = []
    labels: List[str] = []
    for i, ch in enumerate(chunks[:use_top_k]):
        text = (ch.get("text") or "").strip()
        meta: Dict[str, Any] = ch.get("meta") or {}
        source_file = meta.get("source_file")
        source = meta.get("source")
        label = source_file or source or f"Chunk-{i + 1}"
        if text:
            blocks.append(f"[Context {i + 1}]\n{text}")
            labels.append(str(label))

    has_real_context = len(blocks) > 0
    if not has_real_context:
        blocks = ["[Context 1]\n(No relevant context available.)"]
        labels = ["No source"]
    logger.info(
        f"Created {len(blocks)} context blocks. Has real context: {has_real_context}."
    )
    return blocks, labels, has_real_context


def _safe_parse_json(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception as e:
        logger.warning(f"Failed to parse JSON: {e}. Raw string: '{s}...'")
        return {}


def _should_flag_out_of_scope(
    answer_text: str, has_real_context: bool, require_citation_marker: bool = False
) -> bool:
    """
    Heuristics to decide out-of-scope when model output is ambiguous:
    - No real context was supplied
    - Very short or empty answer
    - (Optional) No citation markers like [1], [2] present if require_citation_marker is True
    Args:
        answer_text: The answer string to check.
        has_real_context: Whether real context was supplied.
        require_citation_marker: If True, require at least one [n] citation marker.
    """
    if not has_real_context:
        return True
    if not answer_text.strip():
        return True
    if require_citation_marker:
        # Look for at least one numeric citation [n]
        if not re.search(r"\[\d+\]", answer_text):
            # If no explicit citations, treat as possibly out-of-scope
            return True
    return False


class ResponseGeneratorAgent(dspy.Module):
    """
    Creates a grounded, humanized answer from retrieved chunks.
    Returns a dict: {"answer": str, "questionOutOfLLMScope": bool}
    """

    def __init__(self) -> None:
        super().__init__()
        self._predictor = dspy.Predict(HumanizeRAGSig)

    def forward(
        self, question: str, chunks: List[Dict[str, Any]], max_blocks: int = 10
    ) -> Dict[str, Any]:
        logger.info(f"Generating response for question: '{question}...'")
        context_blocks, citation_labels, has_real_context = build_context_and_citations(
            chunks, use_top_k=max_blocks
        )

        result = self._predictor(
            question=question, context_blocks=context_blocks, citations=citation_labels
        )

        raw = getattr(result, "answer_json", "") or ""
        parsed = _safe_parse_json(raw)
        logger.info(f"LLM raw output: {raw}")

        # If model returned valid JSON with required keys, trust it (with a safety fallback)
        if "answer" in parsed and "questionOutOfLLMScope" in parsed:
            # Validate types
            ans = parsed.get("answer")
            scope = parsed.get("questionOutOfLLMScope")
            if not isinstance(ans, str):
                ans = "" if ans is None else str(ans)
            if not isinstance(scope, bool):
                scope = _should_flag_out_of_scope(ans, has_real_context)
            # If model claims in-scope but our heuristics disagree (e.g., no citations), flip to True
            if scope is False and _should_flag_out_of_scope(ans, has_real_context):
                scope = True
                logger.warning("Flipping out-of-scope to True based on heuristics.")

            logger.info(f"Successfully parsed LLM response. Out of scope: {scope}.")
            return {"answer": ans.strip(), "questionOutOfLLMScope": scope}

        # Fallbacks if parsing failed or structure wrong
        logger.warning(
            "Failed to parse LLM response or structure was incorrect. Using fallback."
        )
        # Try to use the raw string as the answer
        fallback_answer = raw.strip() if isinstance(raw, str) else ""
        scope_flag = _should_flag_out_of_scope(fallback_answer, has_real_context)
        if not fallback_answer:
            fallback_answer = (
                "I don’t have enough grounded information in the provided context to answer. "
                "Please provide more details or additional sources."
            )
            scope_flag = True
            logger.warning(
                "Fallback answer is empty; using default out-of-scope message."
            )

        return {"answer": fallback_answer, "questionOutOfLLMScope": scope_flag}
