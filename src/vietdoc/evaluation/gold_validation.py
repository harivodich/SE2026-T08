"""File-boundary validation; renderer dependencies are loaded only in renderer mode."""
from pathlib import Path
from importlib.metadata import version
import platform

from vietdoc.data.manifest import read_json, require, sha

RENDERER_VERSIONS = frozenset(('d1.2.v1', 'd1.2.v2', 'd2.1.v1', 'd2.2.v1'))
VERSION = 'renderer-consumer-semantic.v1'


def validate(root, manifest_path, manifest, samples, *, mode, manifest_hash):
    """Run the actual consumer validator, never accept a caller's validation receipt.

    This certifies schema/metadata/sidecar consistency, not pixels, renderer replay,
    annotation truth, or consumer/Lead approval. Scoring itself stays stdlib-only.
    """
    require(mode in ('renderer', 'annotated'), 'unsupported gold mode')
    renderer = manifest['version'] in RENDERER_VERSIONS
    require(renderer == (mode == 'renderer'),
            'gold mode mismatch: known renderer formats require renderer; other sources require annotated')
    result = dict(mode=mode, status='unvalidated', manifest_sha256=manifest_hash,
                  scope='annotation integrity only; no semantic gold certification')
    if renderer:
        from vietdoc.data.generator import integration

        root, manifest_path = Path(root).resolve(), Path(manifest_path).resolve()
        integration.check_manifest(manifest)
        schema_path = root / 'specs/contracts/business.schema.json'
        schema = read_json(schema_path)
        for entry, sample in zip(manifest['samples'], samples):
            sid = sample['sample_id']
            try:
                gold = integration.check_sample(root, manifest_path, entry, manifest, schema)
                require(gold == sample['gold'], 'gold changed during validation')
            except (ValueError, OSError, KeyError, TypeError) as error:
                raise ValueError(f'{sid}: {error}') from error
        data_root = Path(integration.__file__).parents[1]
        result.update(status='validated', validator_version=VERSION,
                      scope='renderer consumer schema, metadata, assets and sidecar semantics; not pixel replay',
                      schema_sha256=sha(schema_path),
                      runtime=dict(python=platform.python_version(),
                                   pillow=version('Pillow'), jsonschema=version('jsonschema')),
                      validator_sources={p.relative_to(data_root).as_posix(): sha(p)
                                         for p in sorted(data_root.rglob('*.py'))},
                      assets=[dict(sample_id=e['sample_id'], asset=key, **asset)
                              for e in manifest['samples'] for key, asset in e['assets'].items()])
    require(sha(manifest_path) == manifest_hash, 'manifest changed during validation')
    return result
