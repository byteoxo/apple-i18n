"""CLI orchestration: wires config, parser, and translator together."""

import asyncio
import logging
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from apple_i8n.config import AppConfig, load_config
from apple_i8n.translator import group_tasks_by_language, translate_all
from apple_i8n.xcstrings import (
    TranslationResult,
    detect_languages,
    find_missing_translations,
    load,
    merge_translations,
    save,
)

console = Console()


def setup_logging() -> None:
    """Configure logging with rich handler for colored, readable output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _print_summary_table(
    results: list[TranslationResult],
    target_languages: set[str],
    total_tasks: int,
    elapsed: float,
) -> None:
    """Print a summary table showing translation results per language.

    Args:
        results: List of completed translation results.
        target_languages: Set of target language codes.
        total_tasks: Total number of tasks that were planned.
        elapsed: Total elapsed time in seconds.
    """
    # Count results per language
    lang_counts: dict[str, int] = {}
    for r in results:
        lang_counts[r.target_language] = lang_counts.get(r.target_language, 0) + 1

    table = Table(title="Translation Summary")
    table.add_column("Language", style="cyan")
    table.add_column("Translated", style="green", justify="right")

    for lang in sorted(target_languages):
        count = lang_counts.get(lang, 0)
        table.add_row(lang, str(count))

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold]{len(results)}[/bold] / {total_tasks}")

    console.print()
    console.print(table)
    console.print(f"\n[dim]Completed in {elapsed:.1f}s[/dim]")


async def _run_async(config: AppConfig) -> None:
    """Async entry point for the translation pipeline.

    Args:
        config: Validated application configuration.
    """
    logger = logging.getLogger(__name__)

    # Step 1: Load xcstrings file
    console.print(
        f"\n[bold]Loading xcstrings file:[/bold] {config.translation.xcstrings_path}"
    )
    data = load(config.translation.xcstrings_path)

    source_lang = config.translation.source_language
    console.print(f"[bold]Source language:[/bold] {source_lang}")

    # Step 2: Detect languages
    all_languages = detect_languages(data)
    target_languages = all_languages - {source_lang}

    if not target_languages:
        console.print("[yellow]No target languages found. Nothing to translate.[/yellow]")
        return

    console.print(
        f"[bold]Target languages ({len(target_languages)}):[/bold] "
        f"{', '.join(sorted(target_languages))}"
    )

    # Step 3: Find missing translations
    tasks = find_missing_translations(data, source_lang, target_languages)

    if not tasks:
        console.print("[green]All translations are up to date. Nothing to do.[/green]")
        return

    # Group and summarize
    groups = group_tasks_by_language(tasks)
    console.print(f"\n[bold]Missing translations: {len(tasks)} total[/bold]")
    for lang in sorted(groups.keys()):
        console.print(f"  {lang}: {len(groups[lang])} keys")

    # Step 4: Translate with progress bar
    console.print()
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        progress_task = progress.add_task("Translating...", total=len(tasks))

        async def on_progress(count: int) -> None:
            """Callback to advance the progress bar."""
            progress.advance(progress_task, advance=count)

        results = await translate_all(
            tasks=tasks,
            llm_config=config.llm,
            source_language=source_lang,
            batch_size=config.translation.batch_size,
            max_concurrency=config.translation.max_concurrency,
            progress_callback=on_progress,
        )

    elapsed = time.time() - start_time

    # Step 5: Merge and save
    if results:
        merge_translations(data, results)
        save(config.translation.xcstrings_path, data)
        console.print(
            f"\n[green bold]Saved translations to {config.translation.xcstrings_path}[/green bold]"
        )
    else:
        console.print("\n[yellow]No translations were produced.[/yellow]")

    # Step 6: Summary
    _print_summary_table(results, target_languages, len(tasks), elapsed)


def run(config_path: str = "config.yaml") -> None:
    """Main synchronous entry point for the CLI.

    Loads configuration and runs the async translation pipeline.

    Args:
        config_path: Path to the YAML configuration file.
    """
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        console.print("[bold cyan]Apple XCStrings Translation Tool[/bold cyan]")
        console.print("[dim]─" * 50 + "[/dim]")

        config = load_config(config_path)
        logger.info("Configuration loaded from %s", config_path)
        logger.info("Using model: %s", config.llm.model)

        asyncio.run(_run_async(config))

    except FileNotFoundError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise SystemExit(1)
    except ValueError as e:
        console.print(f"[red bold]Configuration error:[/red bold] {e}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Translation cancelled by user.[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        raise SystemExit(1)
