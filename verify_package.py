"""Check the book-pinned teaching-experiment surface, not mutable documentation.

SHA-256 verifies content identity, not publisher identity or software safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

# Deliberately exclude README, book links, LICENSE, CI YAML, and editorial files.
# A new experimental Python source, plan, fixture or result is automatically in scope.
TRACKED_GLOBS = (
    'lab/**/*.py',
    'lab/*.json',
    'lab/test-results.txt',
    'examples/ci/*.py',
    'tools/test_verify_package.py',
    'verify_package.py',
)
SCHEMA = 'teaching-experiment-manifest/v1'


def expected_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for pattern in TRACKED_GLOBS:
        for candidate in root.glob(pattern):
            if candidate.is_file() or candidate.is_symlink():
                paths.add(candidate.relative_to(root).as_posix())
    return paths


def verify(root: Path, expected_manifest_sha256: str | None = None) -> tuple[int, list[str]]:
    """Return checked-file count and problems, including omitted experiment files."""
    manifest_path = root / 'FILE-MANIFEST.json'
    try:
        raw = manifest_path.read_bytes()
        if expected_manifest_sha256 is not None:
            expected_manifest_sha256 = expected_manifest_sha256.removeprefix('sha256:')
            if re.fullmatch(r'[0-9a-f]{64}', expected_manifest_sha256) is None:
                return 0, ['Expected manifest SHA-256 must be 64 lowercase hex digits.']
            if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
                return 0, ['Manifest does not match the digest supplied from the book.']
        manifest = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError) as exc:
        return 0, [f'Cannot read manifest: {exc}']
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        return 0, ['Unsupported experiment manifest schema.']
    if manifest.get('tracked_globs') != list(TRACKED_GLOBS):
        return 0, ['Manifest must declare the exact experiment file-selection rules.']
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        return 0, ['The manifest has no file entries.']
    checked = 0
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append('Invalid file entry.')
            continue
        name, expected = entry.get('path'), entry.get('sha256')
        if not isinstance(name, str) or not name:
            errors.append('Missing relative path.')
            continue
        path = PurePosixPath(name)
        if (path.is_absolute() or name != path.as_posix() or
                any(p in ('', '.', '..') for p in name.split('/')) or
                '\\' in name or ':' in name or name in seen or name == 'FILE-MANIFEST.json'):
            errors.append(f'Invalid or duplicate path: {name!r}')
            continue
        seen.add(name)
        if not isinstance(expected, str) or re.fullmatch(r'[0-9a-f]{64}', expected) is None:
            errors.append(f'Invalid SHA-256: {name}')
            continue
        candidate = root.joinpath(*path.parts)
        if any(part.is_symlink() for part in [candidate, *candidate.parents] if part != root.parent):
            errors.append(f'Symbolic links are not supported: {name}')
            continue
        if not candidate.resolve().is_relative_to(root.resolve()):
            errors.append(f'Path escapes package: {name}')
            continue
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            errors.append(f'Cannot read {name}: {exc}')
            continue
        checked += 1
        if hashlib.sha256(data).hexdigest() != expected:
            errors.append(f'Content mismatch: {name}')
        size = entry.get('size_bytes')
        if type(size) is not int or size != len(data):
            errors.append(f'Size mismatch: {name}')
    # A listed file must be part of the declared experiment surface.
    expected_set = expected_paths(root)
    missing = expected_set - seen
    extra = seen - expected_set
    if missing:
        errors.append('Unlisted experiment files: ' + ', '.join(sorted(missing)))
    if extra:
        errors.append('Listed files outside experiment scope: ' + ', '.join(sorted(extra)))
    return checked, errors


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-manifest-sha256', help='Manifest digest copied from the corresponding book edition.')
    args = parser.parse_args()
    checked, errors = verify(root, args.expected_manifest_sha256)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f'FAILED: {checked} experimental files checked.', file=sys.stderr)
        return 1
    print(f'OK: {checked} teaching-experiment files match FILE-MANIFEST.json.')
    print('README and other docs can change independently. This does not authenticate the publisher.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
