import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from newsletter_feeds.archive import Archive, list_slug
from newsletter_feeds.server import make_handler

NS = {"a": "http://www.w3.org/2005/Atom"}


def test_list_slug():
    assert list_slug("Noahpinion <noahpinion.substack.com>") == "noahpinion.substack.com"
    assert list_slug("<Foo.Example.ORG>") == "foo.example.org"
    assert list_slug("") is None
    assert list_slug("<../../etc>") is None


def test_feeds_group_by_list_and_sort_newest_first(maildir: Path):
    feeds = Archive(maildir).feeds()
    assert set(feeds) == {"example.substack.com", "other.substack.com", "community-digest"}
    example = feeds["example.substack.com"]
    # the comment reaction (X-Mailgun-Tag: post-comment-reaction) is not a post
    assert [h.subject for h in example.entries] == ["Second post", "First post"]
    assert example.entries[0].link == "https://example.substack.com/p/two"


def test_entries_per_feed_limit(maildir: Path):
    feed = Archive(maildir, entries_per_feed=1).feeds()["example.substack.com"]
    assert [h.subject for h in feed.entries] == ["Second post"]


def test_scan_picks_up_moves_and_new_mail(maildir: Path):
    archive = Archive(maildir)
    assert len(archive.scan()) == 4
    # a message moving new/ -> cur/ (being marked seen) is the same message
    (maildir / "new" / "2.b.host").rename(maildir / "cur" / "2.b.host:2,S")
    assert len(archive.scan()) == 4
    (maildir / "cur" / "1.a.host:2,S").unlink()
    assert len(archive.scan()) == 3


@pytest.fixture
def server(maildir: Path) -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Archive(maildir)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return int(e.code), bytes(e.read())


def test_atom_feed(server: str):
    status, body = get(f"{server}/feeds/example.substack.com.xml")
    assert status == 200
    root = ET.fromstring(body)
    entries = root.findall("a:entry", NS)
    assert [e.findtext("a:title", namespaces=NS) for e in entries] == ["Second post", "First post"]
    content = entries[0].findtext("a:content", namespaces=NS) or ""
    assert "<h1>Hello</h1>" in content and "token=" not in content
    # id matches Substack's public RSS guid (the bare post URL)
    assert entries[0].findtext("a:id", namespaces=NS) == "https://example.substack.com/p/two"
    link = entries[0].find("a:link", NS)
    assert link is not None and link.get("href") == "https://example.substack.com/p/two"


def test_index_opml_health_and_404(server: str):
    assert get(f"{server}/healthz") == (200, b"ok\n")
    status, body = get(f"{server}/")
    assert status == 200 and b"example.substack.com.xml" in body
    # discoverable by feed readers
    assert (
        b'<link rel="alternate" type="application/atom+xml" title="Other" '
        b'href="/feeds/other.substack.com.xml">' in body
    )
    status, body = get(f"{server}/opml")
    assert status == 200 and b"/feeds/other.substack.com.xml" in body
    assert get(f"{server}/feeds/nope.xml")[0] == 404
    assert get(f"{server}/etc/passwd")[0] == 404


def test_filter_assigned_feed_without_list_id(maildir: Path):
    archive = Archive(maildir)
    feed = archive.feeds()["community-digest"]
    assert feed.title == "Community Digest"
    assert [h.subject for h in feed.entries] == ["Community Digest Vol. 10"]
    html = archive.entries(feed)[0].html
    assert "Digest body" in html and "ablink.news.example.org" in html
    assert "<table" not in html and "Manage your email" not in html
