"""Refresh explicit, human-reviewed official PDF URLs. No endpoint guessing.

Run manually from the project root. Network failures are recorded, never bypassed.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = "https://www.mcxindia.com/docs/default-source/"
SOURCES = [
    ("GOLDM", "2025-11-01", "2026-04-30", "products/contract-specification/gold-mini/gold-mini-november-2025-contract-onwardsfc22554857fb64e3bdfdff00007acb35.pdf"),
    ("GOLDM", "2026-05-01", "2026-07-31", "about-us/gold-mini-may-2026-contract-onwards.pdf"),
    ("GOLDM", "2026-08-01", None, "about-us/gold-mini-august-2026-contract-onwards8a79913a-e8de-4136-9f0b-25d31dc163c4.pdf"),
    ("GOLDTEN", "2025-04-01", "2025-10-31", "products/contract-specification/gold-ten/gold-ten-april-2025-contract-onwards7fb63e4857fb64e3bdfdff00007acb3580008247-f6c1-4a56-be21-ac18ff0bdbe4.pdf"),
    ("GOLDTEN", "2025-11-01", "2026-06-30", "products/contract-specification/gold-ten/gold-ten-november-2025-contract-onwards9a08564857fb64e3bdfdff00007acb35.pdf"),
    ("GOLDTEN", "2026-07-01", None, "about-us/gold-ten-july-2026-contract-onwards.pdf"),
    ("GOLDGUINEA", "2025-01-01", "2025-11-30", "products/contract-specification/gold-guinea/gold-guinea-january-2025-contract-onwards8992f3f6-d244-425a-9a53-66d94500bb34.pdf"),
    ("GOLDGUINEA", "2025-12-01", "2026-06-30", "products/contract-specification/gold-guinea/gold-guinea-december-2025-contract-onwardsdc22554857fb64e3bdfdff00007acb35.pdf"),
    ("GOLDGUINEA", "2026-07-01", None, "about-us/gold-guinea-july-2026-contract-onwards.pdf"),
    ("GOLDPETAL", "2025-04-01", "2025-11-30", "products/contract-specification/gold-petal/gold-petal-april-2025-contracts-onwards4b958087-3b38-44b0-abc2-30acd903c1ad.pdf"),
    ("GOLDPETAL", "2025-12-01", "2026-06-30", "products/contract-specification/gold-petal/gold-petal-december-2025-contracts-onwards7a08564857fb64e3bdfdff00007acb35.pdf"),
    ("GOLDPETAL", "2026-07-01", None, "about-us/gold-petal-july-2026-contract-onwards.pdf"),
]


def download(item):
    symbol, start, end, suffix = item
    url = BASE + suffix
    record = {"symbol": symbol, "effective_from": start, "effective_to": end, "source_url": url}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AURUM-X-Research/0.1 (manual official specification audit)"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(5 * 1024 * 1024 + 1)
        if not content.startswith(b"%PDF") or len(content) > 5 * 1024 * 1024:
            raise ValueError("Server did not return a PDF under 5 MiB")
        path = ROOT / "sources" / f"{symbol}_{start}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        record.update(source_hash=hashlib.sha256(content).hexdigest(), source_path=str(path.relative_to(ROOT)), downloaded=True)
    except Exception as exc:
        record.update(source_hash=None, downloaded=False, error=str(exc))
    return record


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(download, SOURCES))
    (ROOT / "source_audit.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k in {"symbol", "effective_from", "downloaded", "error"}} for r in records], indent=2))
