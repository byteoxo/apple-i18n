"""Parser and writer for Apple .xcstrings localization files."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranslationTask:
    """Represents a single translation task for one key and one target language."""

    key: str
    source_text: str
    target_language: str


@dataclass
class TranslationResult:
    """Holds the translated text for a specific key and language."""

    key: str
    target_language: str
    translated_text: str


# Regex pattern matching strings that consist only of format specifiers,
# punctuation, symbols, or whitespace — these should not be translated.
_SKIP_PATTERN = re.compile(
    r"^[\s%@lld.,·•∞⭐\-+/\d(){}[\]|:;!?\"'#&*=<>^~`\\]*$"
)


def load(path: str) -> dict:
    """Load and parse an .xcstrings JSON file.

    Args:
        path: File path to the .xcstrings file.

    Returns:
        Parsed JSON data as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"XCStrings file not found: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_languages(data: dict) -> set[str]:
    """Detect all language codes present in the xcstrings data.

    Scans every string entry's localizations to collect the full set
    of language codes used in the file.

    Args:
        data: Parsed xcstrings data.

    Returns:
        Set of language code strings (e.g., {"en", "de", "zh-Hans"}).
    """
    languages: set[str] = set()
    strings = data.get("strings", {})

    for _key, entry in strings.items():
        localizations = entry.get("localizations", {})
        languages.update(localizations.keys())

    return languages


def _should_skip_key(key: str, source_text: str | None) -> bool:
    """Determine whether a string key should be skipped for translation.

    Keys are skipped if:
    - They have no source text (empty localization body).
    - The source text is empty or consists only of format specifiers,
      punctuation, or symbols that don't need translation.

    Args:
        key: The string key.
        source_text: The source language text, or None if not present.

    Returns:
        True if the key should be skipped.
    """
    if source_text is None:
        return True

    if not source_text.strip():
        return True

    if _SKIP_PATTERN.match(source_text):
        return True

    return False


def find_missing_translations(
    data: dict,
    source_language: str,
    target_languages: set[str],
) -> list[TranslationTask]:
    """Find all string keys that are missing translations for target languages.

    For each key, checks whether a translation exists for every target language.
    Keys that are untranslatable (symbols, format strings, empty) are skipped.

    Args:
        data: Parsed xcstrings data.
        source_language: The base language code to translate from.
        target_languages: Set of language codes to translate into.

    Returns:
        List of TranslationTask objects representing needed translations.
    """
    tasks: list[TranslationTask] = []
    strings = data.get("strings", {})

    for key, entry in strings.items():
        localizations = entry.get("localizations", {})

        # Get source text
        source_loc = localizations.get(source_language, {})
        string_unit = source_loc.get("stringUnit", {})
        source_text = string_unit.get("value")

        if _should_skip_key(key, source_text):
            continue

        # Check each target language
        for lang in target_languages:
            if lang == source_language:
                continue

            lang_loc = localizations.get(lang, {})
            lang_unit = lang_loc.get("stringUnit", {})
            lang_state = lang_unit.get("state")

            # Skip if already translated
            if lang_state == "translated":
                continue

            tasks.append(
                TranslationTask(
                    key=key,
                    source_text=source_text,
                    target_language=lang,
                )
            )

    return tasks


def merge_translations(data: dict, results: list[TranslationResult]) -> dict:
    """Merge translation results back into the xcstrings data.

    Updates or creates localization entries for each result,
    setting the state to "translated".

    Args:
        data: The original parsed xcstrings data (modified in place).
        results: List of TranslationResult objects to merge.

    Returns:
        The modified data dictionary.
    """
    strings = data.get("strings", {})

    for result in results:
        entry = strings.get(result.key)
        if entry is None:
            continue

        if "localizations" not in entry:
            entry["localizations"] = {}

        entry["localizations"][result.target_language] = {
            "stringUnit": {
                "state": "translated",
                "value": result.translated_text,
            }
        }

    return data


def save(path: str, data: dict) -> None:
    """Save xcstrings data back to a JSON file.

    Uses Apple's formatting conventions: 2-space indentation,
    sorted keys, and a trailing newline.

    Args:
        path: File path to write to.
        data: The xcstrings data dictionary.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
