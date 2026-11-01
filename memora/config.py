"""Platform defaults and a small, persistent preferences file."""
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from memora.errors import MemoraError


def default_data_dir() -> Path:
    override = os.environ.get("MEMORA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Memora"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Memora"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "memora"


@dataclass
class Settings:
    data_dir: Path
    database_path: Path | None = None
    max_search_results: int = 1000
    theme: str = "light"
    export_format: str = "json"
    max_file_bytes: int = 50 * 1024 * 1024

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        database_path = Path(self.database_path or "library.sqlite3").expanduser()
        self.database_path = (database_path if database_path.is_absolute() else self.data_dir / database_path).resolve()
        if type(self.max_search_results) is not int or not 1 <= self.max_search_results <= 10000:
            raise MemoraError("Maximum search results must be between 1 and 10,000.")
        if self.theme not in {"light", "dark"} or self.export_format not in {"txt", "csv", "json"}:
            raise MemoraError("Preferences contain an unsupported theme or export format.")
        if type(self.max_file_bytes) is not int or self.max_file_bytes < 1:
            raise MemoraError("The import file size limit must be positive.")

    def save(self):
        self.__post_init__()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            database_location = str(self.database_path.relative_to(self.data_dir))
        except ValueError:
            database_location = str(self.database_path)
        values = {
            "database_path": database_location,
            "max_search_results": self.max_search_results,
            "theme": self.theme,
            "export_format": self.export_format,
            "max_file_bytes": self.max_file_bytes,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.data_dir,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(values, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, self.data_dir / "settings.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def load_settings(data_dir: Path | None = None) -> Settings:
    folder = Path(data_dir or default_data_dir()).expanduser().resolve()
    path = folder / "settings.json"
    try:
        values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        allowed = {"database_path", "max_search_results", "theme", "export_format", "max_file_bytes"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("unknown preferences")
        return Settings(data_dir=folder, **values)
    except (ValueError, TypeError, OSError) as exc:
        raise MemoraError("Cannot read preferences. Check settings.json in your Memora data folder.") from exc
