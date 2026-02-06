"""LLM-based translation engine with batch processing and concurrency control."""

import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from apple_i8n.config import LLMConfig
from apple_i8n.xcstrings import TranslationResult, TranslationTask

logger = logging.getLogger(__name__)

# Language code to human-readable name mapping for better LLM prompts
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "pt-BR": "Brazilian Portuguese",
    "pt-PT": "European Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ru": "Russian",
    "ar": "Arabic",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "tr": "Turkish",
    "pl": "Polish",
    "uk": "Ukrainian",
    "cs": "Czech",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nb": "Norwegian Bokmål",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "ro": "Romanian",
    "sk": "Slovak",
    "ca": "Catalan",
    "hr": "Croatian",
    "bg": "Bulgarian",
}


def _get_language_name(code: str) -> str:
    """Get human-readable language name from a language code.

    Args:
        code: BCP 47 language code.

    Returns:
        Human-readable name, or the code itself if not found.
    """
    return LANGUAGE_NAMES.get(code, code)


def _build_system_prompt(source_language: str, target_language: str) -> str:
    """Build the system prompt for the translation LLM request.

    Args:
        source_language: Source language code.
        target_language: Target language code.

    Returns:
        System prompt string.
    """
    source_name = _get_language_name(source_language)
    target_name = _get_language_name(target_language)

    return (
        f"You are a professional app localizer specializing in Apple platform applications. "
        f"Translate the following strings from {source_name} to {target_name}.\n\n"
        f"Rules:\n"
        f"1. Preserve ALL format specifiers exactly as they appear: %@, %lld, %d, %f, %%, %1$@, %2$lld, etc.\n"
        f"2. Preserve leading/trailing whitespace and newlines.\n"
        f"3. Keep technical terms, brand names, and proper nouns unchanged unless they have "
        f"a well-known localized form.\n"
        f"4. Use natural, idiomatic {target_name} appropriate for a macOS/iOS app UI.\n"
        f"5. Be concise — UI strings should be short and clear.\n\n"
        f"You will receive a JSON object where keys are string identifiers and values are "
        f"the {source_name} texts to translate.\n"
        f"Respond with ONLY a JSON object using the same keys, with translated {target_name} "
        f"values. No markdown, no explanation, just the JSON object."
    )


def _build_user_prompt(batch: dict[str, str]) -> str:
    """Build the user prompt containing the batch of strings to translate.

    Args:
        batch: Dictionary mapping string keys to source text.

    Returns:
        JSON-formatted string.
    """
    return json.dumps(batch, ensure_ascii=False, indent=2)


def _parse_llm_response(response_text: str, expected_keys: list[str]) -> dict[str, str]:
    """Parse the LLM response and extract translated strings.

    Handles cases where the LLM wraps the response in markdown code fences.

    Args:
        response_text: Raw text from the LLM response.
        expected_keys: List of keys we expect in the response.

    Returns:
        Dictionary mapping string keys to translated text.

    Raises:
        ValueError: If the response cannot be parsed as valid JSON.
    """
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:500]}")

    if not isinstance(result, dict):
        raise ValueError(f"LLM response is not a JSON object: {type(result)}")

    # Warn about missing keys
    for key in expected_keys:
        if key not in result:
            logger.warning("LLM response missing key: %s", key)

    return {k: str(v) for k, v in result.items() if k in expected_keys}


