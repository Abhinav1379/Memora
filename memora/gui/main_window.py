"""Desktop pages, navigation and operation dialogs."""
import logging
import queue
import sqlite3
import threading
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from memora import __version__
from memora.config import Settings
from memora.database import Repository
from memora.documents import DocumentImporter
from memora.errors import MemoraError
from memora.exporting import export_data
from memora.gui.pages import NoteEditorPage, OrganizationPage, PreferencesPage, page_header
from memora.gui.panels import AnalysisPanel, DocumentPanel, DocumentViewer, MetadataPanel, RelatedPanel, SearchPanel
from memora.gui.widgets import apply_theme, modal, scrollable_text, set_text
from memora.search import search_documents

logger = logging.getLogger(__name__)


class MainWindow(ttk.Frame):
    def __init__(self, root: tk.Tk, repository: Repository, settings: Settings):
        super().__init__(root)
        self.root, self.repository, self.settings = root, repository, settings
        self.selected_document = None
        self.results = []
        self.categories, self.tags = [], []
        self.current_view = "all"
        self.page = "library"
        self.editor_return = "library"
        self.importing = False
        self.reimport_document_id = None
        self.events = queue.Queue()
        self.poll_id = None
        self.refreshing = False
        root.title("Memora — Your local document library")
        root.geometry("1360x860")
        root.minsize(1024, 720)
        self.colors = apply_theme(root, settings.theme)
        self.app_icon = tk.PhotoImage(width=32, height=32)
        self.app_icon.put("#142E30", to=(0, 0, 32, 32))
        self.app_icon.put("#DCEED9", to=(4, 4, 28, 28))
        for y, row in enumerate(("1000001", "1100011", "1010101", "1001001", "1000001", "1000001", "1000001")):
            for x, pixel in enumerate(row):
                if pixel == "1":
                    self.app_icon.put("#204539", to=(9 + x * 2, 9 + y * 2, 11 + x * 2, 11 + y * 2))
        root.iconphoto(True, self.app_icon)
        root.report_callback_exception = self.callback_error
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.pack(fill="both", expand=True)
        self.build_menu()
        self.build_sidebar()
        workspace = ttk.Frame(self)
        workspace.pack(side="left", fill="both", expand=True)
        footer = ttk.Frame(workspace, padding=(28, 12, 28, 16))
        footer.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Ready · Your library stays on this computer")
        self.count = tk.StringVar(value="0 documents")
        ttk.Label(footer, textvariable=self.count, style="Muted.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(footer, length=110, mode="determinate")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=620).pack(side="left", fill="x", expand=True)
        host = ttk.Frame(workspace, padding=(28, 26, 28, 8))
        host.pack(fill="both", expand=True)
        self.pages = {name: ttk.Frame(host) for name in ("library", "reader")}
        self.build_library_page(self.pages["library"])
        self.build_reader_page(self.pages["reader"])
        self.editor = NoteEditorPage(host, self.save_note, self.cancel_editor)
        self.organization = OrganizationPage(host, repository, self.labels_changed, self.callback_error, self.filter_label)
        self.preferences_page = PreferencesPage(host, self.save_preferences, self.back_to_library)
        self.pages.update(editor=self.editor, organize=self.organization, preferences=self.preferences_page)
        root.bind("<Control-o>", lambda event: self.import_files())
        root.bind("<Control-f>", self.focus_search)
        root.bind("<Control-e>", lambda event: self.export_dialog())
        root.bind("<Control-n>", lambda event: self.note_editor())
        self.refresh_labels()
        self.refresh_library()
        self.show_page("library", guard=False)
        self.recolor(root, self.colors)

    def build_sidebar(self):
        sidebar = ttk.Frame(self, width=224, padding=(14, 26, 14, 18), style="Sidebar.TFrame")
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", pady=(0, 14))
        ttk.Label(brand, text="M", style="BrandMark.TLabel").pack(side="left", padx=(2, 10))
        ttk.Label(brand, text="Memora", style="Brand.TLabel").pack(side="left")
        ttk.Label(sidebar, text="A home for your documents", style="Sidebar.TLabel", font=("Segoe UI", 9)).pack(anchor="w", padx=4)
        ttk.Label(sidebar, text="YOUR LIBRARY", style="Sidebar.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(40, 10))
        self.nav_buttons = {}
        for title, key in (("Library", "all"), ("Notes", "notes"), ("Bookmarks", "bookmarks"), ("Recent", "recent")):
            button = ttk.Button(sidebar, text=title, style="Nav.TButton", command=lambda view=key: self.navigate(view))
            button.pack(fill="x", pady=3)
            self.nav_buttons[key] = button
        ttk.Label(sidebar, text="MAKE IT YOURS", style="Sidebar.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(30, 10))
        for title, key, command in (("Organize", "organize", self.manage_labels), ("Preferences", "preferences", self.preferences)):
            button = ttk.Button(sidebar, text=title, style="Nav.TButton", command=command)
            button.pack(fill="x", pady=3)
            self.nav_buttons[key] = button
        ttk.Label(sidebar, text=f"Memora {__version__}", style="Sidebar.TLabel", font=("Segoe UI", 9)).pack(side="bottom", anchor="w", padx=12)
        ttk.Label(sidebar, text="●  Local & private", style="Sidebar.TLabel").pack(side="bottom", anchor="w", padx=12, pady=(0, 8))

    def build_library_page(self, parent):
        self.library_heading = tk.StringVar(value="Your library")
        actions = page_header(parent, self.library_heading, "Keep what matters. Find it when you need it.")
        self.import_button = ttk.Button(actions, text="+ Import documents", style="Accent.TButton", command=self.import_files)
        self.import_button.pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="+ New note", command=self.note_editor).pack(side="right")
        self.search = SearchPanel(parent, self.refresh_library)
        self.search.pack(fill="x", pady=(0, 22))
        self.library = DocumentPanel(parent, self.select_document, self.open_selected, lambda: self.export_dialog(results_only=True), self.delete_selected)
        self.library.pack(fill="both", expand=True)

    def build_reader_page(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 18))
        self.back_button = ttk.Button(top, text="← Back to library", command=self.back_to_library)
        self.back_button.pack(side="left")
        ttk.Button(top, text="Export…", command=self.export_dialog).pack(side="right")
        self.reader_delete_button = ttk.Button(top, text="Delete", width=7, command=self.delete_selected, state="disabled")
        self.reader_delete_button.pack(side="right", padx=(8, 0))
        self.bookmark_button = ttk.Button(top, text="Bookmark", command=self.toggle_bookmark)
        self.bookmark_button.pack(side="right", padx=8)
        self.document_title = tk.StringVar(value="Your document")
        self.document_subtitle = tk.StringVar(value="Select a document to get started")
        title_label = ttk.Label(parent, textvariable=self.document_title, style="Title.TLabel", wraplength=1000)
        title_label.pack(anchor="w")
        parent.bind("<Configure>", lambda event: title_label.configure(wraplength=max(300, event.width - 12)))
        ttk.Label(parent, textvariable=self.document_subtitle, style="Muted.TLabel").pack(anchor="w", pady=(8, 22))
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        self.viewer = DocumentViewer(self.notebook, self.copy_text, self.document_action)
        self.metadata = MetadataPanel(self.notebook, self.save_metadata, self.manage_labels)
        self.analysis = AnalysisPanel(self.notebook)
        self.related = RelatedPanel(self.notebook, self.link_dialog, self.open_related, self.unlink_related)
        for panel, name in ((self.viewer, "Read"), (self.metadata, "Details"), (self.analysis, "Analysis"), (self.related, "Related")):
            self.notebook.add(panel, text=name)

    def show_page(self, page, *, guard=True):
        if guard and page != self.page and not self.confirm_unsaved():
            return False
        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[page].pack(fill="both", expand=True)
        self.page = page
        active = self.current_view if page in {"library", "reader"} else "notes" if page == "editor" else page
        for key, button in self.nav_buttons.items():
            button.configure(style="NavSelected.TButton" if key == active else "Nav.TButton")
        return True

    def back_to_library(self):
        if self.show_page("library"):
            self.refresh_library()

    def focus_search(self, event=None):
        if self.show_page("library"):
            self.search.entry.focus_set()
            self.search.entry.selection_range(0, "end")
        return "break"

    def confirm_unsaved(self) -> bool:
        if self.page == "editor" and self.editor.dirty():
            answer = messagebox.askyesnocancel("Unsaved note", "Save your note before continuing?", parent=self.root)
            if answer is None or (answer and not self.save_note(open_after=False)):
                return False
            if not answer:
                self.editor.show(self.editor.document)
        if self.page == "preferences" and self.preferences_page.dirty():
            answer = messagebox.askyesnocancel("Unsaved preferences", "Save your preferences before continuing?", parent=self.root)
            if answer is None or (answer and not self.save_preferences()):
                return False
            if not answer:
                self.preferences_page.show(self.settings)
        if self.metadata.dirty():
            answer = messagebox.askyesnocancel("Unsaved details", "Save your document details before continuing?", parent=self.root)
            if answer is None:
                return False
            if answer:
                return self.save_metadata()
            self.metadata.show(self.selected_document)
        return True

    def navigate(self, view):
        if not self.confirm_unsaved():
            return
        if view != self.current_view:
            self.current_view = view
            self.search.reset()
        self.show_page("library", guard=False)
        self.refresh_library()

    def filter_label(self, kind, label_id):
        self.navigate("all")
        if self.page != "library":
            return
        combo = self.search.category_box if kind == "categories" else self.search.tag_box
        SearchPanel.select_id(combo, getattr(self, kind), label_id)
        if not self.search.filters_visible:
            self.search.toggle_filters()
        self.refresh_library()

    def labels_changed(self):
        self.refresh_labels()
        self.refresh_library()
        self.status.set("Organization updated · Your documents are kept")

    def refresh_labels(self):
        self.refreshing = True
        try:
            self.categories, self.tags = self.repository.list_categories(), self.repository.list_tags()
            self.search.refresh_labels(self.categories, self.tags)
            if self.selected_document:
                self.selected_document = self.repository.get_document(self.selected_document["id"])
            self.metadata.document = self.selected_document
            self.metadata.refresh_labels(self.categories, self.tags)
            self.organization.reload(self.categories, self.tags)
            if self.selected_document:
                self.show_document(self.selected_document)
        finally:
            self.refreshing = False

    def refresh_library(self):
        filters = self.search.filters()
        self.search.bookmark_box.configure(state="disabled" if self.current_view == "bookmarks" else "readonly")
        self.search.sort_box.configure(state="disabled" if self.current_view == "recent" else "readonly")
        self.search.type_box.configure(state="disabled" if self.current_view == "notes" else "readonly")
        if self.current_view == "bookmarks":
            self.search.bookmark.set("Bookmarked")
            filters["bookmarked"] = True
        if self.current_view == "recent":
            self.search.sort.set("Newest")
            filters["sort"] = "newest"
        if self.current_view == "notes":
            self.search.file_type.set("Note")
            filters["file_type"] = "note"
        self.search.update_filter_summary()
        self.results = search_documents(self.repository, self.search.query.get(), limit=self.settings.max_search_results, **filters)
        total = self.repository.count_documents()
        selected_id = self.selected_document["id"] if self.selected_document else None
        if not total:
            empty = "No documents in your library yet.\nImport a file or create a note to get started."
        elif self.current_view == "bookmarks" and not self.search.query.get().strip() and not any(filters.get(key) for key in ("category_id", "tag_id", "file_type")):
            empty = "No bookmarks yet.\nBookmark a document to keep it close at hand."
        elif self.current_view == "notes" and not self.search.query.get().strip() and not any(filters.get(key) for key in ("category_id", "tag_id", "bookmarked")):
            empty = "No notes yet.\nChoose New note to start writing."
        else:
            empty = "No documents match your search.\nTry another word or reset the filters."
        titles = {"all": "Your library", "recent": "Recently added", "bookmarks": "Your bookmarks", "notes": "Your notes"}
        self.library_heading.set(titles[self.current_view])
        self.library.title.set("ALL DOCUMENTS" if self.current_view == "all" else self.current_view.upper())
        self.back_button.configure(text="← Back to " + {"all": "library", "notes": "notes", "bookmarks": "bookmarks", "recent": "recent"}[self.current_view])
        self.refreshing = True
        try:
            self.library.show(self.results, empty, preserve=selected_id)
        finally:
            self.refreshing = False
        self.count.set(f"{total:,} items · {len(self.results):,} shown")
        if not self.importing:
            self.status.set(f"Result limit reached ({self.settings.max_search_results:,}) · Refine your search"
                            if len(self.results) == self.settings.max_search_results else "Ready · All changes are stored locally")

    def select_document(self, document_id):
        if self.refreshing or document_id is None:
            return
        if self.selected_document and document_id == self.selected_document["id"]:
            return
        previous_id = self.selected_document["id"] if self.selected_document else None
        if not self.confirm_unsaved():
            if previous_id and self.library.tree.exists(str(previous_id)):
                self.library.tree.selection_set(str(previous_id))
            return
        self.show_document(self.repository.get_document(document_id))

    def show_document(self, document, preserve_edits=False):
        self.selected_document = document
        self.document_title.set(document["filename"] if document else "Your document")
        self.document_subtitle.set(f'{"NOTE" if document["is_note"] else document["file_type"].upper()}   ·   {document["word_count"]:,} words   ·   '
                                  f'{document["category"] or "Uncategorized"}' if document else "Select a document to get started")
        self.bookmark_button.configure(text="★ Bookmarked" if document and document["bookmarked"] else "☆ Bookmark",
                                       state="normal" if document else "disabled")
        self.reader_delete_button.configure(state="normal" if document else "disabled")
        self.viewer.show(document)
        self.metadata.show(document, preserve_edits=preserve_edits)
        self.analysis.show(document)
        self.related.show(document, self.repository.list_related_documents(document["id"]) if document else [])

    def open_selected(self):
        document_id = self.library.selected_id()
        if document_id is not None:
            self.open_document(document_id)

    def delete_selected(self):
        if self.importing:
            messagebox.showinfo("Document operation in progress", "Wait for the current import or reimport to finish before deleting an item.", parent=self.root)
            return
        document_id = self.library.selected_id() if self.page == "library" else (
            self.selected_document["id"] if self.page == "reader" and self.selected_document else None)
        if document_id is None or not self.confirm_unsaved():
            return
        try:
            document = self.repository.get_document(document_id)
            explanation = ("This permanently deletes the note and its text." if document["is_note"] else
                           "This removes the saved copy from Memora. Your original file stays on disk.")
            if not messagebox.askyesno("Delete library item?", f'Delete “{document["filename"]}”?\n\n{explanation}\n'
                                      "Its bookmark, bookmark note and related links will be removed. This cannot be undone.", parent=self.root):
                return
            self.repository.delete_document(document_id)
        except (MemoraError, sqlite3.Error, OSError) as exc:
            self.callback_error(type(exc), exc, None)
            return
        if self.selected_document and self.selected_document["id"] == document_id:
            self.show_document(None)
        self.refresh_labels()
        self.refresh_library()
        self.show_page("library", guard=False)
        self.status.set("Library item deleted" if document["is_note"] else "Removed from library · Original file kept")

    def open_document(self, document_id):
        if not self.confirm_unsaved():
            return
        self.show_document(self.repository.get_document(document_id))
        self.notebook.select(self.viewer)
        self.show_page("reader", guard=False)

    def toggle_bookmark(self):
        if not self.selected_document or not self.confirm_unsaved():
            return
        document = self.selected_document
        if document["bookmarked"] and document.get("bookmark_note"):
            if not messagebox.askyesno("Remove bookmark?", "Remove this bookmark and its note? Your document is kept.", parent=self.root):
                return
        self.repository.set_bookmark(document["id"], not document["bookmarked"])
        self.show_document(self.repository.get_document(document["id"]))
        self.refresh_library()
        self.status.set("Bookmark saved · Add a note in Details" if self.selected_document["bookmarked"] else "Bookmark removed")

    def document_action(self):
        if self.selected_document and self.selected_document["is_note"]:
            self.note_editor(edit=True)
        else:
            self.reimport_selected()

    def note_editor(self, edit=False):
        if edit and (not self.selected_document or not self.selected_document["is_note"]):
            self.status.set("Select a note created in Memora to edit it")
            return
        if not self.confirm_unsaved():
            return
        document = self.selected_document if edit else None
        self.editor_return = self.page if self.page != "editor" else self.editor_return
        self.show_page("editor", guard=False)
        self.editor.show(document)

    def save_note(self, *, open_after=True):
        title, content = self.editor.values()
        try:
            if self.editor.document:
                document_id = self.editor.document["id"]
                self.repository.update_note(document_id, title, content)
            else:
                document_id = self.repository.create_note(title, content)
        except (MemoraError, sqlite3.Error, OSError) as exc:
            self.callback_error(type(exc), exc, None)
            return False
        document = self.repository.get_document(document_id)
        self.editor.document = document
        self.editor.initial = self.editor.values()
        self.show_document(document)
        self.refresh_library()
        if open_after:
            self.show_page("reader", guard=False)
            self.notebook.select(self.viewer)
        self.status.set("Note saved")
        return True

    def cancel_editor(self):
        if self.editor.dirty() and not messagebox.askyesno("Discard note changes?", "Discard the unsaved changes to this note?", parent=self.root):
            return
        self.editor.show(self.editor.document)
        self.show_page(self.editor_return, guard=False)

    def manage_labels(self, kind="categories"):
        if self.show_page("organize"):
            self.organization.reload(self.categories, self.tags)
            getattr(self.organization, kind).new_button.focus_set()

    def preferences(self):
        if self.page != "preferences" and self.show_page("preferences"):
            self.preferences_page.show(self.settings)

    def save_preferences(self):
        theme, export_format, limit = self.preferences_page.values()
        try:
            new_settings = replace(self.settings, theme=theme.lower(), export_format=export_format.lower(), max_search_results=int(limit))
            new_settings.save()
        except (MemoraError, ValueError, OSError) as exc:
            messagebox.showerror("Preferences", str(exc) if isinstance(exc, MemoraError) else
                                 "Enter a whole number from 1 to 10,000 and check the data folder is writable.", parent=self.root)
            return False
        self.settings = new_settings
        self.colors = apply_theme(self.root, new_settings.theme)
        self.recolor(self.root, self.colors)
        self.preferences_page.show(new_settings)
        self.refresh_library()
        self.status.set("Preferences saved")
        return True

    def recolor(self, widget, colors):
        if isinstance(widget, tk.Canvas):
            widget.configure(background=colors["surface"])
        elif isinstance(widget, (tk.Text, tk.Listbox)):
            widget.configure(background=colors["surface"], foreground=colors["text"],
                             selectbackground=colors["accent"], selectforeground="white")
            if isinstance(widget, tk.Text):
                widget.configure(insertbackground=colors["text"])
        elif isinstance(widget, ttk.Treeview):
            widget.tag_configure("alternate", background=colors["stripe"])
        for child in widget.winfo_children():
            self.recolor(child, colors)

    def close(self):
        if self.importing:
            messagebox.showinfo("Document operation in progress", "Please wait for the current import or reimport to finish before closing Memora.", parent=self.root)
            return
        if not self.confirm_unsaved():
            return
        if self.search.pending:
            self.after_cancel(self.search.pending)
        if self.poll_id:
            self.after_cancel(self.poll_id)
        self.repository.close()
        self.root.destroy()

    def build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Import documents…", accelerator="Ctrl+O", command=self.import_files)
        file_menu.add_command(label="New note…", accelerator="Ctrl+N", command=self.note_editor)
        file_menu.add_command(label="Edit selected note…", command=lambda: self.note_editor(edit=True))
        file_menu.add_command(label="Reimport selected document", command=self.reimport_selected)
        file_menu.add_command(label="Export…", accelerator="Ctrl+E", command=self.export_dialog)
        file_menu.add_command(label="Delete selected item…", command=self.delete_selected)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        organize = tk.Menu(menu, tearoff=False)
        organize.add_command(label="Categories…", command=lambda: self.manage_labels("categories"))
        organize.add_command(label="Tags…", command=lambda: self.manage_labels("tags"))
        menu.add_cascade(label="Organize", menu=organize)
        view = tk.Menu(menu, tearoff=False)
        for name, key in (("Library", "all"), ("Notes", "notes"), ("Recent", "recent"), ("Bookmarks", "bookmarks")):
            view.add_command(label=name, command=lambda value=key: self.navigate(value))
        view.add_separator()
        view.add_command(label="Preferences…", command=self.preferences)
        menu.add_cascade(label="View", menu=view)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About Memora", command=lambda: messagebox.showinfo("About Memora",
            f"Memora {__version__}\n\nImport · Organize · Search · Read · Analyze · Bookmark · Export\n\n"
            "Your library stays on your computer. No accounts or network connection required.\n\n"
            "Keyboard: Ctrl+O import, Ctrl+N new note, Ctrl+F search, Ctrl+E export.\n"
            "PDFs are displayed as extracted text. Scanned PDFs need external OCR.", parent=self.root))
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

    def callback_error(self, exception_type, value, traceback):
        logger.error("Interface operation failed (%s).", exception_type.__name__)
        if isinstance(value, MemoraError):
            message = str(value)
        elif isinstance(value, sqlite3.Error):
            message = "The library operation failed. Check free disk space and that the data folder is writable."
        elif isinstance(value, OSError):
            message = "Cannot access the file. Check its location, permissions and available disk space."
        else:
            message = "This operation could not be completed. Your library is still available; try again."
        self.status.set("Operation failed · You can continue using Memora")
        messagebox.showerror("Memora", message, parent=self.root)

    def link_dialog(self):
        if not self.selected_document or not self.confirm_unsaved():
            return
        document_id = self.selected_document["id"]
        linked = {item["id"] for item in self.repository.list_related_documents(document_id)}
        dialog = modal(self.root, "Link a related document", "600x430")
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        query = tk.StringVar()
        ttk.Label(frame, text="Search for a note or document to link", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 10))
        entry = ttk.Entry(top, textvariable=query)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Label(frame, text="Links appear on both documents. Search to narrow the available results.",
                  style="Muted.TLabel", wraplength=540).pack(anchor="w", pady=(0, 8))
        actions = ttk.Frame(frame)
        actions.pack(side="bottom", fill="x", pady=(10, 0))
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=("title", "type"), show="headings", selectmode="browse")
        tree.heading("title", text="Document")
        tree.heading("type", text="Type")
        tree.column("title", width=420)
        tree.column("type", width=60, stretch=False)
        scrollbar = ttk.Scrollbar(body, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        empty = ttk.Label(frame, text="", style="Muted.TLabel")
        empty.pack(anchor="w")

        def search():
            try:
                rows = search_documents(self.repository, query.get(), limit=self.settings.max_search_results)
                rows = [row for row in rows if row["id"] != document_id and row["id"] not in linked]
            except MemoraError as exc:
                self.callback_error(type(exc), exc, None)
                return
            tree.delete(*tree.get_children())
            for row in rows:
                tree.insert("", "end", iid=str(row["id"]), values=(row["filename"], "NOTE" if row["is_note"] else row["file_type"].upper()))
            empty.configure(text="" if rows else "No available documents match. Import a file or create another note.")

        def link():
            if not tree.selection():
                return
            self.repository.link_documents(document_id, int(tree.selection()[0]))
            self.related.show(self.selected_document, self.repository.list_related_documents(document_id))
            self.status.set("Related documents linked")
            dialog.destroy()

        ttk.Button(top, text="Search", command=search).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda event: search())
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Link selected", style="Accent.TButton", command=link).pack(side="right", padx=8)
        search()
        entry.focus_set()

    def open_related(self):
        related_id = self.related.selected_id()
        if related_id is not None:
            self.open_document(related_id)

    def unlink_related(self):
        related_id = self.related.selected_id()
        if self.selected_document and related_id is not None:
            document_id = self.selected_document["id"]
            self.repository.unlink_documents(document_id, related_id)
            self.related.show(self.selected_document, self.repository.list_related_documents(document_id))
            self.status.set("Link removed · Both documents are kept")

    def reimport_selected(self):
        if self.importing or not self.selected_document:
            return
        if self.selected_document["is_note"]:
            self.status.set("Native notes have no original file · Use Edit note")
            return
        if not self.confirm_unsaved():
            return
        document_id = self.selected_document["id"]
        if messagebox.askyesno("Reimport document?", "Replace the saved text with the current original file?\n\n"
            "Your category, tags, bookmark notes and related links will be kept. Previous text versions are not retained.", parent=self.root):
            self.start_import([self.selected_document["filepath"]], reimport_id=document_id)

    def save_metadata(self):
        if not self.selected_document:
            return False
        category, tags, bookmarked, note = self.metadata.values()
        document_id = self.selected_document["id"]
        try:
            self.repository.update_metadata(document_id, category, tags, bookmarked=bookmarked, note=note)
        except (MemoraError, sqlite3.Error, OSError) as exc:
            self.callback_error(type(exc), exc, None)
            return False
        self.show_document(self.repository.get_document(document_id))
        self.refresh_labels()
        self.refresh_library()
        self.status.set("Document details saved")
        return True

    def copy_text(self):
        if not self.selected_document:
            return
        try:
            text = self.viewer.text.get("sel.first", "sel.last")
        except tk.TclError:
            text = self.selected_document["content"]
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Text copied to clipboard")

    def import_files(self):
        if self.importing:
            return
        paths = filedialog.askopenfilenames(parent=self.root, title="Import documents",
            filetypes=[("Supported documents", "*.txt *.md *.pdf"), ("Text", "*.txt"),
                       ("Markdown", "*.md"), ("PDF", "*.pdf"), ("All files", "*.*")])
        if paths:
            self.start_import(paths)

    def start_import(self, paths, reimport_id=None):
        if self.importing or not paths:
            return
        self.importing = True
        self.reimport_document_id = reimport_id
        self.import_button.configure(state="disabled")
        self.progress.configure(maximum=len(paths), value=0)
        self.progress.pack(side="right", padx=12)
        self.status.set("Reimporting selected document…" if reimport_id is not None else f"Importing 0 of {len(paths)} documents…")
        database_path, max_bytes = self.settings.database_path, self.settings.max_file_bytes

        def worker():
            try:
                with Repository(database_path) as repository:
                    importer = DocumentImporter(repository, max_bytes)
                    if reimport_id is not None:
                        changed = importer.reimport_file(reimport_id)
                        self.events.put(("reimported", reimport_id, changed))
                    else:
                        results = importer.import_many(paths,
                            progress=lambda index, result: self.events.put(("progress", index, len(paths))))
                        self.events.put(("done", results))
            except Exception as exc:
                logger.error("Import worker failed (%s).", type(exc).__name__)
                self.events.put(("error", str(exc) if isinstance(exc, MemoraError) else
                                 "Cannot access your library. Check the data folder and free disk space."))

        threading.Thread(target=worker, name="memora-import", daemon=True).start()
        self.poll_id = self.after(100, self.poll_import)

    def poll_import(self):
        self.poll_id = None
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    self.progress.configure(value=event[1])
                    self.status.set(f"Importing {event[1]} of {event[2]} documents…")
                else:
                    was_reimport = self.reimport_document_id is not None
                    self.importing = False
                    self.reimport_document_id = None
                    self.import_button.configure(state="normal")
                    self.progress.pack_forget()
                    if event[0] == "reimported" and self.selected_document and self.selected_document["id"] == event[1]:
                        self.show_document(self.repository.get_document(event[1]), preserve_edits=True)
                    self.refresh_library()
                    if event[0] == "done":
                        self.show_import_report(event[1])
                    elif event[0] == "reimported":
                        self.status.set("Document reimported · Organization and links kept" if event[2] else "Original file is unchanged")
                    else:
                        messagebox.showerror("Reimport failed" if was_reimport else "Import failed", event[1], parent=self.root)
                    return
        except queue.Empty:
            pass
        self.poll_id = self.after(100, self.poll_import)

    def show_import_report(self, results):
        imported = sum(item.status == "imported" for item in results)
        duplicates = sum(item.status == "duplicate" for item in results)
        failed = sum(item.status == "failed" for item in results)
        summary = f"{imported} imported · {duplicates} duplicates skipped · {failed} failed"
        self.status.set(summary)
        dialog = modal(self.root, "Import results", "680x470", grab=False)
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Import complete", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text=summary, style="Heading.TLabel").pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack(side="bottom", fill="x", pady=(16, 0))
        ttk.Button(actions, text="Done", style="Accent.TButton", command=dialog.destroy).pack(side="right")
        text = scrollable_text(frame)
        set_text(text, "\n\n".join(f"{item.filename}\n{item.status.upper()} · {item.message}" for item in results))

    def export_dialog(self, results_only=False):
        if not self.confirm_unsaved():
            return
        choices = ["Search results"]
        if self.selected_document and not results_only:
            choices = ["Document text", "Document metadata", "Analysis results"] + choices
        dialog = modal(self.root, "Export information", "500x350")
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Take a copy with you", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Save to a local file in the format you need.", style="Muted.TLabel").pack(anchor="w", pady=(0, 20))
        kind = tk.StringVar(value=choices[0])
        format = tk.StringVar(value=self.settings.export_format.upper())
        ttk.Label(frame, text="What would you like to export?").pack(anchor="w", pady=(0, 5))
        ttk.Combobox(frame, textvariable=kind, values=choices, state="readonly").pack(fill="x")
        ttk.Label(frame, text="Format").pack(anchor="w", pady=(12, 5))
        ttk.Combobox(frame, textvariable=format, values=["TXT", "CSV", "JSON"], state="readonly").pack(fill="x")

        def save():
            extension = format.get().lower()
            default_name = "memora-results" if kind.get() == "Search results" else "memora-document"
            path = filedialog.asksaveasfilename(parent=dialog, title="Save export", defaultextension="." + extension,
                initialfile=default_name + "." + extension, filetypes=[(extension.upper(), "*." + extension)],
                confirmoverwrite=False)
            if not path:
                return
            mapping = {"Document text": "text", "Document metadata": "metadata", "Analysis results": "analysis", "Search results": "results"}
            export_kind = mapping[kind.get()]
            payload = self.results if export_kind == "results" else self.analysis.result if export_kind == "analysis" else self.selected_document
            try:
                try:
                    export_data(path, export_kind, payload)
                except FileExistsError:
                    if not messagebox.askyesno("Replace existing file?", "This export file already exists. Replace it?", parent=dialog):
                        return
                    export_data(path, export_kind, payload, overwrite=True)
                self.status.set("Export saved")
                dialog.destroy()
            except (MemoraError, OSError, ValueError) as exc:
                self.callback_error(type(exc), exc, None)

        ttk.Button(frame, text="Choose destination…", style="Accent.TButton", command=save).pack(anchor="e", pady=(18, 0))
