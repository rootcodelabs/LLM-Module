# Endpoint configuration lives in constants.ini (shared with Ruuter).
# The loader is a standalone module so the cron-manager container, which has
# none of this package's dependencies, can mount and reuse the same code.
# Re-exported here for backwards compatibility with existing imports.
from src.constants_loader import CONSTANTS_INI_PATH, get_constant  # noqa: F401

# Multilingual message dictionaries
OUT_OF_SCOPE_MESSAGES = {
    "et": "Vabandust, kuid mul pole piisavalt konteksti, et teie küsimusele vastata. Palun püüdke ümber sõnastada või lisage rohkem üksikasju.",
    "ru": "Извините, но у меня недостаточно контекста для ответа на ваш вопрос. Пожалуйста, попробуйте переформулировать или предоставить больше деталей.",
    "en": "I apologize, but I'm unable to provide a complete response because the available context does not sufficiently cover your request. Please try rephrasing or providing more details.",
}

TECHNICAL_ISSUE_MESSAGES = {
    "et": "Tehniline probleem vastuse genereerimisel\nVabandust, kuid ma ei saa praegu vastust genereerida ajutise tehnilise probleemi tõttu. Palun proovige mõne hetke pärast uuesti.",
    "ru": "Техническая проблема при генерации ответа\nИзвините, в настоящее время я не могу сгенерировать ответ из-за временной технической проблемы. Пожалуйста, попробуйте еще раз через мгновение.",
    "en": "Technical issue with response generation\nI apologize, but I'm currently unable to generate a response due to a temporary technical issue. Please try again in a moment.",
}

INPUT_GUARDRAIL_VIOLATION_MESSAGES = {
    "et": "Vabandust, kuid ma ei saa selle taotlusega aidata, kuna see rikub meie kasutustingimusi.",
    "ru": "Извините, но я не могу помочь с этим запросом, так как он нарушает нашу политику использования.",
    "en": "I apologize, but I'm unable to assist with that request as it violates our usage policies.",
}

OUTPUT_GUARDRAIL_VIOLATION_MESSAGES = {
    "et": "Vabandust, kuid ma ei saa vastust anda, kuna see võib rikkuda meie kasutustingimusi.",
    "ru": "Извините, но я не могу предоставить ответ, так как он может нарушить нашу политику использования.",
    "en": "I apologize, but I'm unable to provide a response as it may violate our usage policies.",
}

# Shown when the output guardrail blocks a response that has ALREADY started
# streaming (violation detected mid-answer, after the first chunk).
OUTPUT_GUARDRAIL_VIOLATION_PARTIAL_MESSAGES = {
    "et": "Vabandust, kuid ma ei saa ülejäänud vastust genereerida, kuna see võib rikkuda meie kasutustingimusi.",
    "ru": "Извините, но я не могу сгенерировать оставшуюся часть ответа, так как это может нарушить нашу политику использования.",
    "en": "I apologize, but I'm unable to generate the rest of the response as it may violate our usage policies.",
}

# Query validation messages - single generic message for all rejection types
# (empty queries, special characters only, too short, repetitive characters)
QUERY_VALIDATION_FAILED_MESSAGES = {
    "et": "Palun esitage kehtiv küsimus või sõnum, et ma saaksin teid aidata.",
    "en": "Please provide a valid question or reply so I can assist you.",
    "ru": "Пожалуйста, введите корректный вопрос или сообщение, чтобы я мог вам помочь.",
}

# ---------------------------------------------------------------------------
# Service workflow messages (Layer 1)
#
# Usage: import the dictionary alongside get_localized_message, then look it up
# with the language detected for the request. That language is stamped once per
# request onto the "_detected_language" attribute (see process_orchestration_request
# in llm_orchestration_service.py) and read back with getattr, defaulting to "en".
# Unknown language codes fall back to Estonian - see get_localized_message below.
#
# Any new message dictionary added here MUST also be registered in
# _HISTORY_EXCLUDED_MESSAGES (llm_orchestration_service.py) or the failed
# exchange will be persisted to Dragonfly and replayed to the prompt refiner on
# the user's next turn.
# ---------------------------------------------------------------------------

