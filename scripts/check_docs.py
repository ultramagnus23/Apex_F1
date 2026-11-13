"""Fail if any Markdown link in the README, CONTRIBUTING or docs points at a missing file or anchor,
or if an ``mkdocs.yml`` nav entry points at a missing page.

    uv run python scripts/check_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)


def slug(heading: str) -> str:
    """GitHub-style anchor: lower case, drop punctuation, spaces to hyphens."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return {slug(h) for h in HEADING.findall(text)}


def main() -> int:
    errors: list[str] = []
    files = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for f in files:
        text = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.DOTALL)
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, frag = target.partition("#")
            dest = (f.parent / path_part).resolve() if path_part else f
            if not dest.exists():
                errors.append(f"{f.relative_to(ROOT)}: missing file {target}")
            elif frag and dest.suffix == ".md" and frag not in anchors(dest):
                errors.append(f"{f.relative_to(ROOT)}: missing anchor {target}")
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for page in re.findall(r":\s+([\w./-]+\.(?:md|html))\s*$", nav, flags=re.MULTILINE):
        if not (ROOT / "docs" / page).exists():
            errors.append(f"mkdocs.yml: missing page {page}")
    for e in errors:
        print(e)
    print(f"checked {len(files)} files, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
