"""The review server: book.md, the scans, and the edit log, on localhost.

  GET  /                  the page
  GET  /api/book          the sections
  GET  /api/section/<k>   one section's blocks, each with its boxes on the scans
  GET  /scan/<n>          page n as PNG (rendered on first request if missing)
  POST /api/edit          {version, index, text}: replace block `index`; blank
                          lines in `text` split it, empty `text` deletes it
  POST /api/merge         {version, index}: join block `index` and the next

Every POST carries the version (a hash of book.md) it was made against; if
book.md changed since (a save from another tab, a new `assemble`), it is
refused and the page reloads.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..common import Book
from . import mdbook, notes

PAGE = Path(__file__).with_name("page.html")
LOG = "corrections.jsonl"


class Conflict(Exception):
    pass


class Review:
    def __init__(self, book: Book):
        self.book = book
        self.path = book.dir / "book.md"
        self.raw_path = book.dir / "book.raw.md"
        if not self.path.exists():
            raise SystemExit(f"{self.path} doesn't exist: run `python -m vsc_ocr assemble {book.id}` first.")
        self.scans = mdbook.Scans(book)
        self.lock = threading.Lock()
        self.render_lock = threading.Lock()
        self._text = None
        self._load()

    def _load(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        if text != self._text:
            self._text = text
            self.blocks = mdbook.split(text)
            self.secs = mdbook.sections(self.blocks)
            self.version = hashlib.sha1(text.encode()).hexdigest()[:12]

    # -- reads
    def overview(self) -> dict:
        with self.lock:
            self._load()
            title = next((s["title"] for s in self.secs if s["level"] == 1), self.book.id)
            secs = [{k: s[k] for k in ("title", "level", "start", "pdf", "flags")} for s in self.secs]
            return dict(book=self.book.id, title=title, version=self.version, sections=secs)

    def section(self, k: int) -> dict:
        with self.lock:
            self._load()
            k = max(0, min(k, len(self.secs) - 1))
            s = self.secs[k]
            blocks = self.blocks[s["start"]:s["end"]]
            boxes = self.scans.locate(blocks, s["pdf"])
            return dict(version=self.version, index=k, pdf=s["pdf"],
                        blocks=[dict(i=s["start"] + j, text=b, kind=mdbook.kind(b), boxes=bx)
                                for j, (b, bx) in enumerate(zip(blocks, boxes))])

    def scan(self, n: int) -> Path:
        path = self.book.render_path(n)
        if not path.exists():
            with self.render_lock:
                from ..render import render_pages
                render_pages(self.book, [n])
        return path

    # -- writes
    def edit(self, version: str, index: int, text: str) -> dict:
        new = mdbook.split(text.replace("\r\n", "\n").strip("\n")) if text.strip() else []
        new = [b.strip("\n") for b in new if b.strip()]
        return self._change(version, index, 1, new, "edit" if new else "delete")

    def merge(self, version: str, index: int) -> dict:
        with self.lock:
            self._load()
            if index + 1 >= len(self.blocks):
                raise ValueError("no block after this one")
            a, b = self.blocks[index], self.blocks[index + 1]
        return self._change(version, index, 2, [_joined(a, b)], "merge")

    def _change(self, version: str, index: int, count: int, new: list[str], action: str) -> dict:
        with self.lock:
            self._load()
            if version != self.version:
                raise Conflict("book.md changed since this page loaded")
            old = self.blocks[index:index + count]
            if old == new:
                return dict(version=self.version, section=mdbook.section_of(self.secs, index))
            if not self.raw_path.exists():
                self.raw_path.write_text(self._text, encoding="utf-8")
            sec = self.secs[mdbook.section_of(self.secs, index)]
            pages = sorted({b["page"] for bx in self.scans.locate(old, sec["pdf"]) for b in bx})
            blocks = self.blocks[:index] + new + self.blocks[index + count:]
            text = mdbook.join(blocks)
            tmp = self.path.with_suffix(".md.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self.path)
            with open(self.book.dir / LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(time=datetime.now().isoformat(timespec="seconds"), action=action,
                                        section=sec["title"], pdf_pages=pages, before=old, after=new),
                                   ensure_ascii=False) + "\n")
            self._load()
            notes.sync(self.book.dir / "notes.json",
                       mdbook.split(self.raw_path.read_text(encoding="utf-8")), self.blocks)
            return dict(version=self.version, section=mdbook.section_of(self.secs, min(index, len(self.blocks) - 1)))


_flag_end = re.compile(r"\s*⚠$")


def _joined(a: str, b: str) -> str:
    """Two blocks as one paragraph, as assemble joins a paragraph split by a page."""
    flagged = a.endswith("⚠") or b.endswith("⚠")
    a, b = _flag_end.sub("", a), _flag_end.sub("", b)
    b = b[1:] if b.startswith("\\") else b
    if a.endswith("-") and len(a) > 1 and a[-2].isalpha() and b[:1].islower():
        out = a + b
    else:
        out = a + " " + b
    return out + (" ⚠" if flagged else "")


def _handler(review: Review):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if "json" in ctype or "html" in ctype else "max-age=3600")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=HTTPStatus.OK):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path == "/":
                    self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/book":
                    self._json(review.overview())
                elif m := re.fullmatch(r"/api/section/(\d+)", path):
                    self._json(review.section(int(m.group(1))))
                elif m := re.fullmatch(r"/scan/(\d+)", path):
                    self._send(HTTPStatus.OK, review.scan(int(m.group(1))).read_bytes(), "image/png")
                else:
                    self._json(dict(error="not found"), HTTPStatus.NOT_FOUND)
            except Exception as e:      # a missing page, a bad PDF: show it, keep serving
                self._json(dict(error=str(e)), HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/api/edit":
                    self._json(review.edit(body["version"], int(body["index"]), body["text"]))
                elif self.path == "/api/merge":
                    self._json(review.merge(body["version"], int(body["index"])))
                else:
                    self._json(dict(error="not found"), HTTPStatus.NOT_FOUND)
            except Conflict as e:
                self._json(dict(error=str(e)), HTTPStatus.CONFLICT)
            except Exception as e:
                self._json(dict(error=str(e)), HTTPStatus.BAD_REQUEST)

    return Handler


def serve(book: Book, port: int = 8765, open_browser: bool = True) -> None:
    review = Review(book)
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(review))
    url = f"http://127.0.0.1:{port}/"
    print(f"  reviewing {review.path}\n  open {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
