"""Safe prefix word search and SQL filters over the local full-text index."""
import re
import unicodedata

from memora.database import Repository, decode_search_row
from memora.errors import MemoraError

SORTS = {
    "relevance": "rank, d.filename COLLATE NOCASE, d.id",
    "filename": "d.filename COLLATE NOCASE, d.id",
    "newest": "d.imported_at DESC, d.id DESC",
    "oldest": "d.imported_at, d.id",
    "word count": "d.word_count DESC, d.filename COLLATE NOCASE, d.id",
}


def search_documents(repository: Repository, query: str = "", *, category_id: int | None = None,
                     tag_id: int | None = None, bookmarked: bool | None = None,
                     file_type: str | None = None, sort: str = "relevance", limit: int = 1000) -> list[dict]:
    if sort not in SORTS or type(limit) is not int or not 1 <= limit <= 10000:
        raise MemoraError("Choose a supported sort order and result limit between 1 and 10,000.")
    if len(query) > 500:
        raise MemoraError("Please shorten your search to 500 characters or fewer.")
    tokens = re.findall(r"[^\W_]+", unicodedata.normalize('NFC', query), re.UNICODE)
    if query.strip() and not tokens:
        return []
    parameters = []
    conditions = []
    join = ""
    rank = "0.0"
    if tokens:
        join = "JOIN document_fts ON document_fts.rowid = d.id"
        conditions.append("document_fts MATCH ?")
        parameters.append(" AND ".join('"' + token + '"*' for token in tokens))
        rank = "bm25(document_fts, 6.0, 1.0, 3.0, 3.0)"
    if category_id is not None:
        conditions.append("d.category_id = ?")
        parameters.append(category_id)
    if tag_id is not None:
        conditions.append("EXISTS (SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id AND dt.tag_id = ?)")
        parameters.append(tag_id)
    if bookmarked is not None:
        conditions.append("d.bookmarked = ?")
        parameters.append(int(bookmarked))
    if file_type:
        if file_type == "note":
            conditions.append("d.is_note = 1")
        elif file_type in {"txt", "md", "pdf"}:
            conditions.append("d.file_type = ? AND d.is_note = 0")
            parameters.append(file_type)
        else:
            raise MemoraError("Choose TXT, Markdown, PDF or Note as the type filter.")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    parameters.append(limit)
    rows = repository.connection.execute(f"""
        SELECT d.id, d.filename, d.file_type, d.filepath, d.file_size, d.imported_at, d.modified_at,
            d.word_count, d.character_count, d.category_id, c.name AS category, d.bookmarked, d.is_note,
            b.note AS bookmark_note, b.created_at AS bookmarked_at,
            COALESCE((SELECT json_group_array(t.name) FROM tags t JOIN document_tags dt ON dt.tag_id = t.id
                WHERE dt.document_id = d.id), '[]') AS tags, {rank} AS rank
        FROM documents d LEFT JOIN categories c ON c.id = d.category_id
        LEFT JOIN bookmarks b ON b.document_id = d.id {join}
        {where} ORDER BY {SORTS[sort]} LIMIT ?
    """, parameters)
    return [decode_search_row(row) for row in rows]
