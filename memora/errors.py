"""Errors with safe, actionable messages for the desktop interface."""


class MemoraError(Exception):
    """An expected operation failure."""


class InvalidDocument(MemoraError):
    """A file cannot be imported."""


class DuplicateDocument(MemoraError):
    """A file or its exact contents are already in the library."""
