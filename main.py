"""Entry point for the Apple XCStrings translation tool."""

import argparse

from apple_i8n.cli import run


def main() -> None:
    """Parse CLI arguments and run the translation pipeline."""
    parser = argparse.ArgumentParser(
        description="Translate Apple .xcstrings files using LLM",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    args = parser.parse_args()
    run(config_path=args.config)


if __name__ == "__main__":
    main()
