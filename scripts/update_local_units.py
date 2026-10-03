"""Refresh the official Croix-Rouge local-unit URL index (manual, explicit run)."""
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "https://www.croix-rouge.fr/sitemap-structures.xml"
DEST = Path(__file__).resolve().parents[1] / "data" / "local_units.json"

with urllib.request.urlopen(SOURCE, timeout=30) as response:
    root = ET.fromstring(response.read())
urls = [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text and "/unite-locale-" in node.text]
if len(urls) < 400:
    raise SystemExit(f"Refusing to replace the index: only {len(urls)} unit URLs found")
units = []
for page in urls:
    slug = page.rstrip("/").split("/")[-1]
    city = slug.replace("unite-locale-", "").replace("-", " ").title()
    if slug == "unite-locale-de-calais":
        city = "Calais"
    units.append({"slug": slug, "name": f"Unité locale de {city}", "source_url": page, "postal_code": "", "city": city})
units.sort(key=lambda item: (item["slug"] != "unite-locale-de-calais", item["name"].casefold()))
record = {"source_url": SOURCE, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source_note": "Official structure sitemap; only /unite-locale- URLs included. Names are derived from URL slugs; follow source URL for the current official label.", "units": units}
DEST.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(units)} local units to {DEST}")
