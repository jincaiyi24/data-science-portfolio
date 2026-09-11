from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/sanitize_notebook.py NOTEBOOK.ipynb")

    path = Path(sys.argv[1]).resolve()
    notebook = json.loads(path.read_text(encoding="utf-8"))
    code_cells = 0

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") == "code":
            code_cells += 1
            cell["outputs"] = []
            cell["execution_count"] = None

        metadata = cell.get("metadata")
        if isinstance(metadata, dict):
            metadata.pop("execution", None)
            metadata.pop("trusted", None)

    notebook.get("metadata", {}).pop("widgets", None)
    path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Sanitized {path.name}: cleared {code_cells} code cells")


if __name__ == "__main__":
    main()

