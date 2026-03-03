"""
Simple ingestion script for glossary/recipe style RAG data.

Usage examples:
  python -m GohotBlenderAgent.context.rag_ingest --url https://docs.blender.org/manual/zh-hans/latest/
  python -m GohotBlenderAgent.context.rag_ingest --file ./notes.md
"""

from __future__ import annotations

import argparse
import os
import re
import urllib.request

from .vector_store import get_vector_store


def _read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _strip_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunks(text: str, size: int = 900, overlap: int = 120):
    if not text:
        return
    i = 0
    n = len(text)
    while i < n:
        yield text[i : i + size]
        i += max(1, size - overlap)


def ingest_text(source_id: str, text: str, kind: str = "reference"):
    store = get_vector_store()
    norm = _strip_html(text)
    for idx, chunk in enumerate(_chunks(norm)):
        store.upsert(
            f"rag_ref_{source_id}_{idx}",
            chunk,
            {"kind": kind, "source": source_id},
        )
    store.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--file", action="append", default=[])
    args = parser.parse_args()

    for url in args.url:
        try:
            text = _read_url(url)
            ingest_text(source_id=url.replace("://", "_"), text=text, kind="reference_url")
            print(f"[ingest] ok url: {url}")
        except Exception as e:
            print(f"[ingest] failed url {url}: {e}")

    for fp in args.file:
        try:
            text = _read_file(fp)
            ingest_text(source_id=os.path.basename(fp), text=text, kind="reference_file")
            print(f"[ingest] ok file: {fp}")
        except Exception as e:
            print(f"[ingest] failed file {fp}: {e}")


if __name__ == "__main__":
    main()

