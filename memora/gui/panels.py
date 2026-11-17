"""Library, search, reader, metadata and analysis components."""
import tkinter as tk
from tkinter import ttk

from memora.analysis import analyze_text
from memora.gui.widgets import ScrollableFrame, display_date, display_size, scrollable_text, set_text


class SearchPanel(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent, padding=18, style="Surface.TFrame")
        self.on_change = on_change
        self.pending = None
        self.query = tk.StringVar()
        self.category = tk.StringVar(value="All categories")
        self.tag = tk.StringVar(value="All tags")
        self.bookmark = tk.StringVar(value="Any bookmark status")
        self.file_type = tk.StringVar(value="All types")
        self.sort = tk.StringVar(value="Relevance")
        self.categories = []
        self.tags = []
        top = ttk.Frame(self, style="Surface.TFrame")
        top.pack(fill="x")
        self.entry = ttk.Entry(top, textvariable=self.query, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Search", command=self.submit).pack(side="left", padx=(10, 0))
        self.filter_button = ttk.Button(top, text="Filters", command=self.toggle_filters)
        self.filter_button.pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Reset", command=self.reset).pack(side="left", padx=(8, 0))
        self.entry.bind("<Return>", lambda event: self.submit())
        self.query.trace_add("write", self.schedule)
        self.filter_area = ttk.Frame(self, style="Surface.TFrame")
        self.filter_area.columnconfigure((0, 1, 2, 3), weight=1, uniform="filters")
        self.filters_visible = False
        self.category_box = self._filter("Category", self.category, ["All categories"], 0)
        self.tag_box = self._filter("Tag", self.tag, ["All tags"], 1)
        self.bookmark_box = self._filter("Bookmark", self.bookmark, ["Any bookmark status", "Bookmarked", "Not bookmarked"], 2)
        self.type_box = self._filter("Format", self.file_type, ["All types", "TXT", "MD", "PDF", "Note"], 3)
        self.bottom = ttk.Frame(self, style="Surface.TFrame")
        self.bottom.pack(fill="x", pady=(14, 0))
        ttk.Label(self.bottom, text="Search filenames, document text, categories and tags", style="SurfaceMuted.TLabel").pack(side="left")
        self.sort_box = ttk.Combobox(self.bottom, textvariable=self.sort, values=["Relevance", "Filename", "Newest", "Oldest", "Word count"],
                                    state="readonly", width=12)
        self.sort_box.pack(side="right")
        self.sort_box.bind("<<ComboboxSelected>>", lambda event: self.submit())
        ttk.Label(self.bottom, text="Sort by", style="SurfaceMuted.TLabel").pack(side="right", padx=(12, 8))

    def _filter(self, label, variable, values, column):
        frame = ttk.Frame(self.filter_area, style="Surface.TFrame")
        frame.grid(row=0, column=column, sticky="ew", padx=(0, 10 if column < 3 else 0))
        ttk.Label(frame, text=label, style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 5))
        combo = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=12)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda event: self.submit())
        return combo

    def toggle_filters(self):
        self.filters_visible = not self.filters_visible
        if self.filters_visible:
            self.filter_area.pack(fill="x", pady=(18, 0), before=self.bottom)
        else:
            self.filter_area.pack_forget()

    def update_filter_summary(self):
        filters = self.filters()
        count = sum(filters[key] is not None for key in ("category_id", "tag_id", "bookmarked", "file_type"))
        self.filter_button.configure(text=f"Filters ({count})" if count else "Filters")

    def schedule(self, *args):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(300, self.submit)

    def submit(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        self.on_change()

    def reset(self):
        self.query.set("")
        self.category.set("All categories")
        self.tag.set("All tags")
        self.bookmark.set("Any bookmark status")
        self.file_type.set("All types")
        self.sort.set("Relevance")
        self.submit()

    def refresh_labels(self, categories, tags):
        old_category = self.selected_id(self.category_box, self.categories)
        old_tag = self.selected_id(self.tag_box, self.tags)
        self.categories, self.tags = categories, tags
        self.category_box.configure(values=["All categories"] + [item["name"] for item in categories])
        self.tag_box.configure(values=["All tags"] + [item["name"] for item in tags])
        self.select_id(self.category_box, categories, old_category)
        self.select_id(self.tag_box, tags, old_tag)

    @staticmethod
    def selected_id(combo, items):
        index = combo.current() - 1
        return items[index]["id"] if 0 <= index < len(items) else None

    @staticmethod
    def select_id(combo, items, item_id):
        combo.current(next((index + 1 for index, item in enumerate(items) if item["id"] == item_id), 0))

    def filters(self):
        return {
            "category_id": self.selected_id(self.category_box, self.categories),
            "tag_id": self.selected_id(self.tag_box, self.tags),
            "bookmarked": {"Any bookmark status": None, "Bookmarked": True, "Not bookmarked": False}[self.bookmark.get()],
            "file_type": None if self.file_type.get() == "All types" else self.file_type.get().lower(),
            "sort": self.sort.get().lower(),
        }


class DocumentPanel(ttk.Frame):
    def __init__(self, parent, on_select, on_open, on_export, on_delete):
        super().__init__(parent)
        self._displayed = {}
        self.title = tk.StringVar(value="All documents")
        self.summary = tk.StringVar(value="0 documents")
        top = ttk.Frame(self, padding=(0, 0, 0, 12))
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.title, style="Muted.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.summary, style="Muted.TLabel").pack(side="right")
        actions = ttk.Frame(self, padding=(0, 14, 0, 0))
        actions.pack(side="bottom", fill="x")
        self.open_button = ttk.Button(actions, text="Open document →", style="Accent.TButton", command=on_open, state="disabled")
        self.open_button.pack(side="right")
        ttk.Button(actions, text="Export results", command=on_export).pack(side="right", padx=(0, 8))
        self.delete_button = ttk.Button(actions, text="Delete", width=7, command=on_delete, state="disabled")
        self.delete_button.pack(side="right", padx=(0, 8))
        self.selection_summary = tk.StringVar(value="Select a document, then open it to read.")
        ttk.Label(actions, textvariable=self.selection_summary, style="Muted.TLabel").pack(side="left")
        body = ttk.Frame(self, style="Surface.TFrame")
        body.pack(fill="both", expand=True)
        columns = ("filename", "file_type", "category", "tags", "word_count", "imported_at", "bookmarked")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        labels = ("Document", "Type", "Category", "Tags", "Words", "Added", "Saved")
        widths = (260, 70, 125, 135, 75, 115, 65)
        for column, label, width in zip(columns, labels, widths):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=55, stretch=column == "filename",
                             anchor="center" if column in {"file_type", "word_count", "bookmarked"} else "w")
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.empty = ttk.Label(body, text="No documents in your library yet.\nImport TXT, Markdown or PDF to get started.",
                               anchor="center", justify="center", padding=24, style="SurfaceMuted.TLabel", font=("Segoe UI", 12))
        def selection(event=None):
            self.open_button.configure(state="normal" if self.selected_id() else "disabled")
            self.delete_button.configure(state="normal" if self.selected_id() else "disabled")
            self.selection_summary.set("Double-click a document to open it." if self.selected_id() else "Select a document, then open it to read.")
            on_select(self.selected_id())
        self.tree.bind("<<TreeviewSelect>>", selection)
        self.tree.bind("<Double-1>", lambda event: on_open() if self.tree.identify_region(event.x, event.y) == "cell" else None)
        self.tree.bind("<Return>", lambda event: on_open())

    def selected_id(self):
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def show(self, results, empty_message, preserve=None):
        current_order = self.tree.get_children()
        current = set(current_order)
        selection = self.tree.selection()
        position = self.tree.yview()[0]
        incoming = []
        displayed = {}
        self.summary.set(f"{len(results):,} shown")
        for index, item in enumerate(results):
            iid = str(item['id'])
            incoming.append(iid)
            values = (item["filename"], "NOTE" if item["is_note"] else item["file_type"].upper(),
                item["category"] or "—", ", ".join(item["tags"]) or "—", f'{item["word_count"]:,}',
                display_date(item["imported_at"]), "★" if item["bookmarked"] else "")
            tags = ('alternate',) if index % 2 else ()
            displayed[iid] = (values, tags)
            if iid not in current:
                self.tree.insert('', 'end', iid=iid, values=values, tags=tags)
            elif self._displayed.get(iid) != (values, tags):
                self.tree.item(iid, values=values, tags=tags)
        self._displayed = displayed
        removed = current - set(incoming)
        if removed:
            self.tree.delete(*removed)
        if tuple(incoming) != current_order:
            self.tree.set_children('', *incoming)
        self.tree.yview_moveto(position)
        if results:
            self.empty.place_forget()
        else:
            self.empty.configure(text=empty_message)
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        if preserve is not None and self.tree.exists(str(preserve)) and selection != (str(preserve),):
            self.tree.selection_set(str(preserve))
            self.tree.see(str(preserve))
        self.open_button.configure(state="normal" if self.selected_id() else "disabled")
        self.delete_button.configure(state="normal" if self.selected_id() else "disabled")