# No service in the catalogue matches the user's request.
SERVICE_NOT_FOUND_MESSAGES = {
    "et": "Ma ei leidnud teie päringule vastavat teenust. Palun sõnastage küsimus ümber või küsige mõne muu teema kohta.",
    "ru": "Я не нашёл службы, соответствующей вашему запросу. Пожалуйста, переформулируйте вопрос или спросите о другой теме.",
    "en": "I couldn't find a service that matches your request. Please try rephrasing, or ask about a different topic.",
}

# A matching service exists but its current_state is not 'active'.
SERVICE_VALIDATION_FAILED_MESSAGES = {
    "et": "See teenus ei ole hetkel saadaval. Palun proovige hiljem uuesti.",
    "ru": "Эта услуга сейчас недоступна. Пожалуйста, попробуйте позже.",
    "en": "This service is currently unavailable. Please try again later.",
}

# The service call exceeded its timeout budget.
SERVICE_TIMEOUT_ERROR_MESSAGES = {
    "et": "Teenuse vastus võtab oodatust kauem aega. Palun proovige hetke pärast uuesti.",
    "ru": "Служба отвечает дольше обычного. Пожалуйста, попробуйте через мгновение.",
    "en": "The service is taking longer than expected to respond. Please try again in a moment.",
}

# The service was reached but returned an error response.
SERVICE_EXECUTION_ERROR_MESSAGES = {
    "et": "Teie päringu täitmisel läks midagi valesti. Palun proovige uuesti.",
    "ru": "При выполнении вашего запроса произошла ошибка. Пожалуйста, попробуйте ещё раз.",
    "en": "Something went wrong while completing your request. Please try again.",
}

# The LLM could not extract the entities/slots the service requires.
ENTITY_EXTRACTION_FAILED_MESSAGES = {
    "et": "Vajan jätkamiseks veidi rohkem teavet. Kas saaksite täpsustada, mida soovite?",
    "ru": "Мне нужно немного больше информации, чтобы продолжить. Уточните, пожалуйста, что вам нужно.",
    "en": "I need a little more detail to continue. Could you tell me more about what you need?",
}

# ---------------------------------------------------------------------------
# Context workflow messages (Layer 3)
# ---------------------------------------------------------------------------

# The query refers back to the conversation, but no clear answer can be derived.
INSUFFICIENT_CONTEXT_MESSAGES = {
    "et": "Ma ei ole kindel, millele te viitate. Kas saaksite küsimuse täpsemalt ümber sõnastada?",
    "ru": "Я не уверен, о чём именно вы спрашиваете. Не могли бы вы переформулировать вопрос подробнее?",
    "en": "I'm not sure what you're referring to. Could you rephrase your question with more detail?",
}

# The query refers back to the conversation, but there is no history at all.
NO_CONTEXT_AVAILABLE_MESSAGES = {
    "et": "Me ei ole veel midagi arutanud. Kas saaksite esitada oma küsimuse tervikuna?",
    "ru": "Мы ещё ничего не обсуждали. Не могли бы вы задать вопрос полностью?",
    "en": "We haven't discussed anything yet. Could you ask your question in full?",
}

# Legacy constants for backward compatibility (English defaults)
OUT_OF_SCOPE_MESSAGE = OUT_OF_SCOPE_MESSAGES["en"]
TECHNICAL_ISSUE_MESSAGE = TECHNICAL_ISSUE_MESSAGES["en"]
INPUT_GUARDRAIL_VIOLATION_MESSAGE = INPUT_GUARDRAIL_VIOLATION_MESSAGES["en"]
OUTPUT_GUARDRAIL_VIOLATION_MESSAGE = OUTPUT_GUARDRAIL_VIOLATION_MESSAGES["en"]
OUTPUT_GUARDRAIL_VIOLATION_PARTIAL_MESSAGE = (
    OUTPUT_GUARDRAIL_VIOLATION_PARTIAL_MESSAGES["en"]
)

