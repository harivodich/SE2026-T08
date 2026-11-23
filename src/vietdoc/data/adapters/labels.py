"""Versioned label projection; no model, batching or loss policy."""
from dataclasses import dataclass
from typing import Literal

from vietdoc.data.generator.artifact_io import require

VERSION = 'vietdoc.field-labels.v1'
Status = Literal['present', 'absent', 'obscured', 'unlabeled']


@dataclass(frozen=True)
class FieldLabel:
    pointer: str
    value: str | None
    status: Status


@dataclass(frozen=True)
class FieldLabels:
    version: str
    fields: tuple[FieldLabel, ...]


def field_labels(gold, labels):
    """Validate annotation coverage/statuses and project business scalar leaves.

    This in-memory accessor does NOT certify schema, assets or provenance. Use
    load_training_labels at the renderer file boundary for those checks.
    """
    require(isinstance(gold, dict) and isinstance(gold.get('items'), list), 'invalid gold object/items')
    values = {'/' + key: value for key, value in gold.items() if key != 'items'}
    for index, row in enumerate(gold['items']):
        require(isinstance(row, dict), 'invalid gold item')
        values.update({f'/items/{index}/{key}': value for key, value in row.items()})
    require(all(isinstance(value, str) or value is None for value in values.values()),
            'business leaves must be strings or null')
    require(isinstance(labels, dict) and set(labels) == set(values), 'label pointer coverage mismatch')
    fields = []
    for pointer, value in sorted(values.items()):
        label = labels[pointer]
        require(isinstance(label, dict) and set(label) == {'status', 'raw', 'reason'}, f'invalid label: {pointer}')
        status = label['status']
        require(status in ('present', 'absent', 'obscured', 'unlabeled') and
                (status == 'present') == (value is not None), f'label status mismatch: {pointer}')
        require(isinstance(label['raw'], str) and bool(label['raw']) if status == 'present' else
                label['raw'] is None or (status == 'obscured' and isinstance(label['raw'], str)),
                f'label raw mismatch: {pointer}')
        require(label['reason'] is None if status == 'present' else
                isinstance(label['reason'], str) and bool(label['reason']), f'label reason mismatch: {pointer}')
        fields.append(FieldLabel(pointer, value, status))
    return FieldLabels(VERSION, tuple(fields))


def load_training_labels(root, manifest, *, full_set=False):
    """Yield (sample, gold, FieldLabels) only after the whole manifest validates.

    Labels are the exact objects checked by the existing renderer consumer;
    never reread mutable files or infer status from a null business value.
    """
    from vietdoc.data.generator.integration import load_labeled_artifacts

    loaded = []
    for sample, gold, labels in load_labeled_artifacts(root, manifest, full_set=full_set):
        try:
            loaded.append((sample, gold, field_labels(gold, labels)))
        except ValueError as error:
            raise ValueError(f'{sample["sample_id"]}: {error}') from error
    yield from loaded
