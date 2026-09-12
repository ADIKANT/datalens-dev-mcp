"""Release checks reject downgrades, occupied tags and divergent artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'release_version.py'


def source(tmp_path, version='1.1.1', manifest='1.1.1', runtime='1.1.1'):
    (tmp_path / 'pyproject.toml').write_text(f'[project]\nname="datalens-dev-mcp"\nversion="{version}"\n')
    (tmp_path / '.codex-plugin').mkdir()
    (tmp_path / '.codex-plugin/plugin.json').write_text(json.dumps({'version': manifest}))
    (tmp_path / 'src/datalens_dev_mcp').mkdir(parents=True)
    (tmp_path / 'src/datalens_dev_mcp/__init__.py').write_text(f'__version__ = "{runtime}"\n')
    return tmp_path


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), *args], capture_output=True, text=True)


def test_stable_release_is_newer_than_legacy_and_validation_is_read_only(tmp_path):
    root = source(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = run(root, '--previous', '1.1.0+codex.20260910071145', '--tag', 'v1.1.1')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['version'] == '1.1.1'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('version,manifest,runtime,previous,tag', [
    ('1.1.0','1.1.0','1.1.0','1.1.0+codex.20260910071145', 'v1.1.0'),
    ('1.1.1+codex.1','1.1.1+codex.1','1.1.1+codex.1','1.1.0', 'v1.1.1+codex.1'),
    ('1.1.1','1.1.2','1.1.1','1.1.0', 'v1.1.1'),
    ('1.1.1','1.1.1','1.1.0','1.1.0', 'v1.1.1'),
    ('1.1.1','1.1.1','1.1.1','1.1.0', 'v1.1.2'),
])
def test_invalid_release_fails(tmp_path, version, manifest, runtime, previous, tag):
    result = run(source(tmp_path, version, manifest, runtime), '--previous', previous, '--tag', tag)
    assert result.returncode != 0


def test_occupied_tag_cannot_be_reissued(tmp_path):
    root = source(tmp_path)
    result = run(root, '--existing-tag', 'v1.1.1')
    assert result.returncode != 0
    assert 'occupied' in result.stderr


def test_controlled_sync_uses_pyproject_without_changing_it(tmp_path):
    root = source(tmp_path, '1.1.2', '1.1.1', '1.1.1')
    before = (root / 'pyproject.toml').read_bytes()
    result = run(root, '--sync', '--previous', '1.1.1')
    assert result.returncode == 0, result.stderr
    assert (root / 'pyproject.toml').read_bytes() == before
    assert json.loads((root / '.codex-plugin/plugin.json').read_text())['version'] == '1.1.2'
    assert run(root).returncode == 0


def test_git_tag_inventory_and_existing_release_checkout(tmp_path):
    root = source(tmp_path)
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)
    git('init')
    git('add', '.')
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-m', 'fixture')
    git('tag', 'v1.1.1')
    assert run(root, '--check-git').returncode == 1
    assert run(root, '--check-git', '--tag', 'v1.1.1').returncode == 0
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '--allow-empty', '-m', 'changed')
    assert run(root, '--check-git', '--tag', 'v1.1.1').returncode == 1


def test_archive_audit_rejects_version_content_mismatch(tmp_path):
    import zipfile
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_audit', SCRIPT.with_name('check_public_release.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / 'synthetic.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('datalens_dev_mcp/server.py', '')
        archive.writestr('datalens_dev_mcp/api/sdk_adapter.py', '')
        archive.writestr('datalens_dev_mcp/assets/recipes/registry.json', '{}')
        archive.writestr('datalens_dev_mcp/__init__.py', '__version__ = "1.1.0"\n')
        archive.writestr('datalens_dev_mcp-1.1.1.dist-info/METADATA', 'Name: datalens-dev-mcp\nVersion: 1.1.1\n')
    with pytest.raises(ValueError, match='version'):
        module.audit(wheel)