UNKNOWN_SOURCE = "Unknown source"

GUARDRAILS_BLOCKED_PHRASES = [
    "i'm sorry, i can't respond to that",
    "i cannot respond to that",
    "i cannot help with that",
    "this is against policy",
]

# Markers emitted by NeMo Guardrails when `enable_rails_exceptions: true` and an
# output rail blocks a chunk mid-stream. NeMo yields this as a *content chunk*
# (not an exception), e.g.:
#   {"error": {"message": "Blocked by self check output rails.",
#              "type": "guardrails_violation", "code": "content_blocked"}}
GUARDRAILS_EXCEPTION_MARKERS = [
    "guardrails_violation",
    "content_blocked",
    "blocked by self check",
]


def is_output_guardrail_violation(chunk: str) -> bool:
    """Return True if a streamed chunk indicates an output guardrail block.

    Handles two cases:
    1. Bot refusal phrases (short refusals like "I cannot respond to that").
    2. NeMo's `enable_rails_exceptions` JSON payload emitted as a content chunk
       (e.g. "Blocked by self check output rails." / guardrails_violation), which
       can be arbitrarily long and is therefore missed by the phrase/length check.
    """
    if not isinstance(chunk, str):
        return False

    chunk_lower = chunk.strip().lower()
    if not chunk_lower:
        return False

    # Case 2: NeMo exception payload — check first, no length gate.
    if any(marker in chunk_lower for marker in GUARDRAILS_EXCEPTION_MARKERS):
        return True

    # Case 1: short bot refusal phrases.
    return any(
        phrase.lower() in chunk_lower and len(chunk_lower) <= len(phrase.lower()) + 20
        for phrase in GUARDRAILS_BLOCKED_PHRASES
    )


# Streaming configuration
STREAMING_ALLOWED_ENVS = {"production", "testing"}
TEST_DEPLOYMENT_ENVIRONMENT = "testing"
PRODUCTION_DEPLOYMENT_ENVIRONMENT = "production"

# ---------------------------------------------------------------------------
# API-level error messages (streaming endpoint, rate limiting, request validation)
#
# These are produced before or outside the orchestration pipeline, so callers
# detect the language from the user's message themselves (see
# llm_orchestration_service_api.py). Register every dict here in
# _HISTORY_EXCLUDED_MESSAGES (src/orchestration/constants.py).
# ---------------------------------------------------------------------------

# The stream exceeded its total or idle time budget.
STREAM_TIMEOUT_MESSAGES = {
    "et": "Vabandust, kuid vastuse koostamine võtab oodatust kauem aega. Palun proovige küsimus lihtsamalt sõnastada või jagage see väiksemateks osadeks.",
    "ru": "Извините, но подготовка ответа занимает больше времени, чем ожидалось. Пожалуйста, попробуйте сформулировать вопрос проще или разбейте его на несколько частей.",
    "en": "I apologize, but generating your response is taking longer than expected. Please try asking your question in a simpler way or break it into smaller parts.",
}

# The streamed answer hit the maximum token count and was cut short.
STREAM_TOKEN_LIMIT_MESSAGES = {
    "et": "Vabandust, kuid vastus jõudis selle küsimuse puhul maksimaalse pikkuseni. Ülaltoodud vastus hõlmab peamisi punkte, kuid mõned üksikasjad võivad olla lühendatud. Lisateabe saamiseks esitage julgelt täpsustavaid küsimusi.",
    "ru": "Извините, но ответ на этот вопрос достиг максимальной длины. Приведённый выше ответ охватывает основные моменты, но некоторые детали могли быть сокращены. Задавайте уточняющие вопросы, чтобы получить больше информации.",
    "en": "I apologize, but I've reached the maximum response length for this question. The answer provided above covers the main points, but some details may have been abbreviated. Please feel free to ask follow-up questions for more information.",
}