class DocumentViewer(ttk.Frame):
    def __init__(self, parent, on_copy, on_action):
        super().__init__(parent, padding=(20, 14, 20, 20), style="Surface.TFrame")
        toolbar = ttk.Frame(self, padding=(0, 0, 0, 14), style="Surface.TFrame")
        toolbar.pack(fill="x")
        self.text_label = ttk.Label(toolbar, text="Extracted text", style="SurfaceMuted.TLabel")
        self.text_label.pack(side="left")
        self.copy_button = ttk.Button(toolbar, text="Copy text", command=on_copy, state="disabled")
        self.copy_button.pack(side="right")
        self.action_button = ttk.Button(toolbar, text="Reimport", command=on_action, state="disabled")
        self.action_button.pack(side="right", padx=(0, 6))
        self.text = scrollable_text(self, font=("Segoe UI", 12), spacing1=3, spacing3=6)
        set_text(self.text, "Select a document to view its contents.")

    def show(self, document):
        set_text(self.text, document["content"] if document else "Select a document to view its contents.")
        self.copy_button.configure(state="normal" if document else "disabled")
        is_note = bool(document and document["is_note"])
        self.text_label.configure(text="Note text" if is_note else "Extracted text")
        self.action_button.configure(text="Edit note" if is_note else "Reimport", state="normal" if document else "disabled")