async def _translate_batch(
    client: AsyncOpenAI,
    model: str,
    source_language: str,
    target_language: str,
    batch: dict[str, str],
    max_retries: int = 3,
) -> dict[str, str]:
    """Translate a batch of strings using the LLM API.

    Implements retry with exponential backoff on transient errors.

    Args:
        client: AsyncOpenAI client instance.
        model: Model name to use.
        source_language: Source language code.
        target_language: Target language code.
        batch: Dictionary mapping string keys to source text.
        max_retries: Maximum number of retry attempts.

    Returns:
        Dictionary mapping string keys to translated text.

    Raises:
        RuntimeError: If all retry attempts are exhausted.
    """
    system_prompt = _build_system_prompt(source_language, target_language)
    user_prompt = _build_user_prompt(batch)
    expected_keys = list(batch.keys())

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty response")

            return _parse_llm_response(content, expected_keys)

        except Exception as e:
            last_error = e
            wait_time = 2 ** attempt
            logger.warning(
                "Translation attempt %d/%d failed for %s (batch size %d): %s. "
                "Retrying in %ds...",
                attempt + 1,
                max_retries,
                target_language,
                len(batch),
                str(e),
                wait_time,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)

    raise RuntimeError(
        f"Failed to translate batch after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


def group_tasks_by_language(
    tasks: list[TranslationTask],
) -> dict[str, list[TranslationTask]]:
    """Group translation tasks by target language.

    Args:
        tasks: List of all translation tasks.

    Returns:
        Dictionary mapping language codes to lists of tasks.
    """
    groups: dict[str, list[TranslationTask]] = {}
    for task in tasks:
        groups.setdefault(task.target_language, []).append(task)
    return groups


def _chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of the given size.

    Args:
        items: List to split.
        chunk_size: Maximum number of items per chunk.

    Returns:
        List of chunks.
    """
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


async def translate_all(
    tasks: list[TranslationTask],
    llm_config: LLMConfig,
    source_language: str,
    batch_size: int = 20,
    max_concurrency: int = 5,
    progress_callback: Any = None,
) -> list[TranslationResult]:
    """Translate all tasks concurrently with batching and rate limiting.

    Groups tasks by target language, splits into batches, and processes
    them concurrently with a semaphore to limit parallelism.

    Args:
        tasks: List of TranslationTask objects.
        llm_config: LLM configuration.
        source_language: Source language code.
        batch_size: Number of keys per LLM request.
        max_concurrency: Maximum concurrent API calls.
        progress_callback: Optional async callable(count) to report progress.

    Returns:
        List of TranslationResult objects.
    """
    if not tasks:
        logger.info("No translation tasks to process.")
        return []

    client = AsyncOpenAI(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
    )

    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[TranslationResult] = []
    results_lock = asyncio.Lock()

    groups = group_tasks_by_language(tasks)

    async def process_batch(
        target_language: str,
        batch_tasks: list[TranslationTask],
    ) -> None:
        """Process a single batch of translation tasks."""
        batch = {t.key: t.source_text for t in batch_tasks}

        async with semaphore:
            try:
                translations = await _translate_batch(
                    client=client,
                    model=llm_config.model,
                    source_language=source_language,
                    target_language=target_language,
                    batch=batch,
                )

                batch_results = [
                    TranslationResult(
                        key=key,
                        target_language=target_language,
                        translated_text=text,
                    )
                    for key, text in translations.items()
                ]

                async with results_lock:
                    results.extend(batch_results)

                if progress_callback:
                    await progress_callback(len(batch_results))

                logger.debug(
                    "Translated batch of %d keys to %s",
                    len(batch_results),
                    target_language,
                )

            except Exception as e:
                logger.error(
                    "Failed to translate batch of %d keys to %s: %s",
                    len(batch_tasks),
                    target_language,
                    str(e),
                )

    # Build all batch coroutines
    coroutines = []
    for language, lang_tasks in groups.items():
        batches = _chunk_list(lang_tasks, batch_size)
        for batch_tasks in batches:
            coroutines.append(process_batch(language, batch_tasks))

    logger.info(
        "Starting translation: %d tasks across %d languages in %d batches "
        "(concurrency=%d)",
        len(tasks),
        len(groups),
        len(coroutines),
        max_concurrency,
    )

    # Run all batches concurrently (semaphore controls actual parallelism)
    await asyncio.gather(*coroutines)

    return results