# Too many requests from the same author within the rate-limit window.
RATE_LIMIT_REQUESTS_EXCEEDED_MESSAGES = {
    "et": "Vabandust, kuid olete lühikese aja jooksul saatnud liiga palju päringuid. Palun oodake hetk ja proovige uuesti.",
    "ru": "Извините, но вы отправили слишком много запросов за короткое время. Пожалуйста, подождите немного и попробуйте снова.",
    "en": "I apologize, but you've made too many requests in a short time. Please wait a moment before trying again.",
}

# Too many tokens from the same author within the rate-limit window.
RATE_LIMIT_TOKENS_EXCEEDED_MESSAGES = {
    "et": "Vabandust, kuid saadate päringuid liiga kiiresti. Palun oodake mõni sekund ja proovige uuesti.",
    "ru": "Извините, но вы отправляете запросы слишком быстро. Пожалуйста, подождите несколько секунд и попробуйте снова.",
    "en": "I apologize, but you're sending requests too quickly. Please slow down and try again in a few seconds.",
}

# The orchestration service is not initialised or not available.
ORCHESTRATION_SERVICE_UNAVAILABLE_MESSAGES = {
    "et": "Vabandust, kuid teenus ei ole hetkel saadaval. Palun proovige hiljem uuesti.",
    "ru": "Извините, но сервис в данный момент недоступен. Пожалуйста, попробуйте позже.",
    "en": "I apologize, but the service is not available at the moment. Please try again later.",
}

# Streaming failed with an unexpected error while generating the answer.
STREAM_GENERATION_ERROR_MESSAGES = {
    "et": "Vabandust, kuid vastuse koostamisel tekkis probleem. Palun proovige uuesti.",
    "ru": "Извините, но при подготовке ответа возникла проблема. Пожалуйста, попробуйте снова.",
    "en": "I apologize, but I encountered an issue while generating your response. Please try again.",
}

# Any other unexpected error in the streaming endpoint.
UNEXPECTED_ERROR_MESSAGES = {
    "et": "Vabandust, kuid tekkis ootamatu probleem. Palun proovige uuesti.",
    "ru": "Извините, но возникла непредвиденная проблема. Пожалуйста, попробуйте снова.",
    "en": "I apologize, but I encountered an unexpected issue. Please try again.",
}

# Request validation messages (shown when the request body fails validation)
VALIDATION_TOO_SHORT_MESSAGES = {
    "et": "Palun kirjutage vähemalt paar tähemärki, et ma saaksin teie päringust aru.",
    "ru": "Пожалуйста, напишите хотя бы несколько символов, чтобы я мог понять ваш запрос.",
    "en": "Please provide a message with at least a few characters so I can understand your request.",
}

VALIDATION_TOO_LONG_MESSAGES = {
    "et": "Teie sõnum on liiga pikk. Palun lühendage seda ja proovige uuesti.",
    "ru": "Ваше сообщение слишком длинное. Пожалуйста, сократите его и попробуйте снова.",
    "en": "Your message is too long. Please shorten it and try again.",
}

VALIDATION_INVALID_FORMAT_MESSAGES = {
    "et": "Palun sisestage kehtiv sõnum ilma erivorminduseta.",
    "ru": "Пожалуйста, введите корректное сообщение без специального форматирования.",
    "en": "Please provide a valid message without special formatting.",
}

VALIDATION_INVALID_INPUT_MESSAGES = {
    "et": "Palun sisestage oma päringu jaoks kehtiv sõnum.",
    "ru": "Пожалуйста, введите корректное сообщение для вашего запроса.",
    "en": "Please provide a valid message for your request.",
}

VALIDATION_CONVERSATION_HISTORY_ERROR_MESSAGES = {
    "et": "Vestluse ajaloo vorminguga tekkis probleem. Palun proovige uuesti.",
    "ru": "Возникла проблема с форматом истории разговора. Пожалуйста, попробуйте снова.",
    "en": "There was an issue with the conversation history format. Please try again.",
}

