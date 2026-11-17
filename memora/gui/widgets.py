"""Shared visual styles and small desktop helpers."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk

PALETTES = {
    "light": {"background": "#F4F6F3", "surface": "#FFFFFF", "text": "#1D3535", "muted": "#627775",
              "border": "#DDE5DF", "accent": "#237D65", "active": "#19634F", "selection": "#DDEEE5",
              "stripe": "#F8FAF7", "sidebar": "#142E30", "nav_active": "#285052"},
    "dark": {"background": "#182526", "surface": "#213233", "text": "#EAF2ED", "muted": "#ABBFBA",
             "border": "#3A504D", "accent": "#308C70", "active": "#247258", "selection": "#355C4E",
             "stripe": "#253839", "sidebar": "#102325", "nav_active": "#285052"},
}


def apply_theme(root: tk.Tk, theme: str):
    colors = PALETTES[theme]
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=colors["background"])
    root.option_add("*Listbox.font", "{Segoe UI} 10")
    root.option_add("*Text.font", "{Segoe UI} 10")
    root.option_add("*Menu.font", "{Segoe UI} 10")
    root.option_add("*Listbox.background", colors["surface"])
    root.option_add("*Listbox.foreground", colors["text"])
    root.option_add("*Listbox.selectBackground", colors["accent"])
    root.option_add("*Listbox.selectForeground", "white")
    root.option_add("*Text.background", colors["surface"])
    root.option_add("*Text.foreground", colors["text"])
    root.option_add("*Text.insertBackground", colors["text"])
    style.configure(".", background=colors["background"], foreground=colors["text"], font=("Segoe UI", 10))
    style.configure("TFrame", background=colors["background"])
    style.configure("Surface.TFrame", background=colors["surface"])
    style.configure("Sidebar.TFrame", background=colors["sidebar"])
    style.configure("TLabel", background=colors["background"])
    style.configure("Muted.TLabel", foreground=colors["muted"])
    style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
    style.configure("Heading.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("Surface.TLabel", background=colors["surface"])
    style.configure("SurfaceMuted.TLabel", background=colors["surface"], foreground=colors["muted"])
    style.configure("SurfaceHeading.TLabel", background=colors["surface"], font=("Segoe UI", 14, "bold"))
    style.configure("Metric.TLabel", background=colors["surface"], font=("Segoe UI", 24, "bold"))
    style.configure("Brand.TLabel", background=colors["sidebar"], foreground="#F0F6F0", font=("Segoe UI", 22, "bold"))
    style.configure("Sidebar.TLabel", background=colors["sidebar"], foreground="#ADBFBA")
    style.configure("BrandMark.TLabel", background="#DCEED9", foreground="#204539", font=("Segoe UI", 19, "bold"), padding=(12, 4))
    style.configure("TButton", padding=(14, 9), borderwidth=1, bordercolor=colors["border"],
                    background=colors["surface"], lightcolor=colors["border"], darkcolor=colors["border"])
    style.map("TButton", background=[("active", colors["selection"])], foreground=[("disabled", colors["muted"])])
    style.configure("Accent.TButton", background=colors["accent"], foreground="white", borderwidth=0)
    style.map("Accent.TButton", background=[("active", colors["active"]), ("disabled", colors["border"])],
              foreground=[("disabled", colors["muted"]), ("!disabled", "white")])
    for name, background in (("Nav.TButton", colors["sidebar"]), ("NavSelected.TButton", colors["nav_active"])):
        style.configure(name, background=background, foreground="#EFF5EF", anchor="w", padding=(18, 13),
                        borderwidth=0, font=("Segoe UI", 11))
        style.map(name, background=[("active", colors["nav_active"]), ("!active", background)],
                  foreground=[("!disabled", "#EFF5EF")])
    style.configure("TEntry", fieldbackground=colors["surface"], foreground=colors["text"], padding=9,
                    bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"])
    style.map("TEntry", bordercolor=[("focus", colors["accent"])])
    style.configure("TCombobox", fieldbackground=colors["surface"], foreground=colors["text"], padding=7,
                    bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"],
                    arrowcolor=colors["muted"])
    style.map("TCombobox", fieldbackground=[("disabled", colors["stripe"]), ("readonly", colors["surface"])],
              foreground=[("readonly", colors["text"])], selectbackground=[("readonly", colors["surface"])],
              selectforeground=[("readonly", colors["text"])], bordercolor=[("focus", colors["accent"])])
    style.configure("Treeview", background=colors["surface"], fieldbackground=colors["surface"],
                    foreground=colors["text"], rowheight=49, borderwidth=0, font=("Segoe UI", 10),
                    bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"])
    style.map("Treeview", background=[("selected", colors["selection"])], foreground=[("selected", colors["text"])])
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(12, 12), relief="flat",
                    background=colors["surface"], foreground=colors["muted"])
    style.map("Treeview.Heading", background=[("active", colors["stripe"])])
    style.configure("TNotebook", background=colors["background"], borderwidth=0, bordercolor=colors["border"],
                    lightcolor=colors["border"], darkcolor=colors["border"])
    style.configure("TNotebook.Tab", padding=(22, 12), borderwidth=0, background=colors["background"],
                    bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"])
    style.map("TNotebook.Tab", background=[("selected", colors["surface"]), ("active", colors["selection"])],
              foreground=[("selected", colors["accent"])])
    style.configure("TCheckbutton", background=colors["background"])
    style.configure("Surface.TCheckbutton", background=colors["surface"])
    style.map("Surface.TCheckbutton", background=[("active", colors["surface"])])
    style.configure("Horizontal.TProgressbar", background=colors["accent"], troughcolor=colors["border"], borderwidth=0)
    style.configure("TScrollbar", background=colors["border"], troughcolor=colors["surface"],
                    bordercolor=colors["surface"], lightcolor=colors["border"], darkcolor=colors["border"],
                    arrowcolor=colors["muted"], borderwidth=0)
    style.map("TScrollbar", background=[("active", colors["muted"])])
    style.configure("TSeparator", background=colors["border"])
    return colors


def display_date(value: str | None, *, full: bool = False) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value).astimezone()
        return parsed.strftime("%d %b %Y, %H:%M" if full else "%d %b %Y")
    except ValueError:
        return value


def display_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{size:,} B"
        size /= 1024


def set_text(widget: tk.Text, content: str, *, readonly: bool = True):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    if readonly:
        widget.configure(state="disabled")
    widget.yview_moveto(0)


def scrollable_text(parent, **options) -> tk.Text:
    frame = ttk.Frame(parent, style="Surface.TFrame")
    frame.pack(fill="both", expand=True)
    text = tk.Text(frame, wrap="word", relief="flat", borderwidth=0, padx=16, pady=14,
                   selectbackground="#237D65", selectforeground="white", **options)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    return text


def modal(parent, title: str, size: str = "520x440", *, grab: bool = True) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry(size)
    dialog.transient(parent)
    dialog.update_idletasks()
    width, height = (int(value) for value in size.split("x"))
    x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
    y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2)
    dialog.geometry(f"{size}+{x}+{y}")
    dialog.minsize(width, height)
    if grab:
        dialog.grab_set()
    return dialog


class ScrollableFrame(ttk.Frame):
    """Keep a form usable on smaller desktop windows."""
    def __init__(self, parent, **options):
        super().__init__(parent, **options)
        background = ttk.Style(self).lookup("Surface.TFrame", "background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(self.canvas, padding=24, style="Surface.TFrame")
        item = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(item, width=event.width))

        def wheel(event):
            if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview)):
                return
            widget = event.widget
            while widget is not None:
                if widget == self:
                    if self.content.winfo_height() > self.canvas.winfo_height():
                        self.canvas.yview_scroll(-1 if event.delta > 0 or event.num == 4 else 1, "units")
                        return "break"
                    return
                widget = getattr(widget, "master", None)

        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.winfo_toplevel().bind(event, wheel, add="+")
