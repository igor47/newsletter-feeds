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

# the shape of a real Substack email: hidden preview, "View in browser" bar,
# a header div.post (title, subtitle, post-meta), a body div.post, button
# rows and a footer
POST_HTML = f"""<html><head><style>p {{ color: red }}</style><title>x</title></head><body>
<div class="preview">Preview line ͏ ­͏ ­</div>
<table class="email-body-container"><tr><td class="content">
<table><tr><td><a href="https://example.substack.com/p/hello">View in browser</a></td></tr></table>
<div class="post typography"><div class="post-header">
<h1 class="post-title published"></h1>
<h3 class="subtitle">A subtitle worth keeping</h3>
<table class="post-meta"><tr><td><a href="https://substack.com/@example">Example Author</a></td>
<td><time>Nov 2</time></td><td>Paid</td>
<td><a href="https://open.substack.com/pub/example/p/hello?utm_source=email&amp;redirect=app-store">READ IN APP</a></td></tr></table>
</div></div>
<div class="post typography"><div class="body markup">
<h1>Hello</h1>
<p>Body with <a href="https://substack.com/redirect/0b1c2d3e-aaaa-bbbb-cccc-000000000001?j={b64({"u": REF})}.sig">an article</a>
and <a href="https://example.org/plain">a plain link</a>.</p>
<p class="button-wrapper" data-attrs='{{"url":"https://substack.com/app-link/post?action=share&amp;r={REF}&amp;token={LOGIN_TOKEN}"}}'>
<a href="https://substack.com/app-link/post?publication_id=1&amp;post_id=42&amp;r={REF}&amp;token={LOGIN_TOKEN}">Like</a>
<a href="https://open.substack.com/pub/example/p/hello?r={REF}&amp;action=comments&amp;token={LOGIN_TOKEN}">Comment</a></p>
<p><a href="{REDIRECT2}">Read in browser</a></p>
<figure><table border="0" cellpadding="0" cellspacing="0" class="image-wrapper" width="100%"><tr><td>
<img src="https://substackcdn.com/image/fetch/w_1456/photo.jpg" width="600" height="400">
</td></tr></table></figure>
<table class="twitter-embed tweet" role="presentation" cellpadding="0" cellspacing="0"><tr><td>
<table role="presentation"><tr><td>@someone</td><td>a tweet</td></tr></table></td></tr></table>
<table><tr><th>Year</th><th>GDP</th></tr><tr><td>2026</td><td>1.2</td></tr></table>
<img src="https://eotrx.substackcdn.com/o/abc/p.gif?token={LOGIN_TOKEN}">
<img width="1" height="1" alt="" src="https://email.mg1.substack.com/o/eJxTRACK">
</div><div class="footnote"><p>1. A footnote.</p></div></div>
<table class="email-ufi-2-row"><tr><td>Like</td><td>Comment</td><td>Restack</td></tr></table>
<table class="footer"><tr><td>© 2026 Example Author, 548 Market Street
<a href="https://example.substack.com/action/disable_email/disable?token={LOGIN_TOKEN}">Unsubscribe</a></td></tr></table>
</td></tr></table>
</body></html>"""


def make_message(
    list_id: str,
    subject: str,
    date: str,
    name: str = "Example",
    slug: str = "hello",
    tag: str = "post",
) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"{name} <example@substack.com>"
    msg["To"] = "someone@example.org"
    msg["Subject"] = subject
    msg["Date"] = date
    msg["Message-ID"] = f"<{subject.replace(' ', '-')}@mg1.substack.com>"
    msg["List-Id"] = f"<{list_id}>"
    msg["List-Post"] = f"<https://example.substack.com/p/{slug}>"
    msg["X-Mailgun-Tag"] = tag
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
    # a comment reaction: same List-Id and List-Post as the post it is about
    (tmp_path / "new" / "5.e.host").write_bytes(
        make_message(
            "example.substack.com",
            "Someone liked your comment",
            "Thu, 5 Nov 2026 10:00:00 +0000",
            slug="two",
            tag="post-comment-reaction",
        )
    )
    no_list = EmailMessage()
    no_list["Subject"] = "not a newsletter"
    no_list.set_content("hi")
    (tmp_path / "new" / "4.d.host").write_bytes(bytes(no_list))
    return tmp_path
