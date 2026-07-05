#!/usr/bin/env python3
import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

VAULT_ROOT = Path(__file__).resolve().parents[1]
BOOKS_DIR = VAULT_ROOT / "Reading" / "Books"
COVERS_DIR = BOOKS_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)


def clean_value(value: Optional[str]) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}
    frontmatter = match.group(1)
    data = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = clean_value(value)
    return data


def write_frontmatter(path: Path, cover_rel_path: str, title: str, author: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return
    frontmatter_block = match.group(1)
    rest = text[match.end():]
    lines = frontmatter_block.splitlines()

    updated = False
    for idx, line in enumerate(lines):
        if line.startswith("cover:"):
            lines[idx] = f'cover: "{cover_rel_path}"'
            updated = True
            break

    if not updated:
        lines.append(f'cover: "{cover_rel_path}"')

    new_text = "---\n" + "\n".join(lines) + "\n---\n" + rest
    path.write_text(new_text, encoding="utf-8")


def download_image(url: str) -> Optional[Path]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read()
    except Exception:
        return None

    if not data:
        return None

    ext = ".jpg"
    if "png" in url.lower():
        ext = ".png"

    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    target = COVERS_DIR / f"cover-{digest}{ext}"
    target.write_bytes(data)
    return target


def fetch_cover(title: str, author: str) -> Optional[str]:
    search_query = " ".join([part for part in [title, author] if part]).strip()
    if not search_query:
        return None

    # Open Library
    openlib_url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(search_query)}&limit=5"
    try:
        req = urllib.request.Request(openlib_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = response.read().decode("utf-8")
            docs = __import__("json").loads(payload).get("docs", [])
        for doc in docs:
            cover_id = doc.get("cover_i")
            if cover_id:
                image_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                saved = download_image(image_url)
                if saved:
                    return saved.relative_to(VAULT_ROOT).as_posix()
    except Exception:
        pass

    # Google Books fallback
    gbooks_url = (
        "https://www.googleapis.com/books/v1/volumes?q="
        + urllib.parse.quote(f"intitle:{title} inauthor:{author}")
    )
    try:
        req = urllib.request.Request(gbooks_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = response.read().decode("utf-8")
            items = __import__("json").loads(payload).get("items", [])
        for item in items:
            image_links = item.get("volumeInfo", {}).get("imageLinks", {})
            image_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
            if image_url:
                saved = download_image(image_url)
                if saved:
                    return saved.relative_to(VAULT_ROOT).as_posix()
    except Exception:
        pass
    return None


def process_file(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False

    data = read_frontmatter(path)
    existing_cover = (data.get("cover") or "").strip()
    if existing_cover and existing_cover != "":
        return False

    title = data.get("title") or path.stem
    author = data.get("author") or ""
    cover_rel = fetch_cover(title, author)
    if not cover_rel:
        return False

    write_frontmatter(path, cover_rel, title, author)
    print(f"Updated {path.relative_to(VAULT_ROOT)} with cover {cover_rel}")
    return True


def process_all() -> int:
    updated = 0
    for path in sorted(BOOKS_DIR.glob("*.md")):
        if process_file(path):
            updated += 1
    return updated


def watch_files(interval: int = 5) -> None:
    seen = set()
    while True:
        for path in sorted(BOOKS_DIR.glob("*.md")):
            if path in seen:
                continue
            seen.add(path)
            process_file(path)
        time.sleep(interval)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch_files()
    else:
        updated = process_all()
        print(f"Processed {updated} book note(s) with new covers.")
