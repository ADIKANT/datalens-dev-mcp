from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, safe_error_text


class BackupService:
    def __init__(self, reader: Any) -> None:
        self.reader = reader

    def export(self, targets: list[dict[str, Any]], output_dir: str | Path) -> dict[str, Any]:
        root = Path(output_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        for index, target in enumerate(targets):
            object_type = str(target["object_type"])
            object_id = str(target["object_id"])
            branch = str(target.get("branch") or "saved")
            try:
                readback = self.reader.object_get(object_type, object_id, branch=branch)
                slug = re.sub(r"[^A-Za-z0-9._-]+", "_", object_id)[:80] or "object"
                filename = f"{index:04d}-{object_type}-{slug}.json"
                (root / filename).write_text(
                    json.dumps(readback, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
                )
                entries.append(
                    {
                        "object_type": object_type,
                        "object_id": object_id,
                        "branch": branch,
                        "status": "exported",
                        "file": filename,
                    }
                )
            except (DataLensApiError, ValueError, TypeError) as exc:
                entries.append(
                    {
                        "object_type": object_type,
                        "object_id": object_id,
                        "branch": branch,
                        "status": "failed",
                        "error": safe_error_text(exc),
                    }
                )
        complete = all(item["status"] == "exported" for item in entries)
        manifest = {
            "schema_version": 1,
            "artifact_kind": "snapshot_not_full_restore",
            "complete": complete,
            "restore_verified": False,
            "objects": entries,
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return {"ok": complete, "complete": complete, "manifest_path": str(path), "objects": entries}
