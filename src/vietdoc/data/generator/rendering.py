"""Shared D1.2/D2.1 raster renderer; bounds checked before accepting output."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .templates import LABELS, MONEY, PAGE_SIZE, TITLES, columns

FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

def raw(key, value):
    if value is None:
        return None
    if key in MONEY:
        integer, dot, fraction = value.partition('.')
        return f'{int(integer):,}'.replace(',', '.') + (',' + fraction if dot else '') + ' đ'
    if key.endswith('date'):
        return '/'.join(reversed(value.split('-')))
    return value.replace('.', ',') if key == 'quantity' else value


def render(payload, kind, layout, font_path=FONT):
    if kind not in TITLES:
        raise ValueError("unsupported document type")
    table_columns = columns(layout)
    width, height = PAGE_SIZE
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 23)
    title_font = ImageFont.truetype(str(font_path), 32)
    regions, transcript = [], []
    y = 35

    def text(value, x, top, pointer=None, title=False):
        face = title_font if title else font
        box = list(draw.textbbox((x, top), value, font=face))
        if not (0 <= box[0] < box[2] < width and 0 <= box[1] < box[3] < height):
            raise ValueError(f'Clipping: {value}: {box}')
        draw.text((x, top), value, font=face, fill='black')
        transcript.append(value)
        regions.append(dict(text=value, pointer=pointer, page=0, bbox_px=box))

    text(TITLES[kind], 45, y, title=True)
    y += 55
    text('DỮ LIỆU HƯ CẤU — KHÔNG CÓ GIÁ TRỊ GIAO DỊCH', 45, y)
    y += 45
    for key, value in payload.items():
        if key == 'items' or key in MONEY or value is None:
            continue
        text(LABELS[key] + ': ' + raw(key, value), 45 if layout == 0 else 180, y, '/' + key)
        y += 36
    y += 15
    for _, label, x, _ in table_columns:
        text(label, x, y)
    y += 38
    for index, row in enumerate(payload['items']):
        max_lines = 1
        for key, _, x, max_width in table_columns:
            value = raw(key, row[key])
            if value is None:
                continue
            lines, line = [], ''
            for word in value.split():
                if draw.textlength(word, font=font) > max_width:
                    raise ValueError('Word exceeds column')
                candidate = (line + ' ' + word).strip()
                if draw.textlength(candidate, font=font) > max_width:
                    if not line:
                        raise ValueError('Word exceeds column')
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for offset, fragment in enumerate(lines):
                text(fragment, x, y + offset * 29, f'/items/{index}/{key}')
            max_lines = max(max_lines, len(lines))
        y += max_lines * 29 + 8
        if layout:
            draw.line((40, y - 3, 1460, y - 3), fill='#bbbbbb')
    y += 20
    for key in payload:
        if key in MONEY and payload[key] is not None:
            text(LABELS[key] + ': ' + raw(key, payload[key]), 650 if layout == 0 else 45, y, '/' + key)
            y += 36
    if payload['total_amount'] is not None:
        text('Số tiền ghi lại: ' + raw('total_amount', payload['total_amount']), 45, y + 10, '/total_amount')
    return image, '\n'.join(transcript) + '\n', dict(
        convention='renderer-local-v1; not approved shared geometry', page=0,
        width=width, height=height, origin='top-left', units='pixels',
        transform='identity; PNG is the rendered page', regions=regions)
