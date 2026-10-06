# CPython contributor guidance

Source for <https://python.ca/cpython-guidance/>, built with
[Zensical](https://zensical.org/) and served as static files by nginx.

## Layout

- `docs/`: Markdown source, with a subfolder for each topic.
- `zensical.toml`: site configuration and navigation.
- `build.py`: builds the site and adds downloadable Markdown sources.
- `site/`: generated HTML and assets (ignored by Git).
- `uv.lock`: pinned build dependencies; commit this with the source.

## Install and preview

Install [uv](https://docs.astral.sh/uv/), then run:

```sh
uv sync --locked
uv run zensical serve
```

Open the local URL printed by Zensical. The preview server is only for development.

## Build

```sh
uv run --locked build.py
```

The output includes `site/index.html`, `site/free-threading/index.html`, and
`site/guidance-process/index.html`. Each page links to an unchanged copy of its
Markdown source, published beside it as `source.md`. The script adds these files
and links after Zensical's clean build; running Zensical directly does not add
them, including during preview.

No Python process or application server is needed to serve it.

## Deploy with nginx

Copy the **contents** of `site/` into the `cpython-guidance/` subdirectory of
sites's document root. For example, if the document root is
`/var/www/python.ca`:

```sh
rsync -av --delete site/ /var/www/python.ca/cpython-guidance/
```

`--delete` removes obsolete files inside that destination. Check the destination
path before running it; do not deploy to the domain's document root directly.

Inside the existing python.ca `server` block, use its document root and add:

```nginx
# Assumes the server already has: root /var/www/python.ca;
location = /cpython-guidance {
    return 301 /cpython-guidance/;
}

location /cpython-guidance/ {
    index index.html;
    try_files $uri $uri/ =404;
}
```

Test the nginx configuration with `nginx -t` before reloading it. Adapt paths to
the host's existing configuration. Do not use a single-page-app fallback: each
page has its own generated HTML file.

If the public URL changes, update `site_url` in `zensical.toml` and rebuild.

## Add a topic

Create `docs/<topic>/index.md`, add it to `nav` in `zensical.toml`, and link it
from `docs/index.md`. It will be published at `/cpython-guidance/<topic>/`.
