"""Simple time tracking for orchestration service steps."""

from typing import Dict, Optional
from loguru import logger


def log_step_timings(
    timing_dict: Dict[str, float], chat_id: Optional[str] = None
) -> None:
    """
    Log all step timings in a clean format.

    Args:
        timing_dict: Dictionary containing step names and their execution times
        chat_id: Optional chat ID for context
    """
    if not timing_dict:
        return

    # Parent/composite timings that should be hidden from logs
    # These are aggregate timings that already include their sub-steps
    PARENT_TIMINGS = {"classifier.route"}

    prefix = f"[{chat_id}] " if chat_id else ""
    logger.info(f"{prefix}STEP EXECUTION TIMES:")

    total_time = 0.0
    for step_name, elapsed_time in timing_dict.items():
        # Skip parent/composite timings entirely
        if step_name in PARENT_TIMINGS:
            continue

        # Special handling for inline streaming guardrails
        if step_name == "output_guardrails" and elapsed_time < 0.001:
            logger.info(f"  {step_name:25s}: (inline during streaming)")
        else:
            logger.info(f"  {step_name:25s}: {elapsed_time:.3f}s")
            total_time += elapsed_time

    logger.info(f"  {'TOTAL':25s}: {total_time:.3f}s")
