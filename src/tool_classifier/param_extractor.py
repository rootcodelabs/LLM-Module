"""API parameter extraction using DSPy."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

import dspy
from loguru import logger

_TRUTHY_STRINGS = {"true", "yes", "jah", "1", "on", "õige", "да"}
_FALSY_STRINGS = {"false", "no", "ei", "0", "off", "vale", "нет"}

_MAX_HISTORY_TURNS = 5


class ParamExtractionResult(TypedDict):
    """Return contract for ParamExtractionModule.forward()."""

    extracted_params: Dict[str, Any]
    missing_required: List[str]
    clarifying_question: str


class ParamExtractionSignature(dspy.Signature):
    """Extract API parameter values from user message and conversation history.

    CRITICAL LANGUAGE RULE:
    - Understand Estonian, English, and Russian input
    - Generate clarifying_question in the SAME language as the user_message

    Extraction rules:
    - Extract values for parameters listed in params_schema that are not yet in already_collected
    - Search BOTH user_message AND conversation_history for values
    - Do NOT re-extract parameters already present in already_collected
    - Validate types: dates must be ISO 8601 (YYYY-MM-DD), integers must be whole numbers,
      numbers must be numeric, booleans must be true or false

    missing_required rules:
    - List every required parameter (required=true in schema) whose value is absent
      AFTER combining already_collected with newly extracted params
    - Do NOT list optional parameters as missing

    clarifying_question rules:
    - After extraction, check whether ALL required params are now satisfied
      (i.e., present in already_collected OR just extracted).
    - If ALL required params are satisfied, return the literal string "none".
    - If ONE OR MORE required params are still missing, generate ONE friendly question
      that asks for ALL of those remaining missing params at once.
      On the first turn this may cover many params; on follow-up turns it narrows
      to only the params the user has not yet provided.
    - Use each missing parameter's description field to phrase the question naturally
      (e.g., "Which country and date would you like to use?" not "Provide countryIsoCode and startDate")
    - Never expose raw parameter names (camelCase identifiers) to the user
    """

    user_message: str = dspy.InputField(
        desc="Current turn message from the user in Estonian, English, or Russian"
    )
    conversation_history: str = dspy.InputField(
        desc="Recent conversation turns formatted as 'role: message', one per line"
    )
    params_schema: str = dspy.InputField(
        desc='JSON array of parameter schemas: [{"name": str, "type": str, "required": bool, "description": str}]'
    )
    already_collected: str = dspy.InputField(
        desc="JSON object of already-collected parameter values: {param_name: value}"
    )

    extracted_params: str = dspy.OutputField(
        desc='Valid JSON object of newly extracted parameters only: {"param_name": value}. Empty object {} if nothing new found.'
    )
    missing_required: str = dspy.OutputField(
        desc='Valid JSON array of required parameter names still missing after extraction: ["param1", "param2"]. Empty array [] if all required params are satisfied.'
    )
    clarifying_question: str = dspy.OutputField(
        desc='A single natural-language question that asks for ALL missing parameters at once, or the literal string "none" if all required params are collected.'
    )


class ParamExtractionModule(dspy.Module):
    """DSPy Module for API parameter extraction from natural language."""

    def __init__(self) -> None:
        """Initialize param extraction module with Predict (direct prediction)."""
        super().__init__()
        self.extractor = dspy.Predict(ParamExtractionSignature)

    def forward(
        self,
        user_message: str,
        params_schema: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        already_collected: Optional[Dict[str, Any]] = None,
    ) -> ParamExtractionResult:
        """
        Extract parameter values from user message and conversation history.

        Args:
            user_message: Current turn message from the user
            params_schema: List of parameter schema dicts with name, type, required, description
            conversation_history: Recent conversation messages (optional)
            already_collected: Parameter values collected in prior turns (optional)

        Returns:
            ParamExtractionResult with extracted_params, missing_required, clarifying_question
        """
        already_collected = already_collected or {}

        history_text = self._format_conversation_history(conversation_history)
        params_schema_json = json.dumps(params_schema, ensure_ascii=False)
        already_collected_json = json.dumps(already_collected, ensure_ascii=False)

        result = None
        try:
            result = self.extractor(
                user_message=user_message,
                conversation_history=history_text,
                params_schema=params_schema_json,
                already_collected=already_collected_json,
            )

            # Parse extracted_params
            extracted_raw = json.loads(result.extracted_params)
            if not isinstance(extracted_raw, dict):
                raise ValueError("extracted_params is not a JSON object")

            # Parse missing_required
            missing_raw = json.loads(result.missing_required)
            if not isinstance(missing_raw, list):
                raise ValueError("missing_required is not a JSON array")

            clarifying_question = (result.clarifying_question or "").strip()

            # Post-process: validate extracted param types against schema
            schema_map: Dict[str, Dict[str, Any]] = {
                p["name"]: p for p in params_schema if isinstance(p, dict)
            }
            validated_params: Dict[str, Any] = {}
            type_invalid_params: List[str] = []

            for param_name, raw_value in extracted_raw.items():
                if param_name in already_collected:
                    # Prior turns are authoritative — discard any LLM re-output
                    continue
                schema_entry = schema_map.get(param_name)
                if schema_entry is None:
                    # Param not in schema — skip silently
                    continue
                param_type = schema_entry.get("type", "string")
                is_valid, coerced = self._validate_param_type(raw_value, param_type)
                if is_valid:
                    validated_params[param_name] = coerced
                else:
                    logger.warning(
                        f"Extracted value for '{param_name}' failed type validation "
                        f"(expected {param_type}, got {raw_value!r})"
                    )
                    type_invalid_params.append(param_name)

            # Re-derive missing required params after type validation
            # already_collected is authoritative: its values must not be overwritten
            all_collected = {**validated_params, **already_collected}
            missing_required: List[str] = [
                p["name"]
                for p in params_schema
                if isinstance(p, dict)
                and p.get("required", False)
                and p["name"] not in all_collected
            ]

            # Add type-invalid required params back to missing list
            for param_name in type_invalid_params:
                schema_entry = schema_map.get(param_name)
                if (
                    schema_entry is not None
                    and schema_entry.get("required", False)
                    and param_name not in missing_required
                ):
                    missing_required.append(param_name)

            # Normalise clarifying_question: override with "none" when nothing is missing
            if not missing_required:
                clarifying_question = "none"
            elif clarifying_question.lower() == "none":
                # LLM incorrectly returned "none" despite missing params — reset to empty
                # string so callers receive a reliable signal that a follow-up is needed.
                logger.warning(
                    "LLM returned clarifying_question='none' but required params are "
                    f"still missing: {missing_required}. Resetting to empty string."
                )
                clarifying_question = ""

            return ParamExtractionResult(
                extracted_params=validated_params,
                missing_required=missing_required,
                clarifying_question=clarifying_question,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse param extraction JSON: {e}")
            if result:
                logger.error(
                    f"Raw extracted_params: {getattr(result, 'extracted_params', None)}"
                )
                logger.error(
                    f"Raw missing_required: {getattr(result, 'missing_required', None)}"
                )
            return self._safe_defaults(params_schema, already_collected)

        except Exception as e:
            logger.exception(f"Param extraction forward failed: {e}")
            return self._safe_defaults(params_schema, already_collected)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_param_type(
        self, value: object, param_type: str
    ) -> tuple[bool, object]:
        """
        Validate and coerce a raw extracted value to the expected param type.

        Args:
            value: Raw value from LLM output
            param_type: Expected type from param schema

        Returns:
            (is_valid, coerced_value) — coerced_value equals value when is_valid is False
        """
        if value is None:
            return False, value

        str_value = str(value).strip()

        if param_type == "string":
            return True, str_value

        if param_type == "date":
            try:
                # Accept ISO 8601 date strings; datetime.fromisoformat handles YYYY-MM-DD
                parsed = datetime.fromisoformat(str_value)
                return True, parsed.date().isoformat()
            except (ValueError, TypeError):
                return False, value

        if param_type == "integer":
            try:
                # int() already rejects float strings like "3.5" with ValueError
                int_val = int(str_value)
                return True, int_val
            except (ValueError, TypeError):
                return False, value

        if param_type == "number":
            try:
                return True, float(str_value)
            except (ValueError, TypeError):
                return False, value

        if param_type == "boolean":
            lower = str_value.lower()
            if lower in _TRUTHY_STRINGS:
                return True, True
            if lower in _FALSY_STRINGS:
                return True, False
            return False, value

        # Unknown type — accept as string to avoid silent data loss
        logger.warning(f"Unknown param type '{param_type}'; accepting as string")
        return True, str_value

    def _format_conversation_history(
        self, conversation_history: Optional[List[Dict[str, Any]]]
    ) -> str:
        """
        Format the last N conversation turns as plain text for the LLM prompt.

        Args:
            conversation_history: List of message dicts with authorRole and message keys

        Returns:
            Newline-separated string of "role: message" or "(No conversation history)"
        """
        if not conversation_history:
            return "(No conversation history)"

        history_lines: List[str] = []
        for msg in conversation_history[-_MAX_HISTORY_TURNS:]:
            role = msg.get("authorRole", "unknown")
            content = msg.get("message", "")
            if content:
                history_lines.append(f"{role}: {content}")

        return (
            "\n".join(history_lines) if history_lines else "(No conversation history)"
        )

    def _safe_defaults(
        self,
        params_schema: List[Dict[str, Any]],
        already_collected: Dict[str, Any],
    ) -> ParamExtractionResult:
        """
        Return safe default result when the LLM call or JSON parsing fails.

        All required params not already collected are put in missing_required.
        """
        missing_required = [
            p["name"]
            for p in params_schema
            if isinstance(p, dict)
            and p.get("required", False)
            and p["name"] not in already_collected
        ]
        return ParamExtractionResult(
            extracted_params={},
            missing_required=missing_required,
            clarifying_question="none" if not missing_required else "",
        )
