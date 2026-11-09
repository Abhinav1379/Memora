"""Validate, extract, analyze, import and refresh local document snapshots."""
import hashlib
import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from memora.analysis import analyze_text
from memora.database import Repository, utc_now
from memora.errors import DuplicateDocument, InvalidDocument, MemoraError

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def validate_path(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> Path:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise InvalidDocument("Select a regular file, not a folder.")
        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InvalidDocument("Unsupported format. Import TXT, Markdown (.md), or PDF files.")
        if resolved.stat().st_size > max_bytes:
            raise InvalidDocument(f"This file exceeds the {max_bytes / (1024 * 1024):g} MB import limit.")
        return resolved
    except FileNotFoundError as exc:
        raise InvalidDocument("This file is missing. Select an existing file.") from exc
    except PermissionError as exc:
        raise InvalidDocument("Permission denied. Check that you can read this file.") from exc
    except (OSError, ValueError) as exc:
        raise InvalidDocument("The file path cannot be read.") from exc


def read_source(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[Path, bytes, os.stat_result]:
    resolved = validate_path(path, max_bytes)
    try:
        with resolved.open("rb") as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > max_bytes:
            raise InvalidDocument("The file is larger than the import limit.")
        if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
            raise InvalidDocument("The file changed during import. Wait for it to finish saving, then try again.")
        return resolved, raw, after
    except PermissionError as exc:
        raise InvalidDocument("Permission denied. Check that you can read this file.") from exc
    except OSError as exc:
        raise InvalidDocument("Cannot read this file. Check its location and permissions.") from exc


def extract_bytes(raw: bytes, file_type: str) -> str:
    if file_type not in {"txt", "md", "pdf"}:
        raise InvalidDocument("Unsupported document format.")
    if file_type == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise InvalidDocument("PDF support requires pypdf. Install requirements.txt and try again.") from exc
        try:
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise InvalidDocument("Encrypted PDFs are not supported. Import an unencrypted copy.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except InvalidDocument:
            raise
        except Exception as exc:
            logger.warning("PDF extraction failed (%s).", type(exc).__name__)
            raise InvalidDocument("PDF text extraction failed. The file may be damaged or unsupported.") from exc
    else:
        try:
            if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
                text = raw.decode("utf-32")
            elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = raw.decode("utf-16")
            else:
                text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise InvalidDocument("Unsupported text encoding. Save this file as UTF-8 and try again.") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if any(ord(char) < 32 and char not in "\n\t\f" for char in text):
        raise InvalidDocument("This file contains binary data or unsupported control characters.")
    if not text.strip():
        detail = " It may contain scanned images; OCR is not included." if file_type == "pdf" else ""
        raise InvalidDocument("No readable text was found in this document." + detail)
    return text


def extract_text(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    resolved, raw, _ = read_source(path, max_bytes)
    return extract_bytes(raw, resolved.suffix.lower()[1:])


@dataclass
class ImportResult:
    filename: str
    status: str
    message: str
    document_id: int | None = None


class DocumentImporter:
    def __init__(self, repository: Repository, max_bytes: int = DEFAULT_MAX_BYTES):
        self.repository = repository
        self.max_bytes = max_bytes

    def import_file(self, path: str | Path) -> int:
        resolved, raw, stat = read_source(path, self.max_bytes)
        fingerprint = hashlib.sha256(raw).hexdigest()
        filepath = os.path.normcase(str(resolved))
        if self.repository.find_duplicate(filepath, fingerprint):
            raise DuplicateDocument("This file or an exact copy is already in your library.")
        return self.repository.add_document(self._snapshot(resolved, raw, stat, fingerprint))

    def _snapshot(self, resolved, raw, stat, fingerprint) -> dict:
        file_type = resolved.suffix.lower()[1:]
        content = extract_bytes(raw, file_type)
        analysis = analyze_text(content)
        return {
            "filename": resolved.name, "filepath": os.path.normcase(str(resolved)), "file_type": file_type,
            "file_size": len(raw), "imported_at": utc_now(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "content": content, "content_hash": fingerprint,
            "word_count": analysis["word_count"], "character_count": analysis["character_count"],
        }

    def reimport_file(self, document_id: int) -> bool:
        document = self.repository.get_document(document_id)
        if document["is_note"]:
            raise MemoraError("Native notes have no original file to reimport. Use Edit note instead.")
        resolved, raw, stat = read_source(document["filepath"], self.max_bytes)
        fingerprint = hashlib.sha256(raw).hexdigest()
        if fingerprint == document["content_hash"]:
            return False
        if self.repository.find_duplicate(os.path.normcase(str(resolved)), fingerprint, exclude_id=document_id):
            raise DuplicateDocument("The updated file is an exact copy of another document in your library.")
        self.repository.replace_document_content(document_id, self._snapshot(resolved, raw, stat, fingerprint))
        return True

    def import_many(self, paths, progress=None) -> list[ImportResult]:
        results = []
        for index, path in enumerate(paths, 1):
            try:
                document_id = self.import_file(path)
                result = ImportResult(Path(path).name, "imported", "Added to your library.", document_id)
            except DuplicateDocument as exc:
                result = ImportResult(Path(path).name, "duplicate", str(exc))
            except MemoraError as exc:
                result = ImportResult(Path(path).name, "failed", str(exc))
            except Exception as exc:
                logger.error("Import failed (%s).", type(exc).__name__)
                result = ImportResult(Path(path).name, "failed", "Import failed. Check file permissions and available disk space.")
            results.append(result)
            if progress:
                progress(index, result)
        return results