VALIDATION_REQUEST_TOO_LARGE_MESSAGES = {
    "et": "Teie päring on liiga suur. Palun lühendage sõnumit või vestluse ajalugu ja proovige uuesti.",
    "ru": "Ваш запрос слишком большой. Пожалуйста, сократите сообщение или историю разговора и попробуйте снова.",
    "en": "Your request is too large. Please reduce the message size or conversation history and try again.",
}

VALIDATION_REQUIRED_FIELDS_MISSING_MESSAGES = {
    "et": "Päringust puudub vajalik teave. Palun veenduge, et kõik nõutud väljad on täidetud.",
    "ru": "В запросе отсутствует необходимая информация. Пожалуйста, убедитесь, что все обязательные поля заполнены.",
    "en": "Required information is missing from your request. Please ensure all required fields are provided.",
}

VALIDATION_GENERIC_ERROR_MESSAGES = {
    "et": "Vabandust, kuid ma ei saanud teie päringut töödelda. Palun kontrollige sisestatud andmeid ja proovige uuesti.",
    "ru": "Извините, но я не смог обработать ваш запрос. Пожалуйста, проверьте введённые данные и попробуйте снова.",
    "en": "I apologize, but I couldn't process your request. Please check your input and try again.",
}

VALIDATION_INVALID_DATA_FORMAT_MESSAGES = {
    "et": "Vabandust, kuid ma ei saanud teie päringut vigase andmevormingu tõttu töödelda. Palun kontrollige sisestatud andmeid ja proovige uuesti.",
    "ru": "Извините, но я не смог обработать ваш запрос из-за неверного формата данных. Пожалуйста, проверьте введённые данные и попробуйте снова.",
    "en": "I apologize, but I couldn't process your request due to invalid data format. Please check your input and try again.",
}

# Connection status / budget enforcement messages
CONNECTION_INACTIVE_MESSAGES = {
    "et": "Vabandust, kuid teenus ei ole praegu saadaval. Palun võtke ühendust administraatoriga.",
    "ru": "Извините, но сервис в настоящее время недоступен. Пожалуйста, обратитесь к администратору.",
    "en": "I apologize, but the service is currently unavailable. Please contact your administrator.",
}

BUDGET_EXCEEDED_MESSAGES = {
    "et": "Vabandust, kuid teenuse eelarve on ületatud. Palun võtke ühendust administraatoriga.",
    "ru": "Извините, но бюджет сервиса превышен. Пожалуйста, обратитесь к администратору.",
    "en": "I apologize, but the service budget has been exceeded. Please contact your administrator.",
}

CONNECTION_INACTIVE_MESSAGE = CONNECTION_INACTIVE_MESSAGES["en"]
BUDGET_EXCEEDED_MESSAGE = BUDGET_EXCEEDED_MESSAGES["en"]


# Helper function to get localized messages
def get_localized_message(message_dict: dict, language_code: str = "et") -> str:
    """
    Get message in the specified language, fallback to Estonian.

    Args:
        message_dict: Dictionary with language codes as keys
        language_code: Language code ('et', 'ru', 'en')

    Returns:
        Localized message string
    """
    return message_dict.get(language_code, message_dict.get("et", ""))


# Service endpoints (configured in constants.ini)
RAG_SEARCH_RESQL = get_constant("RAG_SEARCH_RESQL")
RAG_SEARCH_RUUTER_PUBLIC = get_constant("RAG_SEARCH_RUUTER_PUBLIC")
RAG_SEARCH_RUUTER_PRIVATE = get_constant("RAG_SEARCH_RUUTER_PRIVATE")
QDRANT_URL = get_constant("QDRANT_URL")
LANGFUSE_URL = get_constant("LANGFUSE_URL")  # used when the Vault secret has no host

# Custom Prompt Configuration
RUUTER_PROMPT_CONFIG_ENDPOINT = (
    f"{RAG_SEARCH_RUUTER_PUBLIC}/llm-connections/prompts/get-prompt"
)
PROMPT_CONFIG_CACHE_TTL = 300  # 5 minutes cache
