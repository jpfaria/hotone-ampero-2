"""Build catalog.json from the editor's bundled algorithm table (run once per editor version)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path("/Applications/Ampero II.app/Contents/Frameworks/App.framework/Versions/A/Resources/flutter_assets/assets/data/v1.0.9_alg_data.json")
OUT = Path(__file__).with_name("catalog.json")
WIDGET_FIELDS = ("Name", "ID", "knobID", "Type", "SubType", "DefaultValue", "DisplayMin", "DisplayMax", "Step", "Codeing", "Sync", "SyncDefault")


def _widgets(w):
    items = w if isinstance(w, list) else [w]
    return [{k: x[k] for k in WIDGET_FIELDS if k in x} for x in items]


def build(src: Path = SRC) -> dict:
    data = json.loads(src.read_text())
    cats = data["PluginProperties"]["Modules"]["Catalog"]
    return {
        "source": data["GeneratedInfo"].get("source_excel"),
        "categories": [
            {
                "index": int(c["Index"]),
                "name": c["Name"],
                "models": [
                    {
                        "index": int(a["Index"]),
                        "name": a["Name"],
                        "code": int(a["Code"]),
                        "classify": a.get("classify"),
                        "based_on": a.get("desInforEN"),
                        "signal": a.get("Signal"),
                        "params": _widgets(a.get("Widget", [])),
                    }
                    for a in c["Alg"]
                ],
            }
            for c in cats
        ],
    }


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    OUT.write_text(json.dumps(build(src), ensure_ascii=False, indent=0))
    print(OUT, OUT.stat().st_size, "bytes")
