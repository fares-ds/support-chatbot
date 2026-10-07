# /// script
# requires-python = ">=3.12"
# dependencies = ["trafilatura==2.0.0"]
# ///
"""Fetches a dataset's web pages into its kb/, with trafilatura, as KB-8's web import will.

From the bench directory: `uv run data/fetch.py data/gov-uk`. It fetches every document in
sources.toml whose origin is a URL, overwrites kb/, and sets sources.toml's `retrieved` to
today. Pages change, so review the diff before committing it: questions and their sources may
need to follow.
"""

import re
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

import trafilatura


def main(directory: Path) -> None:
    sources = directory / "sources.toml"
    raw = tomllib.loads(sources.read_text(encoding="utf-8"))
    for entry in raw.get("documents", []):
        if not entry["origin"].startswith("https://"):
            continue
        html = trafilatura.fetch_url(entry["origin"])
        if html is None:
            sys.exit(f"{entry['origin']}: could not fetch it")
        markdown = trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_formatting=True,
            include_links=False,
        )
        if not markdown:
            sys.exit(f"{entry['origin']}: no readable content (KB-9)")
        if not markdown.startswith("# "):
            metadata = trafilatura.extract_metadata(html)
            markdown = f"# {metadata.title}\n\n{markdown}"
        (directory / "kb" / entry["file"]).write_text(markdown.strip() + "\n", encoding="utf-8")
        print(f"{entry['file']}: {len(markdown):,} characters")
        time.sleep(1)  # one request a second, to be polite
    text = re.sub(
        r"^retrieved = .*$",
        f"retrieved = {date.today().isoformat()}",
        sources.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    sources.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
