"""Small offline manifest primitives; no business persistence."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ASSETS = ('png', 'pdf', 'gold.json', 'txt', 'regions.json', 'labels.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def asset_path(root, name):
    require(isinstance(name, str) and name and '\\' not in name, 'invalid asset path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')),
            f'invalid relative path: {name}')
    resolved = (root / name).resolve()
    require(resolved.is_relative_to(root.resolve()), f'asset escapes root: {name}')
    require(resolved.is_file(), f'missing asset: {name}')
    return resolved


def sample_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,119}', value),
            'invalid sample ID')
    return value
