from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, safe_error_text
from datalens_dev_mcp.authoring.artifacts import write_private_json
from datalens_dev_mcp.objects.write import _recordable, _usable_full_read


class BackupService:
    def __init__(self, reader: Any) -> None:
        self.reader = reader

    def export(self, targets: list[dict[str, Any]], output_dir: str | Path) -> dict[str, Any]:
        root = Path(output_dir).expanduser().resolve()
        if any("expected_saved_revision" in target for target in targets):
            raise ValueError("Backup uses branch/revision_id; expected_saved_revision is a publish precondition")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        for index, target in enumerate(targets):
            object_type = str(target["object_type"])
            object_id = str(target["object_id"])
            branch = str(target.get("branch") or "saved")
            try:
                revision_id = target.get("revision_id")
                readback = self.reader.object_get(object_type, object_id, branch=branch, revision_id=revision_id)
                identity = readback.get("identity") or {}
                identity_checked = identity.get("object_type") == object_type and identity.get("object_id") == object_id
                identity_checked = identity_checked and (not revision_id or identity.get("revision_id") == revision_id)
                identity_checked = identity_checked and identity.get("branch") == (
                    "unbranched" if object_type in {"connection", "workbook"} else branch)
                protected = _recordable(readback, object_type)
                content_complete = _usable_full_read(readback) and protected == readback
                if object_type == "html_page":
                    content_complete = content_complete and isinstance(readback.get("object", {}).get("content"), str)
                slug = re.sub(r"[^A-Za-z0-9._-]+", "_", object_id)[:80] or "object"
                filename = f"{index:04d}-{object_type}-{slug}.json"
                write_private_json(root / filename, protected)
                entries.append(
                    {
                        "object_type": object_type,
                        "object_id": object_id,
                        "branch": branch,
                        "status": "exported",
                        "file": filename,
                        "requested_revision": revision_id,
                        "observed_identity": identity,
                        "file_written": True,
                        "target_verified": identity_checked,
                        "content_complete": content_complete,
                    }
                )
            except (DataLensApiError, ValueError, TypeError, OSError) as exc:
                entries.append(
                    {
                        "object_type": object_type,
                        "object_id": object_id,
                        "branch": branch,
                        "status": "failed",
                        "error": safe_error_text(exc),
                    }
                )
        complete = bool(entries) and all(item.get("target_verified") and item.get("content_complete") for item in entries)
        manifest = {
            "schema_version": 1,
            "artifact_kind": "snapshot_not_full_restore",
            "complete": complete,
            "restore_verified": False,
            "objects": entries,
        }
        path = root / "manifest.json"
        write_private_json(path, manifest)
        return {"ok": complete, "complete": complete, "manifest_path": str(path), "objects": entries}
