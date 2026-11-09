"""Render feeds as Atom, and the feed list as OPML."""

from datetime import UTC, datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from .archive import Entry, Feed

ATOM = "http://www.w3.org/2005/Atom"


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def render_feed(feed: Feed, entries: list[Entry], self_url: str) -> bytes:
    root = Element("feed", xmlns=ATOM)
    SubElement(root, "id").text = f"urn:newsletter-feeds:{feed.slug}"
    SubElement(root, "title").text = feed.title
    SubElement(root, "link", rel="self", href=self_url)
    newest = entries[0].header.date if entries else datetime.fromtimestamp(0, UTC)
    SubElement(root, "updated").text = _ts(newest)
    for entry in entries:
        h = entry.header
        e = SubElement(root, "entry")
        # the post URL when there is one: Substack's public RSS uses exactly
        # that as each item's guid, so a reader that switches a subscription
        # from the public feed to this one matches entries it already has
        # (keeping read/starred state, upgrading paywalled previews in place)
        SubElement(e, "id").text = h.link or f"urn:message-id:{h.message_id}"
        SubElement(e, "title").text = h.subject
        if h.link:
            SubElement(e, "link", rel="alternate", href=h.link)
        SubElement(e, "published").text = _ts(h.date)
        SubElement(e, "updated").text = _ts(h.date)
        SubElement(SubElement(e, "author"), "name").text = h.author
        SubElement(e, "content", type="html").text = entry.html
    return tostring(root, encoding="utf-8", xml_declaration=True)


def render_opml(feeds: list[Feed], base_url: str) -> bytes:
    root = Element("opml", version="2.0")
    SubElement(SubElement(root, "head"), "title").text = "newsletter-feeds"
    body = SubElement(root, "body")
    for feed in feeds:
        SubElement(
            body,
            "outline",
            type="rss",
            text=feed.title,
            title=feed.title,
            xmlUrl=f"{base_url}/feeds/{feed.slug}.xml",
        )
    return tostring(root, encoding="utf-8", xml_declaration=True)
