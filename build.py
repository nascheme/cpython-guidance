#!/usr/bin/env -S uv run --locked
"""Build the static site and publish unchanged Markdown beside each HTML page."""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path


def main():
    os.chdir(Path(__file__).resolve().parent)
    subprocess.run(
        ["uv", "run", "--locked", "zensical", "build", "--clean"], check=True
    )

    with Path("zensical.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    docs = Path(project.get("docs_dir", "docs"))
    site = Path(project.get("site_dir", "site"))
    directory_urls = project.get("use_directory_urls", True)
    pages = []

    for source in sorted(docs.rglob("*.md")):
        relative = source.relative_to(docs)
        if relative.name == "index.md" or not directory_urls:
            page = site / relative.with_suffix(".html")
        else:
            page = site / relative.with_suffix("") / "index.html"

        if not page.is_file():
            raise SystemExit(f"Missing HTML page for {source}: {page}")
        html = page.read_text(encoding="utf-8")
        if html.count("</article>") != 1:
            raise SystemExit(f"Expected one article in {page}; check the theme markup")

        # Flat HTML pages need distinct source filenames because they share a folder.
        name = "source.md" if directory_urls else f"{relative.stem}.source.md"
        destination = page.parent / name
        link = f'<p class="markdown-source"><a href="{name}">Markdown source</a></p>\n'
        pages.append(
            (source, page, destination, html.replace("</article>", link + "</article>"))
        )

    if not pages:
        raise SystemExit(f"No Markdown pages found in {docs}")

    # Validate every target before modifying any generated page.
    for source, page, destination, html in pages:
        shutil.copyfile(source, destination)
        page.write_text(html, encoding="utf-8")

    print(f"Published Markdown sources and links for {len(pages)} pages.")


if __name__ == "__main__":
    main()
