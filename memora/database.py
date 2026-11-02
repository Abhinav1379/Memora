"""SQLite schema and transactional document, category, tag and bookmark storage."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memora.analysis import analyze_text
from memora.errors import DuplicateDocument, MemoraError
from memora.indexer import index_document

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 80),
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 80)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL CHECK(file_type IN ('txt', 'md', 'pdf')),
    file_size INTEGER NOT NULL CHECK(file_size >= 0),
    imported_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    word_count INTEGER NOT NULL CHECK(word_count >= 0),
    character_count INTEGER NOT NULL CHECK(character_count >= 0),
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    bookmarked INTEGER NOT NULL DEFAULT 0 CHECK(bookmarked IN (0, 1))
);
CREATE TABLE IF NOT EXISTS document_links (
    first_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    second_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (first_id, second_id),
    CHECK (first_id < second_id)
);
CREATE INDEX IF NOT EXISTS idx_document_links_second ON document_links(second_id);
CREATE TABLE IF NOT EXISTS document_tags (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category_id);
CREATE INDEX IF NOT EXISTS idx_documents_imported ON documents(imported_at);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_documents_bookmarked ON documents(bookmarked);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag_id);
CREATE TRIGGER IF NOT EXISTS bookmark_added AFTER INSERT ON bookmarks BEGIN
    UPDATE documents SET bookmarked = 1 WHERE id = NEW.document_id;
END;
CREATE TRIGGER IF NOT EXISTS bookmark_removed AFTER DELETE ON bookmarks BEGIN
    UPDATE documents SET bookmarked = 0 WHERE id = OLD.document_id;
END;
CREATE TRIGGER IF NOT EXISTS document_removed AFTER DELETE ON documents BEGIN
    DELETE FROM document_fts WHERE rowid = OLD.id;
END;
CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
    filename, content, category, tags, tokenize = 'unicode61 remove_diacritics 2'
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def validate_name(name: str) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 80 or any(ord(char) < 32 for char in name):
        raise MemoraError("Names must contain 1–80 characters without line breaks or control characters.")
    return name


class Repository:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=10)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise MemoraError("This library was created by a newer version of Memora.")
            with self.connection:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
                columns = {row[1] for row in self.connection.execute("PRAGMA table_info(documents)")}
                if "is_note" not in columns:
                    self.connection.execute("ALTER TABLE documents ADD COLUMN is_note INTEGER NOT NULL DEFAULT 0 CHECK(is_note IN (0, 1))")
                self.connection.execute("PRAGMA user_version = 2")
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def count_documents(self) -> int:
        return self.connection.execute("SELECT count(*) FROM documents").fetchone()[0]

    def delete_document(self, document_id: int):
        """Remove a library item and its relationships; never touch source files."""
        with self.connection:
            cursor = self.connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            if not cursor.rowcount:
                raise MemoraError("The selected document no longer exists.")

    def find_duplicate(self, filepath: str, content_hash: str, exclude_id: int | None = None):
        return self.connection.execute(
            "SELECT id FROM documents WHERE (filepath = ? OR content_hash = ?) AND (? IS NULL OR id != ?)",
            (filepath, content_hash, exclude_id, exclude_id)
        ).fetchone()

    def add_document(self, document: dict) -> int:
        columns = ("filename", "filepath", "file_type", "file_size", "imported_at", "modified_at",
                   "content", "content_hash", "word_count", "character_count", "is_note")
        try:
            with self.connection:
                cursor = self.connection.execute(
                    f"INSERT INTO documents ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                    tuple(document.get(column, 0) if column == "is_note" else document[column] for column in columns),
                )
                index_document(self.connection, cursor.lastrowid)
                return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if self.find_duplicate(document["filepath"], document["content_hash"]):
                raise DuplicateDocument("This file or an exact copy is already in your library.") from exc
            raise

    def replace_document_content(self, document_id: int, document: dict):
        """Replace a snapshot atomically, preserving its ID and user organization."""
        self.get_document(document_id)
        columns = ("filename", "filepath", "file_type", "file_size", "modified_at", "content",
                   "content_hash", "word_count", "character_count")
        try:
            with self.connection:
                self.connection.execute(
                    f"UPDATE documents SET {', '.join(column + ' = ?' for column in columns)} WHERE id = ?",
                    tuple(document[column] for column in columns) + (document_id,),
                )
                index_document(self.connection, document_id)
        except sqlite3.IntegrityError as exc:
            if self.find_duplicate(document["filepath"], document["content_hash"], exclude_id=document_id):
                raise DuplicateDocument("The updated file is an exact copy of another document in your library.") from exc
            raise

    @staticmethod
    def _note_fields(title: str, content: str) -> dict:
        title = validate_name(title)
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        size = len(content.encode("utf-8"))
        if size > 50 * 1024 * 1024:
            raise MemoraError("Notes must be no larger than 50 MB.")
        if any(ord(char) < 32 and char not in "\n\t\f" for char in content):
            raise MemoraError("The note contains unsupported control characters.")
        analysis = analyze_text(content)
        return {"filename": title, "content": content, "file_size": size, "modified_at": utc_now(),
                "word_count": analysis["word_count"], "character_count": analysis["character_count"]}

    def create_note(self, title: str, content: str = "") -> int:
        fields = self._note_fields(title, content)
        identity = str(uuid4())
        return self.add_document({**fields, "filepath": "memora:note:" + identity,
                                  "content_hash": "note:" + identity, "file_type": "txt", "is_note": 1,
                                  "imported_at": fields["modified_at"]})

    def update_note(self, document_id: int, title: str, content: str):
        document = self.get_document(document_id)
        if not document["is_note"]:
            raise MemoraError("Only notes created in Memora can be edited here.")
        fields = self._note_fields(title, content)
        self.replace_document_content(document_id, {**document, **fields})

    def link_documents(self, document_id: int, related_id: int):
        if document_id == related_id:
            raise MemoraError("Choose a different document to link.")
        first, second = sorted((document_id, related_id))
        try:
            with self.connection:
                self.connection.execute("""INSERT INTO document_links(first_id, second_id, created_at)
                    VALUES (?, ?, ?) ON CONFLICT(first_id, second_id) DO NOTHING""", (first, second, utc_now()))
        except sqlite3.IntegrityError as exc:
            raise MemoraError("A selected document no longer exists.") from exc

    def unlink_documents(self, document_id: int, related_id: int):
        first, second = sorted((document_id, related_id))
        with self.connection:
            self.connection.execute("DELETE FROM document_links WHERE first_id = ? AND second_id = ?", (first, second))

    def list_related_documents(self, document_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""
            SELECT d.id, d.filename, d.file_type, d.is_note FROM documents d JOIN document_links l
            ON (l.first_id = ? AND l.second_id = d.id) OR (l.second_id = ? AND l.first_id = d.id)
            ORDER BY d.filename COLLATE NOCASE, d.id
        """, (document_id, document_id))]

    def get_document(self, document_id: int) -> dict:
        row = self.connection.execute("""
            SELECT d.*, c.name AS category, b.note AS bookmark_note, b.created_at AS bookmarked_at
            FROM documents d LEFT JOIN categories c ON c.id = d.category_id
            LEFT JOIN bookmarks b ON b.document_id = d.id WHERE d.id = ?
        """, (document_id,)).fetchone()
        if row is None:
            raise MemoraError("The selected document no longer exists.")
        result = dict(row)
        result["tags"] = [dict(tag) for tag in self.connection.execute("""
            SELECT t.id, t.name FROM tags t JOIN document_tags dt ON dt.tag_id = t.id
            WHERE dt.document_id = ? ORDER BY t.name COLLATE NOCASE
        """, (document_id,))]
        result["bookmarked"] = bool(result["bookmarked"])
        result["is_note"] = bool(result["is_note"])
        return result

    def list_categories(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""
            SELECT c.*, (SELECT count(*) FROM documents d WHERE d.category_id = c.id) AS document_count
            FROM categories c ORDER BY c.name COLLATE NOCASE
        """)]

    def list_tags(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""
            SELECT t.*, (SELECT count(*) FROM document_tags dt WHERE dt.tag_id = t.id) AS document_count
            FROM tags t ORDER BY t.name COLLATE NOCASE
        """)]

    def create_category(self, name: str, description: str = "") -> int:
        if len(description) > 2000:
            raise MemoraError("Category descriptions must be at most 2,000 characters.")
        return self._create_label("categories", name, description)

    def create_tag(self, name: str) -> int:
        return self._create_label("tags", name)

    def _create_label(self, table: str, name: str, description: str = "") -> int:
        name = validate_name(name)
        try:
            with self.connection:
                if table == "categories":
                    cursor = self.connection.execute("INSERT INTO categories(name, description) VALUES (?, ?)",
                                                     (name, description.strip()))
                else:
                    cursor = self.connection.execute("INSERT INTO tags(name) VALUES (?)", (name,))
                return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise MemoraError("That name is already in use. Choose a different name.") from exc

    def rename_category(self, category_id: int, name: str):
        self._rename_label("categories", category_id, name)

    def rename_tag(self, tag_id: int, name: str):
        self._rename_label("tags", tag_id, name)

    def _affected_documents(self, table: str, label_id: int) -> list[int]:
        if table == "categories":
            query = "SELECT id FROM documents WHERE category_id = ?"
        else:
            query = "SELECT document_id FROM document_tags WHERE tag_id = ?"
        return [row[0] for row in self.connection.execute(query, (label_id,))]

    def _rename_label(self, table: str, label_id: int, name: str):
        name = validate_name(name)
        try:
            with self.connection:
                cursor = self.connection.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (name, label_id))
                if cursor.rowcount == 0:
                    raise MemoraError("This item no longer exists.")
                for document_id in self._affected_documents(table, label_id):
                    index_document(self.connection, document_id)
        except sqlite3.IntegrityError as exc:
            raise MemoraError("That name is already in use. Choose a different name.") from exc

    def delete_category(self, category_id: int):
        self._delete_label("categories", category_id)

    def delete_tag(self, tag_id: int):
        self._delete_label("tags", tag_id)

    def _delete_label(self, table: str, label_id: int):
        with self.connection:
            affected = self._affected_documents(table, label_id)
            self.connection.execute(f"DELETE FROM {table} WHERE id = ?", (label_id,))
            for document_id in affected:
                index_document(self.connection, document_id)

    def update_metadata(self, document_id: int, category_id: int | None, tag_ids: list[int], *,
                        bookmarked: bool | None = None, note: str = ""):
        self.get_document(document_id)
        if len(note) > 10000:
            raise MemoraError("Bookmark notes must be at most 10,000 characters.")
        try:
            with self.connection:
                self.connection.execute("UPDATE documents SET category_id = ? WHERE id = ?", (category_id, document_id))
                self.connection.execute("DELETE FROM document_tags WHERE document_id = ?", (document_id,))
                self.connection.executemany("INSERT INTO document_tags(document_id, tag_id) VALUES (?, ?)",
                                            [(document_id, tag_id) for tag_id in set(tag_ids)])
                if bookmarked is not None:
                    self._write_bookmark(document_id, bookmarked, note)
                index_document(self.connection, document_id)
        except sqlite3.IntegrityError as exc:
            raise MemoraError("A selected category or tag no longer exists. Refresh and try again.") from exc

    def set_bookmark(self, document_id: int, bookmarked: bool, note: str = ""):
        if len(note) > 10000:
            raise MemoraError("Bookmark notes must be at most 10,000 characters.")
        self.get_document(document_id)
        with self.connection:
            self._write_bookmark(document_id, bookmarked, note)

    def _write_bookmark(self, document_id: int, bookmarked: bool, note: str):
        if bookmarked:
            self.connection.execute("""
                INSERT INTO bookmarks(document_id, note, created_at) VALUES (?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET note = excluded.note
            """, (document_id, note, utc_now()))
        else:
            self.connection.execute("DELETE FROM bookmarks WHERE document_id = ?", (document_id,))

    def rebuild_index(self):
        with self.connection:
            self.connection.execute("DELETE FROM document_fts")
            for row in self.connection.execute("SELECT id FROM documents").fetchall():
                index_document(self.connection, row[0])


def decode_search_row(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["tags"] = json.loads(result["tags"])
    result["bookmarked"] = bool(result["bookmarked"])
    result["is_note"] = bool(result["is_note"])
    return result
