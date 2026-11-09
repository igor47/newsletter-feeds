from conftest import LOGIN_TOKEN, POST_HTML, REDIRECT2, REF, USER_ID
from newsletter_feeds.clean import clean_html, clean_url


def test_redirect2_decodes_to_destination_without_tracking():
    assert clean_url(REDIRECT2) == "https://example.substack.com/p/hello"


def test_opaque_redirect_loses_user_param():
    url = "https://substack.com/redirect/abc-def?j=eyJ1IjoieiJ9.sig"
    assert clean_url(url) == "https://substack.com/redirect/abc-def"


def test_action_and_app_links_are_dropped():
    assert clean_url("https://substack.com/app-link/post?post_id=1&token=x") is None
    assert clean_url("https://open.substack.com/pub/x/p/y?action=share") is None
    assert clean_url("https://x.substack.com/action/disable_email/disable?token=t") is None


def test_ordinary_links_keep_their_query():
    assert clean_url("https://example.org/a?id=3&utm_source=x") == "https://example.org/a?id=3"


def test_clean_html_leaves_no_subscriber_identifiers():
    out = clean_html(POST_HTML)
    for leak in (LOGIN_TOKEN, REF, str(USER_ID), "eotrx", "email.mg1", "data-attrs", "token="):
        assert leak not in out, leak
    assert "<style" not in out and "<title" not in out


def test_clean_html_keeps_the_post():
    out = clean_html(POST_HTML)
    assert "<h1>Hello</h1>" in out
    assert "https://example.org/plain" in out
    assert "https://substackcdn.com/image/fetch/w_1456/photo.jpg" in out
    assert ">an article</a>" in out
    assert "Like</a>" not in out and "Unsubscribe" not in out
