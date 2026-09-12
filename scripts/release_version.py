"""Validate a stable release; --sync explicitly copies pyproject version to mirrors.

Run during release preparation, never during installation or MCP startup.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import subprocess
import tomllib
from pathlib import Path

from packaging.version import Version


def validate(root: Path, *, previous: list[str], tag: str | None, existing_tags: list[str], sync: bool) -> dict:
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('release version must be stable MAJOR.MINOR.PATCH')
    expected_tag = f'v{version}'
    if tag is not None and tag != expected_tag:
        raise ValueError('tag does not match package version')
    if expected_tag in existing_tags:
        raise ValueError(f'tag {expected_tag} is occupied; do not reissue it')
    for old in [*previous, *(value.removeprefix('v') for value in existing_tags)]:
        if Version(version) <= Version(old):
            raise ValueError(f'version {version} must be newer than {old}')
    manifest_path = root / '.codex-plugin/plugin.json'
    runtime_path = root / 'src/datalens_dev_mcp/__init__.py'
    manifest = json.loads(manifest_path.read_text())
    runtime = runtime_path.read_text()
    if sync:
        manifest['version'] = version
        updated, count = re.subn(r'(?m)^__version__ = [^\n]+$', f'__version__ = "{version}"', runtime)
        if count != 1:
            raise ValueError('expected one static runtime version assignment')
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        runtime_path.write_text(updated)
        runtime = updated
    assignments = [ast.literal_eval(node.value) for node in ast.parse(runtime).body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__'
                                                          for t in node.targets)]
    if assignments != [version] or manifest.get('version') != version:
        raise ValueError('pyproject, runtime and plugin versions differ; run --sync during release preparation')
    return {'version': version, 'tag': expected_tag, 'previous': previous, 'synchronized': sync}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--previous', action='append', default=[])
    parser.add_argument('--tag')
    parser.add_argument('--existing-tag', action='append', default=[])
    parser.add_argument('--sync', action='store_true')
    parser.add_argument('--check-git', action='store_true', help='Validate against all fetched release tags')
    args = parser.parse_args()
    try:
        if args.check_git:
            result = subprocess.run(['git', '-C', str(args.root), 'tag', '--list'], check=True,
                                    capture_output=True, text=True)
            tags = [t for t in result.stdout.splitlines() if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:\+[^ ]+)?', t)]
            if args.tag in tags:
                tagged = subprocess.check_output(['git', '-C', str(args.root), 'rev-parse', args.tag + '^{}'], text=True).strip()
                head = subprocess.check_output(['git', '-C', str(args.root), 'rev-parse', 'HEAD'], text=True).strip()
                if tagged != head:
                    raise ValueError('occupied release tag points to another commit')
                tags.remove(args.tag)
            args.existing_tag.extend(tags)
        result = validate(args.root, previous=args.previous, tag=args.tag,
                          existing_tags=args.existing_tag, sync=args.sync)
    except (ValueError, OSError, KeyError, SyntaxError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
