"""Keep the full-text index in the same transaction as library changes."""
import sqlite3


def index_document(connection: sqlite3.Connection, document_id: int):
    connection.execute("DELETE FROM document_fts WHERE rowid = ?", (document_id,))
    connection.execute("""
        INSERT INTO document_fts(rowid, filename, content, category, tags)
        SELECT d.id, d.filename, d.content, COALESCE(c.name, ''),
            COALESCE((SELECT group_concat(t.name, ' ') FROM tags t
                JOIN document_tags dt ON dt.tag_id = t.id WHERE dt.document_id = d.id), '')
        FROM documents d LEFT JOIN categories c ON c.id = d.category_id WHERE d.id = ?
    """, (document_id,))
