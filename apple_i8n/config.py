"""Configuration loading and validation for the xcstrings translation tool."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    """LLM API configuration."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class TranslationConfig:
    """Translation task configuration."""

    source_language: str = "en"
    xcstrings_path: str = "./Localizable.xcstrings"
    batch_size: int = 20
    max_concurrency: int = 5


@dataclass
class AppConfig:
    """Top-level application configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load configuration from a YAML file.

    Environment variable LLM_API_KEY overrides the api_key in the config file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated AppConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required configuration values are missing.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Parse LLM config
    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        base_url=llm_raw.get("base_url", LLMConfig.base_url),
        api_key=llm_raw.get("api_key", LLMConfig.api_key),
        model=llm_raw.get("model", LLMConfig.model),
    )

    # Environment variable override for API key
    env_api_key = os.environ.get("LLM_API_KEY")
    if env_api_key:
        llm.api_key = env_api_key

    # Parse translation config
    trans_raw = raw.get("translation", {})
    translation = TranslationConfig(
        source_language=trans_raw.get("source_language", TranslationConfig.source_language),
        xcstrings_path=trans_raw.get("xcstrings_path", TranslationConfig.xcstrings_path),
        batch_size=trans_raw.get("batch_size", TranslationConfig.batch_size),
        max_concurrency=trans_raw.get("max_concurrency", TranslationConfig.max_concurrency),
    )

    config = AppConfig(llm=llm, translation=translation)
    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    """Validate that all required configuration values are present.

    Args:
        config: The configuration to validate.

    Raises:
        ValueError: If validation fails.
    """
    if not config.llm.api_key or config.llm.api_key == "sk-...":
        raise ValueError(
            "LLM API key is not configured. "
            "Set it in config.yaml or via the LLM_API_KEY environment variable."
        )

    if not config.llm.base_url:
        raise ValueError("LLM base_url must not be empty.")

    if not config.llm.model:
        raise ValueError("LLM model must not be empty.")

    if not config.translation.source_language:
        raise ValueError("source_language must not be empty.")

    if config.translation.batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    if config.translation.max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1.")
