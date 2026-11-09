"""Synthetic Substack-shaped emails. Real ones carry the subscriber's tokens and
must never be committed, so these reproduce the structure with fake values."""

import base64
import json
from email.message import EmailMessage
from pathlib import Path

import pytest

USER_ID = 999001
REF = "zzref"


def b64(obj: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


LOGIN_TOKEN = b64({"user_id": USER_ID, "post_id": 42}) + ".sig"
REDIRECT2 = (
    "https://substack.com/redirect/2/"
    + b64(
        {
            "e": f"https://example.substack.com/p/hello?utm_campaign=email-post&r={REF}"
            f"&token={LOGIN_TOKEN}",
            "u": USER_ID,
        }
    )
    + ".sig"
)

POST_HTML = f"""<html><head><style>p {{ color: red }}</style><title>x</title></head><body>
<h1>Hello</h1>
<p>Body with <a href="https://substack.com/redirect/0b1c2d3e-aaaa-bbbb-cccc-000000000001?j={b64({"u": REF})}.sig">an article</a>
and <a href="https://example.org/plain">a plain link</a>.</p>
<p class="button-wrapper" data-attrs='{{"url":"https://substack.com/app-link/post?action=share&amp;r={REF}&amp;token={LOGIN_TOKEN}"}}'>
<a href="https://substack.com/app-link/post?publication_id=1&amp;post_id=42&amp;r={REF}&amp;token={LOGIN_TOKEN}">Like</a>
<a href="https://open.substack.com/pub/example/p/hello?r={REF}&amp;action=comments&amp;token={LOGIN_TOKEN}">Comment</a></p>
<p><a href="{REDIRECT2}">Read in browser</a></p>
<img src="https://substackcdn.com/image/fetch/w_1456/photo.jpg" width="600" height="400">
<img src="https://eotrx.substackcdn.com/o/abc/p.gif?token={LOGIN_TOKEN}">
<img width="1" height="1" alt="" src="https://email.mg1.substack.com/o/eJxTRACK">
<a href="https://example.substack.com/action/disable_email/disable?token={LOGIN_TOKEN}">Unsubscribe</a>
</body></html>"""


def make_message(
    list_id: str, subject: str, date: str, name: str = "Example", slug: str = "hello"
) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"{name} <example@substack.com>"
    msg["To"] = "someone@example.org"
    msg["Subject"] = subject
    msg["Date"] = date
    msg["Message-ID"] = f"<{subject.replace(' ', '-')}@mg1.substack.com>"
    msg["List-Id"] = f"<{list_id}>"
    msg["List-Post"] = f"<https://example.substack.com/p/{slug}>"
    msg.set_content("plain text version")
    msg.add_alternative(POST_HTML, subtype="html")
    return bytes(msg)


@pytest.fixture
def maildir(tmp_path: Path) -> Path:
    for sub in ("new", "cur", "tmp"):
        (tmp_path / sub).mkdir()
    (tmp_path / "cur" / "1.a.host:2,S").write_bytes(
        make_message("example.substack.com", "First post", "Mon, 2 Nov 2026 10:00:00 +0000")
    )
    (tmp_path / "new" / "2.b.host").write_bytes(
        make_message(
            "example.substack.com", "Second post", "Tue, 3 Nov 2026 10:00:00 +0000", slug="two"
        )
    )
    (tmp_path / "new" / "3.c.host").write_bytes(
        make_message("other.substack.com", "Other", "Wed, 4 Nov 2026 10:00:00 +0000", "Other")
    )
    no_list = EmailMessage()
    no_list["Subject"] = "not a newsletter"
    no_list.set_content("hi")
    (tmp_path / "new" / "4.d.host").write_bytes(bytes(no_list))
    return tmp_path
