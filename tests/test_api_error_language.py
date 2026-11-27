"""API-level error messages are returned in the language the user wrote in.

These errors (request validation, service unavailable, rate limiting, stream
timeouts) are produced before the orchestration pipeline detects the language,
so the API layer detects it itself. Estonian is the fallback when there is no
usable message text.
"""

import json
from typing import Any, Dict, List

import pytest
from httpx import ASGITransport, AsyncClient

from src.llm_orchestrator_config.exceptions import StreamTimeoutError
from src.llm_orchestrator_config.llm_ochestrator_constants import (
    ORCHESTRATION_SERVICE_UNAVAILABLE_MESSAGES,
    STREAM_GENERATION_ERROR_MESSAGES,
    STREAM_TIMEOUT_MESSAGES,
    UNEXPECTED_ERROR_MESSAGES,
    VALIDATION_REQUIRED_FIELDS_MISSING_MESSAGES,
)

ESTONIAN_MESSAGE = "Kuidas ma saan taotleda sünnitoetust?"
RUSSIAN_MESSAGE = "Как я могу подать заявку на пособие?"
ENGLISH_MESSAGE = "How can I apply for the benefit?"


LANGUAGE_CASES = [
    (ESTONIAN_MESSAGE, "et"),
    (RUSSIAN_MESSAGE, "ru"),
    (ENGLISH_MESSAGE, "en"),
]


def _valid_body(message: str) -> Dict[str, Any]:
    return {
        "chatId": "chat-1",
        "message": message,
        "authorId": "author-1",
        "conversationHistory": [],
        "url": "opensearch-dashboard-test",
        "environment": "production",
    }


class _FailingOrchestrationService:
    """Stand-in whose stream raises the given error on first iteration."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def stream_orchestration_response(self, request: object):  # noqa: ANN201
        raise self._error
        yield ""  # pragma: no cover - makes this an async generator


async def _post_stream(message: str) -> str:
    from llm_orchestration_service_api import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/orchestrate/stream", json=_valid_body(message))
    return response.text


def _sse_contents(body: str) -> List[str]:
    """Extract payload.content from every SSE data frame."""
    contents: List[str] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            frame: Dict[str, Any] = json.loads(line[len("data: ") :])
            contents.append(frame["payload"]["content"])
    return contents


class TestUserLanguage:
    @pytest.mark.parametrize(
        "message,expected",
        [
            (ESTONIAN_MESSAGE, "et"),
            (RUSSIAN_MESSAGE, "ru"),
            (ENGLISH_MESSAGE, "en"),
            ("", "et"),
            ("   ", "et"),
            (None, "et"),
            (123, "et"),
        ],
    )
    def test_detects_language_with_estonian_fallback(
        self, message: object, expected: str
    ) -> None:
        from llm_orchestration_service_api import _user_language

        assert _user_language(message) == expected


class TestValidationErrorLanguage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message,lang",
        [(ESTONIAN_MESSAGE, "et"), (RUSSIAN_MESSAGE, "ru"), (ENGLISH_MESSAGE, "en")],
    )
    async def test_stream_validation_error_follows_message_language(
        self, message: str, lang: str
    ) -> None:
        from llm_orchestration_service_api import app

        # authorId and url are missing -> required-fields validation error
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/orchestrate/stream",
                json={
                    "chatId": "chat-1",
                    "message": message,
                    "environment": "production",
                },
            )

        assert _sse_contents(response.text) == [
            VALIDATION_REQUIRED_FIELDS_MISSING_MESSAGES[lang]
        ]


class TestStreamingErrorLanguage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message,lang",
        [(ESTONIAN_MESSAGE, "et"), (RUSSIAN_MESSAGE, "ru"), (ENGLISH_MESSAGE, "en")],
    )
    async def test_service_unavailable_follows_message_language(
        self, message: str, lang: str
    ) -> None:
        from llm_orchestration_service_api import app

        saved = getattr(app.state, "orchestration_service", None)
        had_service = hasattr(app.state, "orchestration_service")
        app.state.orchestration_service = None
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/orchestrate/stream",
                    json={
                        "chatId": "chat-1",
                        "message": message,
                        "authorId": "author-1",
                        "conversationHistory": [],
                        "url": "opensearch-dashboard-test",
                        "environment": "production",
                    },
                )
        finally:
            if had_service:
                app.state.orchestration_service = saved
            else:
                del app.state.orchestration_service

        assert _sse_contents(response.text) == [
            ORCHESTRATION_SERVICE_UNAVAILABLE_MESSAGES[lang],
            "END",
        ]


class TestStreamFailureLanguage:
    """Failures while streaming are reported in the language the user wrote in."""

    @pytest.fixture
    def failing_service(self, request: pytest.FixtureRequest):  # noqa: ANN201
        from llm_orchestration_service_api import app

        had_service = hasattr(app.state, "orchestration_service")
        saved = getattr(app.state, "orchestration_service", None)
        app.state.orchestration_service = _FailingOrchestrationService(request.param)
        yield
        if had_service:
            app.state.orchestration_service = saved
        else:
            del app.state.orchestration_service

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failing_service", [StreamTimeoutError("too slow")], indirect=True
    )
    @pytest.mark.parametrize("message,lang", LANGUAGE_CASES)
    async def test_stream_timeout(
        self, failing_service: None, message: str, lang: str
    ) -> None:
        assert _sse_contents(await _post_stream(message)) == [
            STREAM_TIMEOUT_MESSAGES[lang],
            "END",
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failing_service", [RuntimeError("LLM provider crashed")], indirect=True
    )
    @pytest.mark.parametrize("message,lang", LANGUAGE_CASES)
    async def test_generation_error(
        self, failing_service: None, message: str, lang: str
    ) -> None:
        assert _sse_contents(await _post_stream(message)) == [
            STREAM_GENERATION_ERROR_MESSAGES[lang],
            "END",
        ]


class TestUnexpectedErrorLanguage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message,lang", LANGUAGE_CASES)
    async def test_unexpected_error(
        self, monkeypatch: pytest.MonkeyPatch, message: str, lang: str
    ) -> None:
        import llm_orchestration_service_api as api

        def broken_info(*args: object, **kwargs: object) -> None:
            raise RuntimeError("unexpected failure before streaming starts")

        # The first thing the endpoint does is log the request; failing there
        # sends it straight to the endpoint's catch-all error handler.
        monkeypatch.setattr(api.logger, "info", broken_info)

        assert _sse_contents(await _post_stream(message)) == [
            UNEXPECTED_ERROR_MESSAGES[lang],
            "END",
        ]
