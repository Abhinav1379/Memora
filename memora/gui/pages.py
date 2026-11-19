"""Focused pages for writing, organizing and preferences."""
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from memora.errors import MemoraError
from memora.gui.widgets import ScrollableFrame, modal, scrollable_text, set_text


def page_header(parent, title, subtitle):
    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(0, 24))
    actions = ttk.Frame(header)
    actions.pack(side="right", anchor="n", pady=6)
    heading = ttk.Frame(header)
    heading.pack(side="left", fill="x", expand=True)
    title_options = {"textvariable": title} if isinstance(title, tk.Variable) else {"text": title}
    ttk.Label(heading, style="Title.TLabel", **title_options).pack(anchor="w")
    description = ttk.Label(heading, text=subtitle, style="Muted.TLabel")
    description.pack(anchor="w", pady=(6, 0))
    heading.bind("<Configure>", lambda event: description.configure(wraplength=max(200, event.width)))
    return actions


class NoteEditorPage(ttk.Frame):
    def __init__(self, parent, on_save, on_cancel):
        super().__init__(parent)
        self.document = None
        self.initial = ("", "")
        self.title = tk.StringVar()
        self.heading = tk.StringVar(value="New note")
        actions = page_header(self, self.heading, "A little space for your thoughts. Saved directly in your library.")
        self.save_button = ttk.Button(actions, text="Save note", style="Accent.TButton", command=on_save)
        self.save_button.pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Cancel", command=on_cancel).pack(side="right")
        title_card = ttk.Frame(self, padding=(24, 18), style="Surface.TFrame")
        title_card.pack(fill="x", pady=(0, 14))
        ttk.Label(title_card, text="TITLE", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 8))
        self.title_entry = ttk.Entry(title_card, textvariable=self.title, font=("Segoe UI", 15))
        self.title_entry.pack(fill="x")
        footer = ttk.Frame(self)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Label(footer, text="Plain text · Titles can contain up to 80 characters", style="Muted.TLabel").pack(anchor="w")
        self.text = scrollable_text(self, font=("Segoe UI", 12), undo=True, spacing1=3, spacing3=6)

    def show(self, document=None):
        self.document = document
        self.initial = (document["filename"], document["content"]) if document else ("", "")
        self.heading.set("Edit note" if document else "New note")
        self.title.set(self.initial[0])
        set_text(self.text, self.initial[1], readonly=False)
        self.text.edit_reset()
        self.title_entry.focus_set()

    def values(self):
        return self.title.get(), self.text.get("1.0", "end-1c")

    def dirty(self):
        return self.values() != self.initial


