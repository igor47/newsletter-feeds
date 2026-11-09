# newsletter-feeds

Serves full-text Atom feeds built from newsletter emails in a maildir: one feed
per mailing list (`List-Id`), with each email's HTML as the entry content.

It exists because Substack's public `/feed` truncates paid posts and Substack
offers no private full-text RSS for paid text newsletters. The email has the
whole post.

## How it fits together

1. The mail filter delivers newsletter mail to a dedicated maildir instead of
   the inbox. With maildrop (`~/.mailfilter`):

   ```
   if (/^List-Id: <[a-z0-9-]+\.substack\.com>/)
       to "$HOME/newsletters/"
   ```

   Create the maildir first: `maildirmake ~/newsletters`.
2. This service mounts only that maildir, read-only, and serves:
   - `/feeds/<list-id>.xml`: Atom, newest 50 entries (`ENTRIES_PER_FEED`)
   - `/`: an HTML list of feeds; `/opml`: the same as OPML
   - `/healthz`
3. The feed reader subscribes over a private docker network. There is no
   auth, so do not publish the port or route it through a reverse proxy.

## What gets cleaned out

Newsletter emails are addressed to one subscriber. Before anything reaches a
feed (`src/newsletter_feeds/clean.py`):

- open-tracking pixels are removed;
- Substack `redirect/2/<payload>` links are decoded to their real destination,
  offline;
- Substack `redirect/<uuid>?j=<user>` links lose the `j` parameter, so a click
  is anonymous (the redirect still works);
- Like/Comment/Restack/Share buttons (`app-link`, `?action=`), which carry a
  login token, are removed, along with the unsubscribe link;
- `token`, `r`, `utm_*` and similar parameters are stripped from every link
  and image URL.

## Running

```sh
mise run install
mise run test
mise run dev -- ~/newsletters     # http://127.0.0.1:8000/
```

Docker: the image runs as uid 1000. Mount the maildir at `/mail:ro`; the uid
must be able to read it.

## Caveats

- Only emails received after the filter rule exists show up. There is no back
  catalog.
- The maildir only grows. Nothing here deletes mail; prune it by hand if it
  ever matters.
- The newsletter must be set to email delivery, not app-only.
