"""Turn a newsletter email's HTML into something safe to put in a feed.

A newsletter email is addressed to one subscriber, and Substack's in particular
is full of things tied to that subscriber: open-tracking pixels, redirect links
that carry a user id, and Like/Comment/Share buttons whose links carry a login
token. A feed is read outside the mail client and may be shared more widely, so
all of that comes out here. What stays is the post itself, with links pointing
at their real destinations wherever that can be worked out offline.
"""

import base64
import binascii
import json
from typing import cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

# query parameters that identify the subscriber or the campaign
_DROP_PARAMS = frozenset({"token", "r", "j", "s", "reemail", "redirect", "inbox"})

# tags that never belong in feed content
_DROP_TAGS = ("head", "title", "meta", "link", "style", "script", "noscript")


def _b64json(segment: str) -> dict[str, object] | None:
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        value = json.loads(raw)
    except (binascii.Error, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _strip_params(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _DROP_PARAMS and not k.startswith("utm_")
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def clean_url(url: str) -> str | None:
    """Return the URL to keep for a link, or None if the link should go.

    - ``substack.com/redirect/2/<payload>.<sig>``: the payload is base64 JSON
      whose ``e`` is the destination, so decode it and use that.
    - ``substack.com/redirect/<uuid>?j=<user>``: opaque; the ``j`` parameter
      only identifies the subscriber and the redirect works without it.
    - ``substack.com/app-link/...`` and anything with ``action=``: the
      Like/Comment/Restack/Share buttons, which log the subscriber in.
    - ``.../action/disable_email``: the per-subscriber unsubscribe link.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host == "substack.com" and parts.path.startswith("/redirect/2/"):
        token = parts.path.removeprefix("/redirect/2/")
        payload = _b64json(token.split(".", 1)[0])
        target = payload.get("e") if payload else None
        return clean_url(target) if isinstance(target, str) else None
    if host == "substack.com" and parts.path.startswith("/app-link/"):
        return None
    if "/action/disable_email" in parts.path:
        return None
    if any(k == "action" for k, _ in parse_qsl(parts.query)):
        return None
    return _strip_params(url)


def _is_tracking_pixel(img: Tag) -> bool:
    src = str(img.get("src") or "")
    host = urlsplit(src).hostname or ""
    if host.startswith("eotrx.") or (host.startswith("email.") and "/o/" in src):
        return True
    return str(img.get("width")) == "1" and str(img.get("height")) == "1"


def clean_html(html: str) -> str:
    """Strip subscriber-specific links, buttons and tracking from email HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for img in soup.find_all("img"):
        if _is_tracking_pixel(img):
            img.decompose()
    for a in soup.find_all("a"):
        href = a.get("href")
        if not isinstance(href, str):
            continue
        kept = clean_url(href)
        if kept is None:
            a.decompose()
        else:
            a["href"] = kept
    for tag in soup.find_all(True):
        for name, value in list(tag.attrs.items()):
            # data-* is Substack editor metadata (e.g. data-attrs holds the
            # Share button's URL, token and all); a feed reader has no use for it
            if name.startswith("data-"):
                del tag[name]
            elif isinstance(value, str) and "token=" in value:
                if name == "src":
                    tag[name] = _strip_params(value)
                else:
                    del tag[name]
    post = _substack_post(soup)
    if post is not None:
        return str(post)
    body = soup.body
    return body.decode_contents() if body else str(soup)


# inside a Substack post: email furniture that a feed reader shows anyway
# (title, author, date) or that only makes sense in a mail client
_SUBSTACK_CHROME = (
    "table.post-meta",  # author, date, Paid/Preview badge, READ IN APP
    ".email-ufi-2-row",  # Like / Comment / Restack row
    "[class*=email-button-outline-wrapper]",
    ".footer",  # copyright, postal address, unsubscribe
)


_TABLE_PARTS = ("thead", "tbody", "tfoot", "tr", "td", "th")
_LAYOUT_ATTRS = ("border", "cellpadding", "cellspacing", "role", "width", "height", "align")


def _is_layout_table(table: Tag) -> bool:
    return (
        table.get("role") == "presentation"
        or table.get("cellpadding") == "0"
        or "image-wrapper" in table.get_attribute_list("class")
    )


def _flatten_layout_tables(root: Tag) -> None:
    """Turn email layout tables into divs.

    Email HTML wraps every image and embed in tables (``cellpadding=0``,
    ``role=presentation``) because mail clients cannot be trusted with CSS.
    Readers style tables as data (Capy Reader draws borders around every
    cell), so these become plain divs. A table without those markers is
    content and stays a table.
    """
    for table in root.find_all("table"):
        if not _is_layout_table(table):
            continue
        for part in table.find_all(_TABLE_PARTS):
            if part.find_parent("table") is table:
                part.name = "div"
                for attr in _LAYOUT_ATTRS:
                    del part[attr]
        table.name = "div"
        for attr in _LAYOUT_ATTRS:
            del table[attr]


def _substack_post(soup: BeautifulSoup) -> Tag | None:
    """The post itself from a Substack email, minus the email chrome.

    A Substack email is a hidden preview line, a "View in browser" bar, then
    two ``div.post``s: one holding the header (title, subtitle,
    ``table.post-meta``), one holding ``div.body.markup`` (and footnotes),
    followed by button rows and the footer. Keep the body's ``div.post``,
    preceded by the subtitle; the reader already shows title and author.
    Returns None for anything that does not look like that.
    """
    body = soup.select_one("div.post div.body.markup")
    post = body.find_parent("div", class_="post") if body else None
    if post is None:
        return None
    for tag in post.select(", ".join(_SUBSTACK_CHROME)):
        tag.decompose()
    _flatten_layout_tables(post)
    subtitle = soup.select_one("div.post-header h3.subtitle")
    if subtitle is not None and subtitle.get_text(strip=True):
        subtitle.extract()
        post.insert(0, subtitle)
    return post
