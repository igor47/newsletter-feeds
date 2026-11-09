"""A tiny HTTP server for the feeds. No auth: it is meant to be reachable only
on a private docker network, by the feed reader."""

import logging
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .archive import Archive
from .atom import render_feed, render_opml

log = logging.getLogger("newsletter_feeds")


def make_handler(archive: Archive) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "newsletter-feeds"

        def _base_url(self) -> str:
            return f"http://{self.headers.get('Host', 'localhost')}"

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                archive.scan()
                self._send(200, b"ok\n", "text/plain")
            elif path == "/":
                self._send(200, self._index(), "text/html; charset=utf-8")
            elif path == "/opml":
                feeds = sorted(archive.feeds().values(), key=lambda f: f.title.lower())
                self._send(200, render_opml(feeds, self._base_url()), "text/x-opml")
            elif path.startswith("/feeds/") and path.endswith(".xml"):
                slug = path.removeprefix("/feeds/").removesuffix(".xml")
                feed = archive.feeds().get(slug)
                if feed is None:
                    self._send(404, b"no such feed\n", "text/plain")
                    return
                body = render_feed(feed, archive.entries(feed), self._base_url() + path)
                self._send(200, body, "application/atom+xml; charset=utf-8")
            else:
                self._send(404, b"not found\n", "text/plain")

        def _index(self) -> bytes:
            feeds = sorted(archive.feeds().values(), key=lambda f: f.title.lower())
            # <link rel=alternate> per feed: feed readers' "add subscription"
            # discovery (miniflux included) lists every feed found on the page
            links = "".join(
                f'<link rel="alternate" type="application/atom+xml" '
                f'title="{escape(f.title)}" href="/feeds/{escape(f.slug)}.xml">'
                for f in feeds
            )
            rows = "".join(
                f'<li><a href="/feeds/{escape(f.slug)}.xml">{escape(f.title)}</a> '
                f"({len(f.entries)} entries, latest {f.entries[0].date:%Y-%m-%d})</li>"
                for f in feeds
            )
            return (
                f"<!doctype html><html><head><title>newsletter-feeds</title>{links}</head>"
                f'<body><h1>newsletter-feeds</h1><p><a href="/opml">OPML</a></p>'
                f"<ul>{rows}</ul></body></html>"
            ).encode()

        def log_message(self, format: str, *args: object) -> None:
            log.info("%s %s", self.address_string(), format % args)

    return Handler


def serve(archive: Archive, host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(archive))
    log.info("serving %s on %s:%d", archive.maildir, host, port)
    httpd.serve_forever()
