"""Παράθυρο εφαρμογής (ttkbootstrap)."""

import os
import queue
import subprocess
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap.widgets.dateentry import DateEntry
from ttkbootstrap.widgets.tableview import Tableview

from . import batch, core, settings

TITLE = "ATHEX → MetaStock"
THEME = "flatly"
DATE_FMT = "%d/%m/%Y"
PREVIEW_COLUMNS = [
    {"text": "Σύμβολο", "stretch": True},
    {"text": "Κλείσιμο", "stretch": False},
    {"text": "Όγκος", "stretch": False},
    {"text": "Ανώτερη", "stretch": False},
    {"text": "Κατώτερη", "stretch": False},
    {"text": "Άνοιγμα", "stretch": False},
]
STATUS_COLORS = {
    batch.OK: "#1e7e34",
    batch.EXISTS: "#555555",
    batch.NO_SESSION: "#555555",
    batch.NOT_PUBLISHED: "#a66300",
    batch.UNAVAILABLE: "#a66300",
    batch.ERROR: "#c62828",
}


def _num(value, cast=float):
    try:
        return cast(float(value))
    except (TypeError, ValueError):
        return 0


def _short_days(days, limit=4):
    text = ", ".join(f"{d:%d/%m}" for d in days[:limit])
    return text + (f" … {days[-1]:%d/%m}" if len(days) > limit else "")


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class App:
    def __init__(self):
        self.root = tb.Window(title=TITLE, themename=THEME, size=(940, 720), minsize=(820, 600))
        self.out_dir = settings.output_dir()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.result_days = {}

        self._build()
        self.refresh_summary()
        self.refresh_preview_choices(select_latest=True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- κατασκευή --------------------------------------------------------------

    def _build(self):
        root = self.root
        pad = {"padx": 12, "pady": 6}

        header = tb.Frame(root)
        header.pack(fill="x", padx=12, pady=(12, 0))
        tb.Label(header, text=TITLE, font=("", 16, "bold")).pack(side="left")
        tb.Label(header, text="Τιμές κλεισίματος ΧΑ σε αρχεία MetaStock (UTF-8, ελληνικά σύμβολα)",
                 bootstyle="secondary").pack(side="left", padx=12)

        # Φάκελος
        folder = tb.Labelframe(root, text="Φάκελος αποθήκευσης")
        folder.pack(fill="x", **pad)
        self.folder_var = tb.StringVar(value=str(self.out_dir))
        tb.Entry(folder, textvariable=self.folder_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=8, pady=8)
        tb.Button(folder, text="Αλλαγή…", bootstyle="secondary-outline",
                  command=self.choose_folder).pack(side="left", padx=(0, 6))
        tb.Button(folder, text="Άνοιγμα φακέλου", bootstyle="secondary-outline",
                  command=lambda: open_folder(self.out_dir)).pack(side="left", padx=(0, 8))

        actions = tb.Frame(root)
        actions.pack(fill="x", padx=12)
        actions.columnconfigure(0, weight=1, uniform="a")
        actions.columnconfigure(1, weight=1, uniform="a")

        # Ενημέρωση
        upd = tb.Labelframe(actions, text="Ενημέρωση")
        upd.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)
        self.latest_var = tb.StringVar()
        self.pending_var = tb.StringVar()
        tb.Label(upd, textvariable=self.latest_var).pack(anchor="w", padx=10, pady=(8, 0))
        tb.Label(upd, textvariable=self.pending_var, bootstyle="secondary").pack(anchor="w", padx=10)
        self.update_btn = tb.Button(upd, text="Ενημέρωση", bootstyle="success", width=18,
                                    command=self.on_update)
        self.update_btn.pack(anchor="w", padx=10, pady=10)

        # Συγκεκριμένες ημέρες
        rng = tb.Labelframe(actions, text="Συγκεκριμένες ημέρες")
        rng.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)
        line = tb.Frame(rng)
        line.pack(fill="x", padx=10, pady=(8, 0))
        start = batch.last_weekday(date.today())
        tb.Label(line, text="Από").pack(side="left")
        self.from_entry = DateEntry(line, date_format=DATE_FMT, start_date=start, first_weekday=0,
                                    popup_title="Επιλογή ημερομηνίας", width=11)
        self.from_entry.pack(side="left", padx=(4, 12))
        tb.Label(line, text="Έως").pack(side="left")
        self.to_entry = DateEntry(line, date_format=DATE_FMT, start_date=start, first_weekday=0,
                                  popup_title="Επιλογή ημερομηνίας", width=11)
        self.to_entry.pack(side="left", padx=4)
        line2 = tb.Frame(rng)
        line2.pack(fill="x", padx=10, pady=8)
        self.overwrite_var = tb.BooleanVar(value=False)
        tb.Checkbutton(line2, text="Αντικατάσταση υπαρχόντων", variable=self.overwrite_var).pack(side="left")
        self.range_btn = tb.Button(line2, text="Λήψη", bootstyle="primary", width=10,
                                   command=self.on_range)
        self.range_btn.pack(side="right")
        tb.Label(rng, text="Το ΧΑ κρατά μόνο τις τελευταίες ~3 εβδομάδες.",
                 bootstyle="secondary", font=("", 9)).pack(anchor="w", padx=10, pady=(0, 8))

        # Πρόοδος
        prog = tb.Frame(root)
        prog.pack(fill="x", **pad)
        self.progress = tb.Progressbar(prog, mode="determinate", bootstyle="success")
        self.progress.pack(side="left", fill="x", expand=True)
        self.cancel_btn = tb.Button(prog, text="Διακοπή", bootstyle="danger-outline",
                                    command=self.cancel.set, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.status_var = tb.StringVar(value="Έτοιμο.")
        tb.Label(root, textvariable=self.status_var).pack(anchor="w", padx=12)

        # Αποτελέσματα / Προεπισκόπηση
        self.tabs = tb.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        res = tb.Frame(self.tabs)
        self.tabs.add(res, text="Αποτελέσματα")
        cols = ("date", "status", "rows", "notes")
        self.results = tb.Treeview(res, columns=cols, show="headings", height=8)
        for cid, text, width, stretch in (("date", "Ημερομηνία", 100, False),
                                          ("status", "Κατάσταση", 240, False),
                                          ("rows", "Μετοχές", 80, False),
                                          ("notes", "Σημειώσεις", 400, True)):
            self.results.heading(cid, text=text, anchor="w")
            self.results.column(cid, width=width, stretch=stretch, anchor="e" if cid == "rows" else "w")
        for status, color in STATUS_COLORS.items():
            self.results.tag_configure(status, foreground=color)
        sb = tb.Scrollbar(res, orient="vertical", command=self.results.yview)
        self.results.configure(yscrollcommand=sb.set)
        self.results.pack(side="left", fill="both", expand=True, pady=6)
        sb.pack(side="left", fill="y", pady=6)
        self.results.bind("<Double-1>", self.on_result_open)
        self.results.bind("<Return>", self.on_result_open)

        prev = tb.Frame(self.tabs)
        self.tabs.add(prev, text="Προεπισκόπηση")
        top = tb.Frame(prev)
        top.pack(fill="x", pady=6)
        tb.Label(top, text="Ημέρα:").pack(side="left")
        self.preview_var = tb.StringVar()
        self.preview_combo = tb.Combobox(top, textvariable=self.preview_var, state="readonly", width=14)
        self.preview_combo.pack(side="left", padx=6)
        self.preview_combo.bind("<<ComboboxSelected>>", lambda e: self.load_preview())
        self.preview_info = tb.StringVar()
        tb.Label(top, textvariable=self.preview_info, bootstyle="secondary").pack(side="left", padx=8)
        self.table = Tableview(prev, coldata=PREVIEW_COLUMNS, rowdata=[], searchable=True,
                               yscrollbar=True, autofit=True, height=14, bootstyle="primary")
        self.table.pack(fill="both", expand=True)

    # --- σύνοψη / προεπισκόπηση ----------------------------------------------------

    def refresh_summary(self):
        files = batch.existing_files(self.out_dir)
        if files:
            self.latest_var.set(f"Τελευταίο αρχείο: {max(files):%d/%m/%Y}  ({len(files)} αρχεία)")
        else:
            self.latest_var.set("Δεν υπάρχουν αρχεία ακόμα στον φάκελο.")
        pending = batch.pending_days(self.out_dir, date.today())
        if pending:
            self.pending_var.set(f"Προς λήψη: {len(pending)} ημέρες ({_short_days(pending)})")
        else:
            self.pending_var.set("Όλα ενημερωμένα.")

    def refresh_preview_choices(self, select_latest=False, select=None):
        days = sorted(batch.existing_files(self.out_dir), reverse=True)
        self._preview_days = {f"{d:%d/%m/%Y}": d for d in days}
        self.preview_combo.configure(values=list(self._preview_days))
        target = select if select in days else (days[0] if days and select_latest else None)
        if target:
            self.preview_var.set(f"{target:%d/%m/%Y}")
            self.load_preview()
        elif not days:
            self.preview_var.set("")
            self.preview_info.set("Δεν υπάρχουν αρχεία.")
            self.table.build_table_data(PREVIEW_COLUMNS, [])

    def load_preview(self):
        day = self._preview_days.get(self.preview_var.get())
        if day is None:
            return
        path = self.out_dir / core.output_name(day)
        try:
            df = core.read_txt(path)
        except Exception as e:
            self.preview_info.set(f"Σφάλμα ανάγνωσης: {e}")
            return
        rows = [
            (r["<TICKER>"], _num(r["<CLOSE>"]), _num(r["<VOL>"], int),
             _num(r["<HIGH>"]), _num(r["<LOW>"]), _num(r["<OPEN>"]))
            for _, r in df.iterrows()
        ]
        self.table.build_table_data(PREVIEW_COLUMNS, rows)
        self.table.autofit_columns()
        self.preview_info.set(f"{len(rows)} μετοχές · {path.name}")

    # --- ενέργειες -------------------------------------------------------------------

    def choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=str(self.out_dir), title="Φάκελος αποθήκευσης")
        if chosen:
            self.out_dir = Path(chosen)
            settings.set_output_dir(self.out_dir)
            self.folder_var.set(str(self.out_dir))
            self.refresh_summary()
            self.refresh_preview_choices(select_latest=True)

    def on_update(self):
        days = batch.pending_days(self.out_dir, date.today())
        if not days:
            self.status_var.set("Όλα ενημερωμένα — δεν λείπει καμία ημέρα.")
            return
        self.start(days, overwrite=False)

    def on_range(self):
        start, end = self.from_entry.get_date(), self.to_entry.get_date()
        if start is None or end is None:
            messagebox.showerror(TITLE, "Μη έγκυρη ημερομηνία. Μορφή: ΗΗ/ΜΜ/ΕΕΕΕ.", parent=self.root)
            return
        start, end = start.date(), end.date()
        if start > end:
            messagebox.showerror(TITLE, "Η ημερομηνία «Από» είναι μετά την «Έως».", parent=self.root)
            return
        days = batch.weekdays(start, end)
        if not days:
            self.status_var.set("Το εύρος περιέχει μόνο Σαββατοκύριακο.")
            return
        self.start(days, overwrite=self.overwrite_var.get())

    def on_result_open(self, _event=None):
        sel = self.results.selection()
        day = self.result_days.get(sel[0]) if sel else None
        if day and day in batch.existing_files(self.out_dir):
            self.refresh_preview_choices(select=day)
            self.tabs.select(1)

    # --- εργασία στο παρασκήνιο ------------------------------------------------------

    def start(self, days, overwrite):
        if self.worker and self.worker.is_alive():
            return
        self.cancel.clear()
        self.results.delete(*self.results.get_children())
        self.result_days.clear()
        self.tabs.select(0)
        self.progress.configure(maximum=len(days), value=0)
        self.status_var.set(f"Λήψη {len(days)} ημερών…")
        self._set_busy(True)
        out_dir, today = self.out_dir, date.today()

        def work():
            try:
                results = batch.run_days(days, out_dir, today=today, overwrite=overwrite,
                                         cancel=self.cancel,
                                         progress=lambda i, n, r: self.events.put(("day", i, n, r)))
                self.events.put(("done", results))
            except Exception as e:                       # δεν πρέπει να «παγώσει» το παράθυρο
                self.events.put(("fail", e))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.root.after(100, self._poll)

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "day":
                    _, i, n, r = event
                    self._add_result(r)
                    self.progress.configure(value=i)
                    self.status_var.set(f"{i}/{n} · {r.day:%d/%m/%Y}: {r.label}")
                elif kind == "done":
                    self._finish(event[1])
                    return
                elif kind == "fail":
                    self._set_busy(False)
                    self.status_var.set(f"Σφάλμα: {event[1]}")
                    messagebox.showerror(TITLE, str(event[1]), parent=self.root)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _add_result(self, r: batch.DayResult):
        iid = self.results.insert("", "end", tags=(r.status,), values=(
            f"{r.day:%d/%m/%Y}", r.label, r.rows or "", " · ".join(r.notes)))
        self.result_days[iid] = r.day
        self.results.see(iid)

    def _finish(self, results):
        self._set_busy(False)
        counts = {}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        parts = [f"{batch.STATUS_LABELS[s].lstrip('✓ ')}: {n}" for s, n in counts.items()]
        prefix = "Διακόπηκε. " if self.cancel.is_set() else "Ολοκληρώθηκε. "
        self.status_var.set(prefix + " · ".join(parts) + f"  ({datetime.now():%H:%M})")
        self.refresh_summary()
        saved = [r.day for r in results if r.status == batch.OK]
        self.refresh_preview_choices(select=max(saved) if saved else None,
                                     select_latest=not saved)
        if counts.get(batch.ERROR):
            errors = "\n".join(f"{r.day:%d/%m/%Y}: {' '.join(r.notes)}"
                               for r in results if r.status == batch.ERROR)
            messagebox.showwarning(TITLE, f"Κάποιες ημέρες απέτυχαν:\n\n{errors}", parent=self.root)

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for btn in (self.update_btn, self.range_btn):
            btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def on_close(self):
        self.cancel.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    App().run()
