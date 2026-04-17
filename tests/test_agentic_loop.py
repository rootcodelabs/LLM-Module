"""Unit tests for the AgenticLoop module."""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tool_classifier.agentic_loop import AgenticLoop
from tool_classifier.enums import AgenticLoopStatus
from tool_classifier.param_extractor import ParamExtractionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHAT_ID = "test-chat-1"

_SCHEMA_TWO_REQUIRED: List[Dict[str, Any]] = [
    {
        "name": "countryIsoCode",
        "type": "string",
        "required": True,
        "description": "Country",
    },
    {
        "name": "validFrom",
        "type": "date",
        "required": True,
        "description": "Start date",
    },
]

_SCHEMA_ONE_OPTIONAL: List[Dict[str, Any]] = [
    {
        "name": "limit",
        "type": "integer",
        "required": False,
        "description": "Max results",
    },
]

_SCHEMA_EMPTY: List[Dict[str, Any]] = []

_HISTORY: List[Dict[str, Any]] = [
    {"authorRole": "user", "message": "Get me public holidays"},
    {"authorRole": "bot", "message": "Which country?"},
]


def _make_session_store_mock() -> AsyncMock:
    """Return an AsyncMock standing in for APIToolSessionStore."""
    mock = AsyncMock()
    mock.update = AsyncMock(return_value=None)
    return mock


def _make_extractor_mock(result: ParamExtractionResult) -> MagicMock:
    """Return a MagicMock whose __call__() returns the given ParamExtractionResult."""
    mock = MagicMock(return_value=result)
    return mock


def _make_loop(
    extractor_mock: MagicMock,
    session_store_mock: AsyncMock | None = None,
) -> AgenticLoop:
    """Convenience factory that wires up AgenticLoop with mocked dependencies."""
    return AgenticLoop(
        session_store=session_store_mock or _make_session_store_mock(),
        param_extractor=extractor_mock,
    )


def _extraction(
    extracted: Dict[str, Any],
    missing: List[str],
    question: str,
) -> ParamExtractionResult:
    return ParamExtractionResult(
        extracted_params=extracted,
        missing_required=missing,
        clarifying_question=question,
    )


# ---------------------------------------------------------------------------
# Turn limit guard
# ---------------------------------------------------------------------------


class TestMaxTurnsReached:
    @pytest.mark.asyncio
    async def test_max_turns_reached_when_turn_count_equals_max(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hello",
            conversation_history=_HISTORY,
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=5,
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED
        extractor_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_turns_reached_when_turn_count_exceeds_max(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hello",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"validFrom": "2026-01-01"},
            turn_count=10,
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED
        assert result.collected_params == {"validFrom": "2026-01-01"}
        extractor_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_count_incremented_on_max_turns(self) -> None:
        loop = _make_loop(_make_extractor_mock(_extraction({}, [], "none")))

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hi",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=5,
            max_turns=5,
        )

        assert result.turn_count == 6


# ---------------------------------------------------------------------------
# COMPLETED status
# ---------------------------------------------------------------------------


class TestCompleted:
    @pytest.mark.asyncio
    async def test_completed_when_extractor_finds_last_param(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"validFrom": "2026-01-01"}, [], "none")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="January 2026",
            conversation_history=_HISTORY,
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE"},
            turn_count=2,
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.COMPLETED
        assert result.collected_params == {
            "countryIsoCode": "EE",
            "validFrom": "2026-01-01",
        }
        assert result.clarifying_question == ""

    @pytest.mark.asyncio
    async def test_completed_when_no_required_params_in_schema(self) -> None:
        extractor_mock = _make_extractor_mock(_extraction({}, [], "none"))
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="list all",
            conversation_history=[],
            params_schema=_SCHEMA_ONE_OPTIONAL,
            collected_params={},
            turn_count=0,
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_completed_with_empty_schema(self) -> None:
        extractor_mock = _make_extractor_mock(_extraction({}, [], "none"))
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="go",
            conversation_history=[],
            params_schema=_SCHEMA_EMPTY,
            collected_params={},
            turn_count=0,
        )

        assert result.status == AgenticLoopStatus.COMPLETED


# ---------------------------------------------------------------------------
# NEEDS_INPUT status
# ---------------------------------------------------------------------------