class LabelManagerPanel(ttk.Frame):
    def __init__(self, parent, kind, repository, on_changed, on_error, on_filter):
        super().__init__(parent, padding=22, style="Surface.TFrame")
        self.kind, self.repository = kind, repository
        self.on_changed, self.on_error, self.on_filter = on_changed, on_error, on_filter
        self.items = []
        header = ttk.Frame(self, style="Surface.TFrame")
        header.pack(fill="x", pady=(0, 8))
        name = "category" if kind == "categories" else "tag"
        ttk.Label(header, text=kind.title(), style="SurfaceHeading.TLabel").pack(side="left")
        self.new_button = ttk.Button(header, text=f"+ New {name}", command=self.create)
        self.new_button.pack(side="right")
        ttk.Label(self, text="One home per document." if kind == "categories" else "Flexible labels. Use as many as you like.",
                  style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 18))
        actions = ttk.Frame(self, style="Surface.TFrame")
        actions.pack(side="bottom", fill="x", pady=(18, 0))
        self.rename_button = ttk.Button(actions, text="Rename", width=6, command=self.rename, state="disabled")
        self.rename_button.pack(side="left")
        self.delete_button = ttk.Button(actions, text="Delete", width=6, command=self.delete, state="disabled")
        self.delete_button.pack(side="left", padx=6)
        self.browse_button = ttk.Button(actions, text="View documents", width=12, command=self.browse, state="disabled")
        self.browse_button.pack(side="right")
        body = ttk.Frame(self, style="Surface.TFrame")
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("name", "count"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Name")
        self.tree.heading("count", text="Documents")
        self.tree.column("name", width=180, minwidth=120)
        self.tree.column("count", width=115, minwidth=105, stretch=False, anchor="center")
        scrollbar = ttk.Scrollbar(body, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.empty = ttk.Label(body, text=f"No {kind} created yet.\nCreate your first {name} above.",
                               style="SurfaceMuted.TLabel", justify="center", anchor="center")
        self.tree.bind("<<TreeviewSelect>>", self.selection_changed)
        self.tree.bind("<Double-1>", lambda event: self.browse())

    def reload(self, items):
        selected = self.selected()
        self.items = items
        self.tree.delete(*self.tree.get_children())
        for item in items:
            self.tree.insert("", "end", iid=str(item["id"]), values=(item["name"], item["document_count"]))
        if selected and self.tree.exists(str(selected["id"])):
            self.tree.selection_set(str(selected["id"]))
        if items:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
        self.selection_changed()

    def selected(self):
        selection = self.tree.selection()
        return next((item for item in self.items if selection and item["id"] == int(selection[0])), None)

    def selection_changed(self, event=None):
        state = "normal" if self.selected() else "disabled"
        for button in (self.rename_button, self.delete_button, self.browse_button):
            button.configure(state=state)

    def create(self):
        self.edit_dialog()

    def rename(self):
        if self.selected():
            self.edit_dialog(self.selected())

    def edit_dialog(self, item=None):
        category = self.kind == "categories"
        label = "category" if category else "tag"
        dialog = modal(self.winfo_toplevel(), f"Rename {label}" if item else f"New {label}",
                       "480x320" if category and not item else "480x240")
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        name = tk.StringVar(value=item["name"] if item else "")
        description = tk.StringVar()
        ttk.Label(frame, text=f"{'Rename' if item else 'Create'} a {label}", style="Heading.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(frame, text="Name · 1–80 characters", style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
        entry = ttk.Entry(frame, textvariable=name)
        entry.pack(fill="x")
        if category and not item:
            ttk.Label(frame, text="Description (optional)", style="Muted.TLabel").pack(anchor="w", pady=(12, 5))
            ttk.Entry(frame, textvariable=description).pack(fill="x")
        actions = ttk.Frame(frame)
        actions.pack(side="bottom", fill="x", pady=(18, 0))

        def save():
            try:
                if item:
                    method = self.repository.rename_category if category else self.repository.rename_tag
                    method(item["id"], name.get())
                elif category:
                    self.repository.create_category(name.get(), description.get())
                else:
                    self.repository.create_tag(name.get())
                self.on_changed()
                dialog.destroy()
            except (MemoraError, sqlite3.Error, OSError) as exc:
                self.on_error(type(exc), exc, None)

        ttk.Button(actions, text="Save" if item else "Create", style="Accent.TButton", command=save).pack(side="right")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)
        entry.bind("<Return>", lambda event: save())
        entry.focus_set()

    def delete(self):
        item = self.selected()
        if not item:
            return
        category = self.kind == "categories"
        explanation = "Documents in it will become uncategorized." if category else "This tag will be removed from assigned documents."
        if messagebox.askyesno("Delete category?" if category else "Delete tag?",
                              f'Delete “{item["name"]}”?\n\n{explanation}\nYour documents are kept.', parent=self.winfo_toplevel()):
            method = self.repository.delete_category if category else self.repository.delete_tag
            method(item["id"])
            self.on_changed()

    def browse(self):
        item = self.selected()
        if item:
            self.on_filter(self.kind, item["id"])


class OrganizationPage(ttk.Frame):
    def __init__(self, parent, repository, on_changed, on_error, on_filter):
        super().__init__(parent)
        page_header(self, "Organize", "Make room for your own way of thinking. Your labels, your library.")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure((0, 1), weight=1, uniform="organization")
        body.rowconfigure(0, weight=1)
        self.categories = LabelManagerPanel(body, "categories", repository, on_changed, on_error, on_filter)
        self.tags = LabelManagerPanel(body, "tags", repository, on_changed, on_error, on_filter)
        self.categories.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tags.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def reload(self, categories, tags):
        self.categories.reload(categories)
        self.tags.reload(tags)


class PreferencesPage(ttk.Frame):
    def __init__(self, parent, on_save, on_cancel):
        super().__init__(parent)
        self.initial = None
        self.theme = tk.StringVar()
        self.export_format = tk.StringVar()
        self.limit = tk.StringVar()
        actions = page_header(self, "Preferences", "A few small choices to make Memora feel like home.")
        self.save_button = ttk.Button(actions, text="Save preferences", style="Accent.TButton", command=on_save)
        self.save_button.pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Cancel", command=on_cancel).pack(side="right")
        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        form = scroll.content
        for label, variable, choices, help_text in (
            ("Appearance", self.theme, ["Light", "Dark"], "Choose a comfortable theme for reading and browsing."),
            ("Default export format", self.export_format, ["TXT", "CSV", "JSON"], "You can choose another format each time you export."),
        ):
            ttk.Label(form, text=label, style="SurfaceHeading.TLabel").pack(anchor="w", pady=(0, 6))
            ttk.Label(form, text=help_text, style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 10))
            ttk.Combobox(form, textvariable=variable, values=choices, state="readonly", width=28).pack(anchor="w", pady=(0, 26))
        ttk.Label(form, text="Search result limit", style="SurfaceHeading.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(form, text="Show between 1 and 10,000 results at a time.", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Entry(form, textvariable=self.limit, width=30).pack(anchor="w", pady=(0, 26))
        ttk.Separator(form).pack(fill="x", pady=(0, 22))
        ttk.Label(form, text="Your local library", style="SurfaceHeading.TLabel").pack(anchor="w", pady=(0, 8))
        self.data_folder = tk.StringVar()
        ttk.Label(form, textvariable=self.data_folder, style="SurfaceMuted.TLabel", wraplength=650).pack(anchor="w")
        ttk.Label(form, text="Documents, notes and preferences stay on this computer.\nTo back up your library, close Memora and copy its data folder.",
                  style="SurfaceMuted.TLabel", wraplength=650).pack(anchor="w", pady=(12, 0))

    def show(self, settings):
        self.theme.set(settings.theme.title())
        self.export_format.set(settings.export_format.upper())
        self.limit.set(str(settings.max_search_results))
        self.data_folder.set(str(settings.data_dir))
        self.initial = self.values()

    def values(self):
        return self.theme.get(), self.export_format.get(), self.limit.get()

    def dirty(self):
        return self.initial is not None and self.values() != self.initial
