# Apple i18n — Let AI Handle Your Localization

[中文文档](README-ZH.md)

If you're building for Apple platforms — iOS, macOS, iPadOS, watchOS, tvOS, visionOS — you know the drill. Localization is tedious. You've got a `Localizable.xcstrings` file with a bunch of keys, and somehow you need translations for every language your app supports.

That's what this tool does. Pick a base language (say `en`, `zh-Hans`, whatever you've already got in your file), and it uses an LLM to translate everything into all the other languages. Results get written straight back into your `.xcstrings` file. Just copy it back to Xcode and you're done.

## What It Does

- Reads your `.xcstrings` file and figures out which languages are in there and what's still missing
- Calls an LLM (any OpenAI-compatible API) to fill in the gaps
- Merges translations back into your file — formatting stays clean
- Skips stuff that shouldn't be translated: symbols, format specifiers (`%@`, `%lld`, etc.)
- Won't re-translate things that are already done — safe to run as many times as you want
- Batches requests and runs them concurrently, so it's fast
- Shows a progress bar and a nice summary when it's done

## How to Use

### 1. Install uv

You'll need [uv](https://docs.astral.sh/uv/), a super fast Python package manager. If you don't have it yet, check the official docs at `https://docs.astral.sh/uv/` for installation options.

On macOS with Homebrew:

```bash
brew install uv
```

### 2. Clone & Install Dependencies

```bash
git clone <>
cd apple-i8n
uv sync
```

`uv sync` sets up a virtual environment and installs everything automatically. No extra steps needed.

### 3. Configure

Copy the example config:

```bash
cp config-example.yaml config.yaml
```

Then edit `config.yaml`:

```yaml
llm:
  base_url: "https://api.openai.com/v1"   # Any OpenAI-compatible endpoint works
  api_key: "sk-your-key"                   # Your API key
  model: "gpt-4o-mini"                     # Model to use

translation:
  source_language: "en"                    # Translate FROM this language
  xcstrings_path: "./Localizable.xcstrings" # Path to your xcstrings file
  batch_size: 20                           # Keys per API request
  max_concurrency: 5                       # Max parallel requests
```

**About the source language:** `source_language` is your "ground truth". Set it to `en` and everything gets translated from English. Set it to `zh-Hans` and it translates from Simplified Chinese. The tool trusts your setting — just make sure that language actually has content in the file.

### 4. Drop in Your xcstrings File

Copy the `Localizable.xcstrings` from your Xcode project into this directory (or point to it in `config.yaml`).

### 5. Run It

```bash
uv run main.py
```

When it's done, you'll see a summary table showing how many strings were translated for each language. The results are already saved back into your `.xcstrings` file — just copy it back to your Xcode project.

## Project Structure

```
apple-i8n/
├── main.py                 # Entry point
├── config.yaml             # Your config (should NOT be committed to git)
├── config-example.yaml     # Example config template
├── Localizable.xcstrings   # Your localization file
├── pyproject.toml          # Project dependencies
└── apple_i8n/
    ├── config.py           # Config loading
    ├── xcstrings.py        # xcstrings file parsing and writing
    ├── translator.py       # LLM translation engine
    └── cli.py              # CLI interface, progress bar, logging
```
