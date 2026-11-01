# Memora

**A private home for your documents.** Import, organize, search and read a personal library, write notes, and export what you need. Memora runs locally without an account.

![Memora library with example documents and filters](docs/images/library.png)

*Existing captures of the running application with generic example documents. Your new library starts empty.*

## Install and open

You need **Python 3.10+ with Tkinter/Tk 8.6** and SQLite with FTS5/JSON support. Standard Windows Python installations normally include these; PDF reading uses the dependency in `requirements.txt`.

Open PowerShell in this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

No environment activation or PowerShell policy change is needed. Installation may need internet access; normal use is offline. To open Memora again, run only the last command.

<details>
<summary>Linux / macOS setup</summary>

Use a Python installation with Tkinter available. Some Linux distributions provide it separately, for example as `python3-tk`.

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python main.py
```

The documented runtime is cross-platform; the recorded desktop checks were performed on Windows.

</details>

## Your first five minutes

1. Choose **Import documents** and select a TXT, Markdown or text-based PDF. Review any duplicate skips or import errors. Original files stay untouched.
2. Double-click a library row to open it. **Read** shows extracted text; **Copy text** copies a selection or the whole document.
3. Visit **Organize** to create a category and tags. Open a document's **Details**, assign those labels and choose **Save changes**. Categories are yours to create; none are preinstalled.
4. Bookmark an item in **Details**, optionally add a bookmark note, and save. Use **Bookmarks** in the sidebar to find it again.
5. Search for words, use **Filters** and choose a sort order. Open **Analysis** for statistics, or **Export** for TXT, CSV or JSON.

<details>
<summary>See the reader and analysis views</summary>

![Memora document reader](docs/images/reader.png)

![Local document statistics and word frequencies](docs/images/analysis.png)

</details>

## What you can do

| Task | Where to go |
| --- | --- |
| Write a note | **New note** → enter a title/body → **Save note** |
| Edit a saved note | Open it from **Notes** → **Edit note** |
| Link related items | Reader → **Related** → **Link document** |
| Refresh a changed original | Reader → **Reimport**; review the replacement confirmation |
| Export a document | Reader → **Export** → choose content and format |
| Export visible search results | Library → **Export results** |
| Change appearance or result limit | **Preferences** |

Search matches literal word prefixes across the indexed filename, text, category and tags. Every search word must match: `travel water` searches for both. It is not semantic search or a Boolean query language. Result exports include the displayed rows, up to the selected result limit.

Reimport requires the original file at its recorded path. It retains labels, bookmarks and related links; a failed reimport leaves the saved snapshot intact. Imported originals are not edited. Native notes are stored inside the library database.

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Import documents |
| `Ctrl+N` | New note |
| `Ctrl+F` | Return to search |
| `Ctrl+E` | Export |
| `Enter` on a library row | Open the selected item |

## Supported files and common fixes

| Situation | What to check |
| --- | --- |
| TXT / Markdown import | Use UTF-8, or UTF-16/UTF-32 with a byte-order mark. Markdown is displayed as source text. |
| PDF has no readable text | Image-only/scanned PDFs need OCR elsewhere first. Encrypted or damaged PDFs are rejected. |
| A file is skipped as a duplicate | Exact byte copies and repeated source paths are detected. Use **Reimport** to refresh the same source. |
| Missing package | Run the `pip install -r requirements.txt` command using this project's `.venv` interpreter. |
| Tkinter or SQLite FTS5 is unavailable | Use a Python build providing those components. |
| Import is slow | Try smaller documents. The default file limit is 50 MB; compressed PDFs can still require substantial memory. |

The minimum window size is 1024 × 720. Unsaved edits prompt you to save, discard or cancel when navigating or exiting. PDF layout, OCR, automatic file watching, version history and cloud sync are not included.

## Your data and privacy

| System | Default data folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Memora` |
| macOS | `~/Library/Application Support/Memora` |
| Linux | `$XDG_DATA_HOME/memora`, or `~/.local/share/memora` |

The folder contains `library.sqlite3`, settings and technical logs. Close Memora before backing up the whole data folder. Moving the source-code folder does not move your library. `MEMORA_DATA_DIR` can select a different data location before launch.

Documents and notes are stored in plain text, without application-level encryption. There are no accounts, telemetry or application network calls. Exports are files you choose to create; replacing an existing export requires confirmation. Protect your account and backups accordingly.

## Inside the code

[documents.py](memora/documents.py) validates and extracts imports. [database.py](memora/database.py) stores the SQLite library and relationships. [search.py](memora/search.py) queries the FTS index; [analysis.py](memora/analysis.py) computes local statistics. The [GUI](memora/gui/main_window.py) brings those services into the library and reader.

## License

PolyForm Noncommercial 1.0.0. See [LICENSE](LICENSE).

Copyright Abhinav007 (Dlyzly-ops007) (2026)
