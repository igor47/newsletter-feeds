import argparse
import logging
import os
from pathlib import Path

from .archive import Archive
from .server import serve


def main() -> None:
    p = argparse.ArgumentParser(prog="newsletter-feeds")
    p.add_argument("--maildir", default=os.environ.get("NEWSLETTER_MAILDIR", "/mail"))
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--entries", type=int, default=int(os.environ.get("ENTRIES_PER_FEED", "50")))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    serve(Archive(Path(args.maildir), args.entries), args.host, args.port)


if __name__ == "__main__":
    main()
