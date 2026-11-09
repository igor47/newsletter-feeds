"""Read newsletter emails out of a maildir and group them into feeds.

The maildir is mounted read-only and only ever grows, so this keeps a cache
keyed by the maildir's unique message name (stable when a message moves from
new/ to cur/ or its flags change). Each file is opened once for its headers;
full parsing and cleaning happens only for the entries a feed actually serves.
"""

import email
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from functools import lru_cache
from html import escape
from pathlib import Path

from .clean import clean_html, clean_url

_LIST_ID = re.compile(r"<([^>]+)>")
_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")


@dataclass(frozen=True)
class Header:
    key: str
    path: Path
    slug: str
    author: str
    subject: str
    date: datetime
    link: str | None
    message_id: str


@dataclass(frozen=True)
class Entry:
    header: Header
    html: str


@dataclass(frozen=True)
class Feed:
    slug: str
    title: str
    entries: list[Header]


def list_slug(list_id: str) -> str | None:
    """`Noahpinion <noahpinion.substack.com>` -> `noahpinion.substack.com`."""
    m = _LIST_ID.search(list_id)
    slug = (m.group(1) if m else list_id).strip().lower()
    return slug if _SLUG_OK.match(slug) else None


def _read_header(key: str, path: Path) -> Header | None:
    with path.open("rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default, _class=EmailMessage)
    slug = list_slug(str(msg.get("List-Id", "")))
    if slug is None:
        return None
    try:
        date = parsedate_to_datetime(str(msg["Date"]))
    except (TypeError, ValueError):
        date = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    name, addr = parseaddr(str(msg.get("From", "")))
    post = _LIST_ID.search(str(msg.get("List-Post", "")))
    link = clean_url(post.group(1)) if post else None
    return Header(
        key=key,
        path=path,
        slug=slug,
        author=name or addr,
        subject=str(msg.get("Subject", "")).strip() or "(no subject)",
        date=date,
        link=link,
        message_id=str(msg.get("Message-ID", "")).strip("<> ") or key,
    )


@lru_cache(maxsize=1024)
def _render(header: Header) -> Entry:
    with header.path.open("rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default, _class=EmailMessage)
    part = msg.get_body(preferencelist=("html", "plain"))
    if part is None:
        return Entry(header, "")
    content = str(part.get_content())
    if part.get_content_type() == "text/plain":
        return Entry(header, f"<pre>{escape(content)}</pre>")
    return Entry(header, clean_html(content))


class Archive:
    def __init__(self, maildir: Path, entries_per_feed: int = 50):
        self.maildir = maildir
        self.entries_per_feed = entries_per_feed
        self._headers: dict[str, Header | None] = {}
        self._lock = threading.Lock()

    def _files(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for sub in ("new", "cur"):
            d = self.maildir / sub
            for name in os.listdir(d):
                if not name.startswith("."):
                    found[name.split(":", 1)[0]] = d / name
        return found

    def scan(self) -> list[Header]:
        """Index any new messages; return headers of every newsletter email."""
        with self._lock:
            files = self._files()
            for key, path in files.items():
                cached = self._headers.get(key, ...)
                if cached is ... or (cached is not None and cached.path != path):
                    try:
                        self._headers[key] = _read_header(key, path)
                    except FileNotFoundError:
                        continue  # moved between listdir and open; next scan gets it
            for gone in self._headers.keys() - files.keys():
                del self._headers[gone]
            return [h for h in self._headers.values() if h is not None]

    def feeds(self) -> dict[str, Feed]:
        by_slug: dict[str, list[Header]] = {}
        for h in self.scan():
            by_slug.setdefault(h.slug, []).append(h)
        feeds: dict[str, Feed] = {}
        for slug, headers in by_slug.items():
            headers.sort(key=lambda h: h.date, reverse=True)
            feeds[slug] = Feed(slug, headers[0].author, headers[: self.entries_per_feed])
        return feeds

    def entries(self, feed: Feed) -> list[Entry]:
        return [_render(h) for h in feed.entries]
