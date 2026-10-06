# Argos Translate for calibre

![calibre 6.0+](https://img.shields.io/badge/calibre-6.0%2B-blue)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Translate EPUB and AZW3 books **offline** between 50 languages, inside calibre, with [Argos Translate](https://github.com/argosopentech/argos-translate).
Use it from calibre's interface or from the command line. It sets itself up the first time it runs.

## Features

- **Offline translation**: the text of your books never leaves your computer.
- **Two modes**: *Replace* produces a fully translated book; *Bilingual* places each paragraph's translation right after the original, which suits language learners.
- **The book stays intact**: books are edited in place with calibre's own book-editing engine, not converted. Structure, CSS, images, links and footnotes are preserved, and the table of contents and language metadata are updated.
- **No setup step**: uv, a Python environment, argostranslate and the language models are installed automatically the first time they are needed.
- **Any language pair Argos supports**, translated through English when no direct model exists.
- **Resumable**: translations are cached, so an interrupted job picks up where it stopped and repeated text is only translated once.
- **Batch processing**: folders, subfolders and file lists, with one translation worker for the whole batch; books already translated are skipped.
- **GUI and CLI share the same engine and cache.**
- **CPU or CUDA.**

## How it works

calibre ships its own Python, which can't load argostranslate's compiled libraries. The plugin therefore runs inside calibre, while the translation engine runs as a separate process in its own Python environment, connected through a pipe. Before each conversion, the plugin checks the Python environment, argostranslate and the language model for the requested pair, and installs only what is missing, fetching uv first if it needs it.

Once everything is in place, a run is a single quick check. Books that are fully cached skip these checks entirely and never touch the network.

## Requirements

- **calibre 6.0 or later** on Windows, macOS or Linux.
- **Internet access on first use**, to fetch uv (if it isn't already installed), Python 3.12, argostranslate and each language model once. After that, translation works offline.
- **Disk space**: the Python environment takes several hundred MB to a few GB depending on the platform, plus roughly 100 MB per language model.
- **uv is optional**: if `uv` is on your PATH it is used; otherwise the plugin downloads a private copy for x86_64 or ARM64 systems. On other architectures, install [uv](https://docs.astral.sh/uv/) yourself.

## Installation

Download `argos_translate.zip` from the [latest release](../../releases/latest).

> **Note:** GitHub's green *Code → Download ZIP* button does **not** produce an installable plugin. It wraps the files in an extra folder, and calibre expects `__init__.py` at the root of the zip. Use the release asset, or install from source as shown below.

### From calibre's interface

1. Open **Preferences → Plugins → Load plugin from file** and select `argos_translate.zip`.
2. Accept the security warning, then choose where to place the button (main toolbar and/or the book context menu).
3. Restart calibre.

You can also add or move the button later under **Preferences → Toolbars & menus**.

### From the command line

```sh
calibre-customize -a argos_translate.zip
```

Restart calibre if it is running. The command-line mode (below) works immediately.

### From source

```sh
git clone https://github.com/ROBERT-MCDOWELL/argostranslate-calibre-plugin.git
cd argostranslate-calibre-plugin
calibre-customize -b .
```

`calibre-customize -b` builds and installs the plugin straight from the folder. To build a zip yourself, zip the folder's **contents** so that `__init__.py` sits at the root of the archive.

## Where things are stored

| | GUI | Command line |
|---|---|---|
| Python environment | `python_env` inside the plugin's folder in calibre's cache (the settings page shows the exact path) | the active virtual environment if there is one, otherwise `./python_env` in the working directory |
| Language models | `models/argos-translate/` next to it | `./models/argos-translate/` |
| Translation cache and worker log | `argos_translate/` in calibre's cache folder | same as the GUI |

Inside `models/argos-translate/`:
- `downloads/` holds the model archives.
- `packages/` holds the unpacked models.
- `index.json` is the local copy of the Argos package index.

Deleting the environment or the models is safe: they are rebuilt on the next run.

## Using the GUI

1. Select one or more books that have an **EPUB** or **AZW3** format.
2. Click **Translate** on the toolbar, or use the button's arrow → *Translate selected books…*.
3. In the dialog, choose:
   - **From**: *Book language* reads it from each book's metadata; or pick a language explicitly.
   - **To**: pick a language, or type its code (e.g. `fr`).
   - **Mode**: *Replace* or *Bilingual*.
4. Click **OK**.

Each book runs as a background job, with progress in calibre's **Jobs** list. When a job finishes, the translation is added to your library as a new book, e.g. *Title [fr]*, or *Title [en+fr]* in bilingual mode, with its language set and the cover copied.

The very first job also builds the environment, so it takes a few minutes. *Refresh language list* in the dialog shows installed pairs and pairs available for download (marked `- download`).

### Settings

Open them via the button's arrow → *Settings…*, or **Preferences → Plugins → Argos Translate → Customize plugin**.

| Setting | Effect |
|---|---|
| Device | `cpu`, `cuda` or `auto` |
| Segments per batch | how many text segments are sent to the translation worker at once |
| Reuse previous translations | the translation cache that makes jobs resumable |
| Download missing language models automatically | turn off for strictly offline use |
| Test worker and list installed pairs | checks the environment and shows what is installed |
| Clear translation cache | needed after updating a language model, so old translations aren't reused |

## Using the command line

The plugin runs through calibre's `calibre-debug`. Everything after `--` is passed to the plugin:

```sh
calibre-debug -r "Argos Translate" -- [options] BOOKS...
```

`BOOKS` can be files, folders, or `@list.txt` (a text file with one path per line), in any mix. Run with `-h` to see every option.

### Examples

```sh
# Translate one book; the source language is read from the book
calibre-debug -r "Argos Translate" -- "My Book.epub" -t fr
# Set the source language explicitly, write to a chosen file
calibre-debug -r "Argos Translate" -- book.azw3 -f de -t en -o /tmp/book-en.azw3
# Bilingual edition: each paragraph followed by its translation
calibre-debug -r "Argos Translate" -- book.epub -t es -m bilingual
# Every EPUB/AZW3 in a folder; outputs go next to each book
calibre-debug -r "Argos Translate" -- ./library -t fr
# Include subfolders and write into a separate tree that mirrors the source
calibre-debug -r "Argos Translate" -- ./library -r -t fr --output-dir ./translated
# Paths from a file, one per line
calibre-debug -r "Argos Translate" -- @books.txt -t fr
# Show installed pairs and pairs available for download
calibre-debug -r "Argos Translate" -- --list
# Strictly offline: fail instead of downloading a missing model
calibre-debug -r "Argos Translate" -- book.epub -t fr --no-download
# Use the GPU
calibre-debug -r "Argos Translate" -- book.epub -t fr --device cuda
```

The examples work the same in Windows `cmd` and PowerShell; only path separators differ.

### Options

| Option | Description |
|---|---|
| `-t`, `--to CODE` | target language (required), e.g. `fr` |
| `-f`, `--from CODE` | source language; default: read from each book's metadata |
| `-m`, `--mode MODE` | `replace` (default) or `bilingual` |
| `-o`, `--output FILE` | output file; only with a single input book |
| `-r`, `--recursive` | also look for books in subfolders of the given folders |
| `--output-dir DIR` | write translations into this folder, mirroring subfolders with `-r` |
| `--overwrite` | translate again even if the output file already exists |
| `--list` | list installed and downloadable language pairs, then exit |
| `--no-download` | never download missing language models, fail instead |
| `--no-cache` | neither read nor write the translation cache |
| `--allow-changes` | allow installing argostranslate into an existing environment even if that changes packages already there  |
| `--device DEVICE` | `cpu`, `cuda` or `auto`; default: the GUI setting |
| `--batch-size N` | segments per worker request; default: the GUI setting |

### Output, logs and exit codes

- **Output file names**: translations are saved as `book.fr.epub`, or `book.fr.bilingual.epub` in bilingual mode, unless you set `-o` or `--output-dir`.
- **stdout** contains only the paths of the translated files, one per line, so it is easy to capture in scripts.
- **stderr** carries progress (`[3/40] title.epub:  45.0% …`), logs and errors.
- **Exit codes**: `0` means everything succeeded; `1` means at least one book failed; `2` means invalid options.

```sh
out=$(calibre-debug -r "Argos Translate" -- book.epub -t fr) && calibredb add "$out"
```

## Translation modes

**Replace** swaps the text for its translation:
- `lang`/`xml:lang` attributes, the package's `dc:language` and the table of contents are all updated.
- In the calibre GUI, the result is added as a new book, so the original is never modified.

**Bilingual** keeps the original text and inserts the translation after each paragraph or heading:
- Each translated block carries the class `argos-translation` and the target `lang` attribute.
- In list items and table cells, the translation goes *inside* the element, so lists and table layouts stay intact.
- Ids are removed from the copies so internal links still point at the originals.

```html
<p>It was a bright cold day in April.</p>
<p class="argos-translation" lang="fr">C'était une journée froide et lumineuse d'avril.</p>
```

To style the translations, for example in italics, add CSS such as `.argos-translation { font-style: italic; opacity: .8; }` with calibre's book editor or the *Extra CSS* option of a conversion.

## Batch processing

- **Folders**: a folder is searched for EPUB and AZW3 files (add `-r` for subfolders). Files already named for the current target, such as `*.fr.epub`, are ignored, so outputs aren't translated again.
- **Resumable**: books whose output already exists are skipped, so rerunning an interrupted batch continues where it stopped. Use `--overwrite` to regenerate.
- **One worker per batch**: the translation process starts once and each language model is loaded once, however many books are in the batch.
- **Failures don't stop the batch**: each failure is reported with its reason, and a summary closes the run (`Batch done: 12 translated, 3 skipped, 1 failed`).
- **Mixed languages**: each book's source language is detected separately, and any new pair is fetched the first time it's needed.

When a folder mixes outputs for several target languages, `--output-dir` keeps translations out of the source tree entirely.

In the GUI, selecting several books queues one job per book; the jobs run one after another.

## Languages

- Argos Translate currently covers **50 languages** with about 100 models. Nearly all of them translate to or from English, so any pair between those 50 languages works, through English where needed.
- Use Argos language codes, mostly two-letter ISO 639-1 codes such as `en`, `fr`, `de`, `es`, `zh`. `--list` or *Refresh language list* shows what is installed and what can be downloaded.
- When no direct model exists for a pair, the plugin translates through English (e.g. `de → en → fr`) and downloads only the missing step. These two-step translations are of somewhat lower quality.
- The source language comes from the book's metadata. Use `--from`, or pick it in the dialog, when a book's metadata is wrong or missing.

## Using an existing virtual environment

If a virtual environment is active when you run the command line (`VIRTUAL_ENV` is set), the plugin uses that environment instead of `./python_env`. Use this when another application on the same machine already has its own environment.

Installing argostranslate can change versions of packages that application depends on. For example, argostranslate 1.11.0 requires exactly `stanza==1.10.1`. So before installing into an environment it didn't create itself, the plugin runs a uv dry run. If any existing package would change, it stops and lists the changes:

```
installing argostranslate into /path/to/python_env would change packages it already uses:
  stanza 1.9.0 -> 1.10.1
Nothing was installed. Run again with --allow-changes if the application owning this environment works with those versions.
```

Check those versions against the other application before using `--allow-changes`.

## What gets translated

- **What is translated**: text is translated block by block (paragraphs, headings, list items, table cells, captions) so the engine sees whole sentences. The table of contents is translated in Replace mode.
- **What is left untouched**: `code`, `pre`, `kbd`, math, SVG, and `sup`/`sub` (footnote markers). Anything marked `translate="no"` or with the class `notranslate` is skipped too.
- **What is kept in place**: links, line breaks and images stay where they are. The text on either side of them is translated as separate pieces.

## Limitations

- **Formats**: EPUB and AZW3 only. Convert other formats first, e.g. with `ebook-convert book.mobi book.epub`.
- **Inline formatting**: italic or bold words *inside* a sentence lose that formatting in the translated text.
- **Quality**: machine translation quality depends on the Argos model for the pair, and pairs routed through English are weaker.
- **Model updates**: after updating a language model, clear the translation cache (or use `--no-cache` / `--overwrite`) so earlier translations aren't reused.

## Troubleshooting

- **Error messages** include the end of the translation worker's log. The full log is `worker.log` in the plugin's folder in calibre's cache.
- **Errors inside calibre itself**: start calibre with `calibre-debug -g` to see full tracebacks in the terminal.

| Message | Meaning |
|---|---|
| `would change packages it already uses` | see [Using an existing virtual environment](#using-an-existing-virtual-environment) |
| `python_env exists but is not a usable Python virtual environment` | a folder named `python_env` that isn't a venv is in the way; the plugin never overwrites it |
| `no prebuilt uv for …` | unusual CPU architecture; install uv yourself and put it on PATH |
| `book language unknown` | the book has no language metadata; set the source language explicitly |
| `no Argos model available for xx->yy` | Argos has no model for that pair, even through English |

## Privacy

Book text is translated locally and never sent anywhere. The only network access is downloading uv, Python, argostranslate and language models, each fetched once from their official sources (GitHub, PyPI and the Argos package index).

## Development

| File | Role |
|---|---|
| `__init__.py` | plugin declaration and command-line entry point |
| `ui.py`, `dialog.py`, `config.py` | toolbar action, translate dialog, settings page |
| `cli.py` | command-line interface and batch handling |
| `jobs.py` | translation job, shared by the GUI and the CLI |
| `translator.py` | HTML segmentation and rewriting (no calibre dependency) |
| `runtime.py` | automatic environment checks: uv, venv, argostranslate |
| `client.py`, `worker.py` | the pipe protocol; `worker.py` runs inside the Argos environment |
| `cache.py`, `prefs.py` | translation cache and settings |

To iterate on the code, run `calibre-customize -b . && calibre-debug -g`.

## License

Released under the MIT License, see [LICENSE](LICENSE).

Built on [calibre](https://calibre-ebook.com), [Argos Translate](https://github.com/argosopentech/argos-translate), [CTranslate2](https://github.com/OpenNMT/CTranslate2) and [uv](https://github.com/astral-sh/uv).