class MetadataPanel(ScrollableFrame):
    def __init__(self, parent, on_save, on_manage):
        super().__init__(parent, style="Surface.TFrame")
        form = self.content
        self.document = None
        self.categories = []
        self.tags = []
        self.category = tk.StringVar(value="Uncategorized")
        self.bookmarked = tk.BooleanVar(value=False)
        form.columnconfigure(1, weight=1)
        self.info = {}
        for row, (key, label) in enumerate((("file_type", "Format"), ("file_size", "File size"),
                                           ("imported_at", "Imported"), ("modified_at", "File modified"),
                                           ("filepath", "Original path"))):
            ttk.Label(form, text=label, style="SurfaceMuted.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 18), pady=4)
            value = tk.StringVar(value="—")
            self.info[key] = value
            ttk.Entry(form, textvariable=value, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Separator(form).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(form, text="Category", style="Surface.TLabel").grid(row=6, column=0, sticky="w")
        self.category_box = ttk.Combobox(form, textvariable=self.category, state="readonly", values=["Uncategorized"])
        self.category_box.grid(row=6, column=1, sticky="ew")
        ttk.Label(form, text="Tags", style="Surface.TLabel").grid(row=7, column=0, sticky="nw", pady=12)
        tag_frame = ttk.Frame(form, style="Surface.TFrame")
        tag_frame.grid(row=7, column=1, sticky="nsew", pady=(12, 0))
        self.tag_list = tk.Listbox(tag_frame, selectmode="multiple", exportselection=False, height=5,
                                  relief="flat", borderwidth=1)
        tag_scroll = ttk.Scrollbar(tag_frame, orient="vertical", command=self.tag_list.yview)
        self.tag_list.configure(yscrollcommand=tag_scroll.set)
        tag_scroll.pack(side="right", fill="y")
        self.tag_list.pack(fill="both", expand=True)
        ttk.Label(form, text="Select tags with a click. Create your own in Organize.", style="SurfaceMuted.TLabel",
                  wraplength=540).grid(row=8, column=1, sticky="w", pady=(5, 10))
        self.bookmark_check = ttk.Checkbutton(form, text="Bookmark this document", variable=self.bookmarked,
                                             command=self.toggle_note, style="Surface.TCheckbutton")
        self.bookmark_check.grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(form, text="Bookmark note", style="Surface.TLabel").grid(row=10, column=0, columnspan=2, sticky="w")
        self.note = tk.Text(form, height=4, wrap="word", relief="flat", padx=8, pady=8)
        self.note.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(5, 10))
        actions = ttk.Frame(self, padding=(24, 12), style="Surface.TFrame")
        actions.pack(side="bottom", fill="x", before=self.canvas)
        self.save_button = ttk.Button(actions, text="Save changes", style="Accent.TButton", command=on_save, state="disabled")
        self.save_button.pack(side="left")
        ttk.Button(actions, text="Organize…", command=on_manage).pack(side="left", padx=8)

    def toggle_note(self):
        self.note.configure(state="normal" if self.document and self.bookmarked.get() else "disabled")

    def refresh_labels(self, categories, tags):
        self.categories, self.tags = categories, tags
        self.category_box.configure(values=["Uncategorized"] + [item["name"] for item in categories])
        self.tag_list.configure(state="normal")
        self.tag_list.delete(0, "end")
        for item in tags:
            self.tag_list.insert("end", item["name"])
        self.show(self.document)

    def show(self, document, preserve_edits=False):
        draft = self.values() if (preserve_edits and self.document and document
                                  and self.document["id"] == document["id"] and self.dirty()) else None
        self.document = document
        for key, value in self.info.items():
            if not document:
                value.set("—")
            elif key == "file_size":
                value.set(display_size(document[key]))
            elif key in {"imported_at", "modified_at"}:
                value.set(display_date(document[key], full=True))
            else:
                value.set(("NOTE" if document["is_note"] else document[key].upper()) if key == "file_type"
                          else "Stored in Memora" if document["is_note"] and key == "filepath" else document[key])
        SearchPanel.select_id(self.category_box, self.categories, document["category_id"] if document else None)
        self.tag_list.configure(state="normal")
        self.tag_list.selection_clear(0, "end")
        selected_tags = {tag["id"] for tag in document["tags"]} if document else set()
        for index, tag in enumerate(self.tags):
            if tag["id"] in selected_tags:
                self.tag_list.selection_set(index)
        self.bookmarked.set(bool(document and document["bookmarked"]))
        set_text(self.note, (document.get("bookmark_note") or "") if document else "", readonly=False)
        self.toggle_note()
        state = "normal" if document else "disabled"
        self.save_button.configure(state=state)
        self.bookmark_check.configure(state=state)
        self.tag_list.configure(state=state)
        self.category_box.configure(state="readonly" if document else "disabled")
        if draft:
            category, tags, bookmarked, note = draft
            SearchPanel.select_id(self.category_box, self.categories, category)
            self.tag_list.selection_clear(0, "end")
            for index, tag in enumerate(self.tags):
                if tag["id"] in tags:
                    self.tag_list.selection_set(index)
            self.bookmarked.set(bookmarked)
            set_text(self.note, note, readonly=False)
            self.toggle_note()

    def values(self):
        return (SearchPanel.selected_id(self.category_box, self.categories),
                [self.tags[index]["id"] for index in self.tag_list.curselection()],
                self.bookmarked.get(), self.note.get("1.0", "end-1c"))

    def dirty(self):
        if not self.document:
            return False
        category, tags, bookmarked, note = self.values()
        return (category != self.document["category_id"] or set(tags) != {tag["id"] for tag in self.document["tags"]}
                or bookmarked != self.document["bookmarked"]
                or (bookmarked and note != (self.document.get("bookmark_note") or "")))


class RelatedPanel(ttk.Frame):
    def __init__(self, parent, on_add, on_open, on_remove):
        super().__init__(parent, padding=24, style="Surface.TFrame")
        ttk.Label(self, text="Connect notes and documents that belong together.",
                  style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 18))
        actions = ttk.Frame(self, style="Surface.TFrame")
        actions.pack(fill="x", pady=(0, 12))
        self.add_button = ttk.Button(actions, text="Link document…", command=on_add, state="disabled")
        self.add_button.pack(side="left")
        self.open_button = ttk.Button(actions, text="Open", command=on_open, state="disabled")
        self.open_button.pack(side="left", padx=6)
        self.remove_button = ttk.Button(actions, text="Unlink", command=on_remove, state="disabled")
        self.remove_button.pack(side="left")
        body = ttk.Frame(self, style="Surface.TFrame")
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("title", "type"), show="headings", selectmode="browse")
        self.tree.heading("title", text="Related document")
        self.tree.heading("type", text="Type")
        self.tree.column("title", width=240, minwidth=100)
        self.tree.column("type", width=60, stretch=False)
        scrollbar = ttk.Scrollbar(body, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.empty = ttk.Label(self, text="Select a document to view its links.", style="SurfaceMuted.TLabel", wraplength=650)
        self.empty.pack(anchor="w", pady=(10, 0))
        self.tree.bind("<<TreeviewSelect>>", self.selection_changed)
        self.tree.bind("<Double-1>", lambda event: on_open())

    def selected_id(self):
        return int(self.tree.selection()[0]) if self.tree.selection() else None

    def selection_changed(self, event=None):
        state = "normal" if self.selected_id() is not None else "disabled"
        self.open_button.configure(state=state)
        self.remove_button.configure(state=state)

    def show(self, document, related):
        self.tree.delete(*self.tree.get_children())
        for item in related:
            self.tree.insert("", "end", iid=str(item["id"]), values=(item["filename"],
                             "NOTE" if item["is_note"] else item["file_type"].upper()))
        self.add_button.configure(state="normal" if document else "disabled")
        self.selection_changed()
        self.empty.configure(text=("" if related else "No related documents yet. Choose Link document to connect one.")
                             if document else "Select a document to view its links.")


class AnalysisPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=22, style="Surface.TFrame")
        self.document = None
        self.result = None
        self.ignore_stop_words = tk.BooleanVar(value=True)
        metrics = ttk.Frame(self, style="Surface.TFrame")
        metrics.pack(fill="x", pady=(0, 18))
        metrics.columnconfigure((0, 1, 2, 3), weight=1, uniform="metrics")
        self.metrics = {}
        labels = (("Words", "word_count"), ("Unique words", "unique_word_count"),
                  ("Characters", "character_count"), ("Reading time", "reading_time_minutes"),
                  ("Characters without spaces", "characters_without_spaces"), ("Lines", "line_count"),
                  ("Paragraphs", "paragraph_count"), ("Average word length", "average_word_length"))
        for index, (label, key) in enumerate(labels):
            value = tk.StringVar(value="—")
            self.metrics[key] = value
            ttk.Label(metrics, textvariable=value, style="Metric.TLabel").grid(
                row=index // 4 * 2, column=index % 4, sticky="w", padx=12, pady=(8, 0))
            ttk.Label(metrics, text=label, style="SurfaceMuted.TLabel", wraplength=145).grid(
                row=index // 4 * 2 + 1, column=index % 4, sticky="nw", padx=12, pady=(0, 12))
        ttk.Separator(self).pack(fill="x", pady=(0, 16))
        frequency_header = ttk.Frame(self, style="Surface.TFrame")
        frequency_header.pack(fill="x", pady=(0, 10))
        ttk.Label(frequency_header, text="Most frequent words", style="SurfaceHeading.TLabel").pack(side="left")
        ttk.Label(frequency_header, text="Reading time at 200 words / minute", style="SurfaceMuted.TLabel").pack(side="right")
        ttk.Checkbutton(self, text="Ignore common English words in frequencies", variable=self.ignore_stop_words,
                        command=self.refresh, style="Surface.TCheckbutton").pack(anchor="w", pady=(0, 12))
        self.empty = ttk.Label(self, text="", style="SurfaceMuted.TLabel")
        self.empty.pack(side="bottom", anchor="w", pady=(8, 0))
        body = ttk.Frame(self, style="Surface.TFrame")
        body.pack(fill="both", expand=True)
        self.frequency_tree = ttk.Treeview(body, columns=("word", "count"), show="headings", height=4)
        self.frequency_tree.heading("word", text="Word")
        self.frequency_tree.heading("count", text="Occurrences")
        self.frequency_tree.column("word", width=350)
        self.frequency_tree.column("count", width=150, stretch=False, anchor="center")
        scrollbar = ttk.Scrollbar(body, command=self.frequency_tree.yview)
        self.frequency_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.frequency_tree.pack(fill="both", expand=True)
        self.refresh()

    def show(self, document):
        self.document = document
        self.refresh()

    def refresh(self):
        self.frequency_tree.delete(*self.frequency_tree.get_children())
        if not self.document:
            self.result = None
            for value in self.metrics.values():
                value.set("—")
            self.empty.configure(text="Select a document to analyze its text.")
            return
        self.result = analyze_text(self.document["content"], self.ignore_stop_words.get())
        seconds = round(self.result["word_count"] / 200 * 60)
        for key, value in self.metrics.items():
            value.set(f"{seconds // 60}m {seconds % 60}s" if key == "reading_time_minutes" else f"{self.result[key]:,}")
        for index, item in enumerate(self.result["frequent_words"]):
            self.frequency_tree.insert("", "end", values=(item["word"], item["count"]), tags=("alternate",) if index % 2 else ())
        self.empty.configure(text="" if self.result["frequent_words"] else "No words remain after filtering.")
