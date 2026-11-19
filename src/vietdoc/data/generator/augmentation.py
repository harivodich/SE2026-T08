"""Seeded bounded image transforms with conservative visibility supervision."""
import copy
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..manifest import require
from .d21 import labels_for


def validate_policy(policy):
    require(set(policy) == {'name', 'shear', 'blur', 'noise', 'crop', 'unreadable'}, 'augmentation keys')
    require(isinstance(policy['name'], str) and policy['name'], 'augmentation name')
    for key, cap in (('shear', .025), ('blur', 1.0), ('noise', 18)):
        value = policy[key]
        require(type(value) in (int, float) and math.isfinite(value) and
                (-cap <= value <= cap if key == 'shear' else 0 <= value <= cap), f'augmentation bound: {key}')
    require(type(policy['noise']) is int, 'noise must be integer')
    require(isinstance(policy['crop'], list) and len(policy['crop']) == 4 and
            all(type(n) is int and 0 <= n <= 200 for n in policy['crop']), 'crop bounds: left/top/right/bottom <=200')
    require(type(policy['unreadable']) is bool, 'unreadable must be explicit boolean')
    return policy


def set_leaf(payload, pointer, value):
    parts = pointer.strip('/').split('/')
    if parts[0] == 'items':
        payload['items'][int(parts[1])][parts[2]] = value
    else:
        payload[parts[0]] = value


def augment(image, geometry, payload, policy, seed):
    validate_policy(policy)
    image, gold = image.copy(), copy.deepcopy(payload)
    labels = labels_for(gold)
    width, height = image.size
    left, top, right, bottom = policy['crop']
    shear = policy['shear']
    out_width, out_height = width - left - right, height - top - bottom

    def point(x, y):
        return [x + shear * (y - height / 2) - left, y - top]

    def bounds(region):
        x0, y0, x1, y1 = region['bbox_px']
        quad = [point(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        return [math.floor(min(p[0] for p in quad)), math.floor(min(p[1] for p in quad)),
                math.ceil(max(p[0] for p in quad)), math.ceil(max(p[1] for p in quad))], quad

    lost = set()
    for region in geometry['regions']:
        box, _ = bounds(region)
        if policy['unreadable'] or not (0 <= box[0] < box[2] <= out_width and 0 <= box[1] < box[3] <= out_height):
            if region['pointer']:
                lost.add(region['pointer'])
    # Remove every occurrence of a partially lost field. No surviving fragment may
    # silently supervise the complete source value; the base retains source truth.
    retained = []
    draw = ImageDraw.Draw(image)
    for region in geometry['regions']:
        box, quad = bounds(region)
        visible = (not policy['unreadable'] and region['pointer'] not in lost and
                   0 <= box[0] < box[2] <= out_width and 0 <= box[1] < box[3] <= out_height)
        if visible:
            retained.append(dict(region, bbox_px=box, quad_px=quad))
        else:
            draw.rectangle(region['bbox_px'], fill='white')
    for pointer in lost:
        set_leaf(gold, pointer, None)
        labels[pointer] = dict(status='obscured', raw=None,
                               reason='Conservative full-field masking after content loss or explicit unreadable slice.')
    # Pillow takes inverse affine coefficients. Forward: x'=x+s*(y-h/2).
    image = image.transform(image.size, Image.Transform.AFFINE,
                            (1, -shear, shear * height / 2, 0, 1, 0),
                            resample=Image.Resampling.BICUBIC, fillcolor='white')
    image = image.crop((left, top, width - right, height - bottom))
    if policy['blur']:
        image = image.filter(ImageFilter.GaussianBlur(policy['blur']))
    amplitude = policy['noise']
    if amplitude:
        rng = random.Random(seed)
        size = (max(1, out_width // 10), max(1, out_height // 10))
        noise = Image.frombytes('L', size, bytes(rng.randrange(128 - amplitude, 129 + amplitude)
                                               for _ in range(size[0] * size[1])))
        noise = noise.resize(image.size, Image.Resampling.BILINEAR).convert('RGB')
        image = ImageChops.add(image, noise, offset=-128)
    geometry = dict(geometry, width=out_width, height=out_height, regions=retained,
                    transform=dict(source_to_canonical=[1, shear, -shear * height / 2 - left, 0, 1, -top],
                                   canonical_to_source=[1, -shear, shear * height / 2 + left - shear * top, 0, 1, top],
                                   source_size=[width, height],
                                   lossy=any(policy['crop']) or len(retained) != len(geometry['regions'])))
    transcript = ''.join(r['text'] + '\n' for r in retained)
    return image, gold, labels, geometry, transcript