class TestNeedsInput:
    @pytest.mark.asyncio
    async def test_needs_input_when_params_still_missing(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction(
                {"countryIsoCode": "EE"},
                ["validFrom"],
                "From which date?",
            )
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Estonia",
            conversation_history=_HISTORY,
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT
        assert result.clarifying_question == "From which date?"

    @pytest.mark.asyncio
    async def test_needs_input_when_extractor_finds_nothing(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="I want holidays",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT
        assert result.clarifying_question == "Which country and date?"


# ---------------------------------------------------------------------------
# Param merging
# ---------------------------------------------------------------------------


class TestParamMerging:
    @pytest.mark.asyncio
    async def test_new_params_merged_with_prior_params(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"validFrom": "2026-01-01"}, [], "none")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="January 2026",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE"},
            turn_count=1,
        )

        assert result.collected_params == {
            "countryIsoCode": "EE",
            "validFrom": "2026-01-01",
        }

    @pytest.mark.asyncio
    async def test_prior_params_not_overwritten_by_extractor(self) -> None:
        # Extractor tries to update countryIsoCode, but prior value is authoritative
        extractor_mock = _make_extractor_mock(
            _extraction({"countryIsoCode": "LV"}, [], "none")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Latvia",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE", "validFrom": "2026-01-01"},
            turn_count=2,
        )

        # Prior "EE" must not be overwritten by newly "extracted" "LV"
        assert result.collected_params["countryIsoCode"] == "EE"
        assert result.status == AgenticLoopStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_empty_extraction_preserves_prior_params(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["validFrom"], "From which date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="not sure",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE"},
            turn_count=0,
        )

        assert result.collected_params == {"countryIsoCode": "EE"}


# ---------------------------------------------------------------------------
# Turn count
# ---------------------------------------------------------------------------


class TestTurnCount:
    @pytest.mark.asyncio
    async def test_turn_count_incremented_on_needs_input(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hello",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
        )

        assert result.turn_count == 4

    @pytest.mark.asyncio
    async def test_turn_count_incremented_on_completed(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"countryIsoCode": "EE", "validFrom": "2026-01-01"}, [], "none")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Estonia, January 2026",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,
        )

        assert result.turn_count == 1


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    @pytest.mark.asyncio
    async def test_session_saved_on_needs_input(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"countryIsoCode": "EE"}, ["validFrom"], "From which date?")
        )
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Estonia",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,
        )

        store_mock.update.assert_awaited_once_with(
            _CHAT_ID,
            collected_params={"countryIsoCode": "EE"},
            turn_count=1,
            awaiting_continuation=False,
        )

    @pytest.mark.asyncio
    async def test_session_saved_on_completed(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"validFrom": "2026-01-01"}, [], "none")
        )
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="January 2026",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE"},
            turn_count=2,
        )

        store_mock.update.assert_awaited_once_with(
            _CHAT_ID,
            collected_params={"countryIsoCode": "EE", "validFrom": "2026-01-01"},
            turn_count=3,
            awaiting_continuation=False,
        )

    @pytest.mark.asyncio
    async def test_session_not_saved_on_max_turns(self) -> None:
        extractor_mock = _make_extractor_mock(_extraction({}, [], "none"))
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hi",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=5,
            max_turns=5,
        )

        store_mock.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_session_not_saved_on_extractor_error(self) -> None:
        extractor_mock = MagicMock()
        extractor_mock.side_effect = RuntimeError("LLM timeout")
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Estonia",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=1,
        )

        store_mock.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_session_save_failure_does_not_raise(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        store_mock = _make_session_store_mock()
        store_mock.update.side_effect = RuntimeError("Redis unavailable")
        loop = _make_loop(extractor_mock, store_mock)

        # Should not raise even if Redis save fails
        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hi",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_extractor_exception_returns_needs_input(self) -> None:
        extractor_mock = MagicMock()
        extractor_mock.side_effect = RuntimeError("LLM timeout")
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="Estonia",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"validFrom": "2026-01-01"},
            turn_count=1,
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT
        assert result.clarifying_question == ""
        # Prior collected_params preserved on error
        assert result.collected_params == {"validFrom": "2026-01-01"}
        assert result.turn_count == 2

    @pytest.mark.asyncio
    async def test_extractor_called_with_correct_arguments(self) -> None:
        extractor_mock = _make_extractor_mock(
            _extraction({"countryIsoCode": "EE"}, ["validFrom"], "From which date?")
        )

        with patch("tool_classifier.agentic_loop.asyncio.to_thread") as mock_to_thread:
            # Make to_thread call the function synchronously so we can inspect args
            async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            mock_to_thread.side_effect = fake_to_thread

            loop = _make_loop(extractor_mock)
            await loop.run_turn(
                chat_id=_CHAT_ID,
                user_message="Estonia",
                conversation_history=_HISTORY,
                params_schema=_SCHEMA_TWO_REQUIRED,
                collected_params={"validFrom": "2026-01-01"},
                turn_count=1,
            )

        extractor_mock.assert_called_once_with(
            "Estonia",
            _SCHEMA_TWO_REQUIRED,
            _HISTORY,
            {"validFrom": "2026-01-01"},
        )


