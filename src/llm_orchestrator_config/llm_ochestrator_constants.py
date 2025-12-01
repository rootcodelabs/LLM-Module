OUT_OF_SCOPE_MESSAGE = (
    "I apologize, but I’m unable to provide a complete response because the available "
    "context does not sufficiently cover your request. Please try rephrasing or providing more details."
)

TECHNICAL_ISSUE_MESSAGE = (
    "Technical issue with response generation\n"
    "I apologize, but I’m currently unable to generate a response due to a temporary technical issue. "
    "Please try again in a moment."
)

UNKNOWN_SOURCE = "Unknown source"

INPUT_GUARDRAIL_VIOLATION_MESSAGE = "I apologize, but I'm unable to assist with that request as it violates our usage policies."

OUTPUT_GUARDRAIL_VIOLATION_MESSAGE = "I apologize, but I'm unable to provide a response as it may violate our usage policies."

GUARDRAILS_BLOCKED_PHRASES = [
    "i'm sorry, i can't respond to that",
    "i cannot respond to that",
    "i cannot help with that",
    "this is against policy",
]

# Streaming configuration
STREAMING_ALLOWED_ENVS = {"production"}
TEST_DEPLOYMENT_ENVIRONMENT = "testing"

# Stream limit error messages
STREAM_TIMEOUT_MESSAGE = (
    "I apologize, but generating your response is taking longer than expected. "
    "Please try asking your question in a simpler way or break it into smaller parts."
)

STREAM_TOKEN_LIMIT_MESSAGE = (
    "I apologize, but I've reached the maximum response length for this question. "
    "The answer provided above covers the main points, but some details may have been abbreviated. "
    "Please feel free to ask follow-up questions for more information."
)

STREAM_SIZE_LIMIT_MESSAGE = (
    "I apologize, but your request is too large to process. "
    "Please shorten your message or reduce the conversation history and try again."
)

STREAM_CAPACITY_EXCEEDED_MESSAGE = (
    "I apologize, but our service is currently at capacity. "
    "Please wait a moment and try again. Thank you for your patience."
)

STREAM_USER_LIMIT_EXCEEDED_MESSAGE = (
    "I apologize, but you have reached the maximum number of concurrent conversations. "
    "Please wait for your existing conversations to complete before starting a new one."
)

# Rate limiting error messages
RATE_LIMIT_REQUESTS_EXCEEDED_MESSAGE = (
    "I apologize, but you've made too many requests in a short time. "
    "Please wait a moment before trying again."
)

RATE_LIMIT_TOKENS_EXCEEDED_MESSAGE = (
    "I apologize, but you're sending requests too quickly. "
    "Please slow down and try again in a few seconds."
)

# Validation error messages
VALIDATION_MESSAGE_TOO_SHORT = "Please provide a message with at least a few characters so I can understand your request."

VALIDATION_MESSAGE_TOO_LONG = (
    "Your message is too long. Please shorten it and try again."
)

VALIDATION_MESSAGE_INVALID_FORMAT = (
    "Please provide a valid message without special formatting."
)

VALIDATION_MESSAGE_GENERIC = "Please provide a valid message for your request."

VALIDATION_CONVERSATION_HISTORY_ERROR = (
    "There was an issue with the conversation history format. Please try again."
)

VALIDATION_REQUEST_TOO_LARGE = "Your request is too large. Please reduce the message size or conversation history and try again."

VALIDATION_REQUIRED_FIELDS_MISSING = "Required information is missing from your request. Please ensure all required fields are provided."

VALIDATION_GENERIC_ERROR = "I apologize, but I couldn't process your request. Please check your input and try again."

# Service endpoints
RAG_SEARCH_RESQL = "http://resql:8082/rag-search"
RAG_SEARCH_RUUTER_PUBLIC = "http://ruuter-public:8086/rag-search"
RAG_SEARCH_RUUTER_PRIVATE = "http://ruuter-private:8088/rag-search"
