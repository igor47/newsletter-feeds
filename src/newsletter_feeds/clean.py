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
    body = soup.body
    return body.decode_contents() if body else str(soup)
