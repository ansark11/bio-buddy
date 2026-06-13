import logging
import time

import groq

logger = logging.getLogger(__name__)


def groq_call_with_retry(call_fn, max_retries: int = 3, wait_seconds: int = 60):
    """Execute a synchronous Groq API call, retrying on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return call_fn()
        except groq.RateLimitError:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Groq rate limit hit (attempt {attempt + 1}/{max_retries}), "
                    f"waiting {wait_seconds}s before retry..."
                )
                time.sleep(wait_seconds)
            else:
                logger.error("Groq rate limit exceeded after all retries")
                raise
