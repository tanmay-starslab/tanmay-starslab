"""Replace the generated blocks in README.md, leaving everything else untouched."""

from __future__ import annotations

import re

from svgkit import ROOT

README = ROOT / "README.md"


def replace_block(text: str, name: str, content: str) -> str:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise KeyError(f"README is missing the {name} markers")
    return pattern.sub(lambda _: f"{start}\n{content.strip()}\n{end}", text, count=1)


def update(blocks: dict[str, str]) -> bool:
    text = README.read_text(encoding="utf-8")
    new = text
    for name, content in blocks.items():
        new = replace_block(new, name, content)
    if new != text:
        README.write_text(new, encoding="utf-8")
        return True
    return False