# ---------------------------------------------------------------------------
# Continuation decision (turn-3 yes/no prompt)
# ---------------------------------------------------------------------------


class TestContinuationDecision:
    @pytest.mark.asyncio
    async def test_continuation_question_asked_at_threshold(self) -> None:
        """AWAITING_CONTINUATION_DECISION is returned on exactly continuation_turn=3."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="I don't know",
            conversation_history=_HISTORY,
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=2,  # updated_turn_count == 3 == continuation_turn
            max_turns=5,
        )

        assert result.status == AgenticLoopStatus.AWAITING_CONTINUATION_DECISION
        assert result.clarifying_question != ""
        assert result.turn_count == 3

    @pytest.mark.asyncio
    async def test_continuation_not_asked_before_threshold(self) -> None:
        """Normal NEEDS_INPUT before the continuation threshold."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="hmm",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=0,  # updated_turn_count == 1, below threshold
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT

    @pytest.mark.asyncio
    async def test_continuation_not_asked_after_threshold(self) -> None:
        """Normal NEEDS_INPUT after the continuation threshold (user already continued)."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="still not sure",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,  # updated_turn_count == 4, past threshold
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT

    @pytest.mark.asyncio
    async def test_user_yes_resets_flag_and_continues(self) -> None:
        """When awaiting_continuation=True and user says 'yes', loop continues."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="yes",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            max_turns=5,
            awaiting_continuation=True,
        )

        # Should continue normally — NEEDS_INPUT (params still missing after "yes")
        assert result.status == AgenticLoopStatus.NEEDS_INPUT

    @pytest.mark.asyncio
    async def test_user_estonian_yes_continues(self) -> None:
        """Estonian 'jah' is recognised as an affirmative response."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Mis riik?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="jah",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            max_turns=5,
            awaiting_continuation=True,
        )

        assert result.status == AgenticLoopStatus.NEEDS_INPUT

    @pytest.mark.asyncio
    async def test_user_no_returns_max_turns_reached(self) -> None:
        """When awaiting_continuation=True and user says 'no', RAG fallback is triggered."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="no",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            max_turns=5,
            awaiting_continuation=True,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED
        assert result.clarifying_question == ""

    @pytest.mark.asyncio
    async def test_user_estonian_no_exits(self) -> None:
        """Estonian 'ei' triggers RAG fallback."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Mis riik?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="ei",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            awaiting_continuation=True,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED

    @pytest.mark.asyncio
    async def test_ambiguous_response_exits(self) -> None:
        """An ambiguous response while awaiting continuation defaults to exit."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="I'm not sure what to do",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            awaiting_continuation=True,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED

    @pytest.mark.asyncio
    async def test_exit_preserves_collected_params(self) -> None:
        """Collected params are returned unchanged when the user chooses to exit."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["validFrom"], "Which date?")
        )
        loop = _make_loop(extractor_mock)

        result = await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="no",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={"countryIsoCode": "EE"},
            turn_count=3,
            awaiting_continuation=True,
        )

        assert result.status == AgenticLoopStatus.MAX_TURNS_REACHED
        assert result.collected_params == {"countryIsoCode": "EE"}

    @pytest.mark.asyncio
    async def test_session_saved_with_awaiting_continuation_true(self) -> None:
        """Session is persisted with awaiting_continuation=True at the threshold."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode", "validFrom"], "Which country and date?")
        )
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="no idea",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=2,
        )

        store_mock.update.assert_awaited_once_with(
            _CHAT_ID,
            collected_params={},
            turn_count=3,
            awaiting_continuation=True,
        )

    @pytest.mark.asyncio
    async def test_session_not_saved_on_user_exit(self) -> None:
        """Session is NOT saved when the user chooses to exit (caller deletes it)."""
        extractor_mock = _make_extractor_mock(
            _extraction({}, ["countryIsoCode"], "Which country?")
        )
        store_mock = _make_session_store_mock()
        loop = _make_loop(extractor_mock, store_mock)

        await loop.run_turn(
            chat_id=_CHAT_ID,
            user_message="no",
            conversation_history=[],
            params_schema=_SCHEMA_TWO_REQUIRED,
            collected_params={},
            turn_count=3,
            awaiting_continuation=True,
        )

        store_mock.update.assert_not_awaited()
