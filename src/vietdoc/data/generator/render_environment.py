"""D1 render fingerprint; no model/runtime service dependency or absolute paths."""
from importlib.metadata import version
from pathlib import Path
import platform
import sys
import zlib

from PIL import Image, ImageFont, features

from .artifact_io import sha


def environment():
    paths = {Path(Image.core.__file__), Path(ImageFont.core.__file__)}
    maps = Path('/proc/self/maps')
    if maps.is_file():
        for line in maps.read_text(encoding='utf-8').splitlines():
            name = line.split()[-1]
            if name.startswith('/') and Path(name).name.startswith(
                    ('libfreetype.', 'libraqm.', 'libharfbuzz.', 'libfribidi.', 'libz.', 'libpng')):
                paths.add(Path(name))
    return dict(python=platform.python_version(), platform=sys.platform,
                pillow=version('Pillow'), jsonschema=version('jsonschema'),
                freetype=features.version('freetype2'), raqm=features.version('raqm'),
                harfbuzz=features.version('harfbuzz'), fribidi=features.version('fribidi'),
                zlib=zlib.ZLIB_RUNTIME_VERSION,
                renderer_binaries={p.name: sha(p) for p in sorted(paths)})
