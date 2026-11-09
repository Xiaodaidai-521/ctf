"""Legacy usage normalization; direct provider construction is disabled."""


def extract_usage(response):
    """Normalize LangChain/OpenAI usage without estimating missing values."""
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
    if not usage:
        metadata = getattr(response, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")
    normalized = {
        "prompt_tokens": int(prompt) if isinstance(prompt, int) else None,
        "completion_tokens": int(completion) if isinstance(completion, int) else None,
        "total_tokens": int(total) if isinstance(total, int) else None,
    }
    return normalized if any(value is not None for value in normalized.values()) else None


class DisabledProvider:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('DIRECT_PROVIDER_DISABLED')
