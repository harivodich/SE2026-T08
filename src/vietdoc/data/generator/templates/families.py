"""Ten structural families per type; shared fonts/colors are deliberately fixed."""
from PIL import Image, ImageDraw, ImageFont

from . import LABELS, MONEY, PAGE_SIZE, TITLES
from ..rendering import raw

VERSION = 'families-v1'
ORDERS = (
    ('description', 'quantity', 'unit', 'unit_price', 'line_total'),
    ('quantity', 'description', 'unit_price', 'unit', 'line_total'),
    ('line_total', 'description', 'unit', 'quantity', 'unit_price'),
    ('unit_price', 'quantity', 'description', 'line_total', 'unit'),
    ('unit', 'line_total', 'quantity', 'unit_price', 'description'),
)
CELL_LABELS = dict(description='Mặt hàng / dịch vụ', quantity='Số lượng', unit='Đơn vị',
                   unit_price='Giá bán', line_total='Cộng dòng')
ALTERNATE = dict(LABELS, merchant_name='Điểm bán', merchant_address='Nơi bán',
                 transaction_date='Ngày giao dịch', transaction_time='Lúc',
                 invoice_number='Mã chứng từ', issue_date='Ngày phát hành',
                 seller_name='Bên cung cấp', buyer_name='Khách mua', total_amount='Phải trả')


def catalog():
    return [dict(family_id=f'{kind}-f{i:02}', document_type=kind, index=i,
                 header='two columns' if i >= 5 else 'stacked',
                 totals='above table' if i >= 5 else 'below table',
                 columns=list(ORDERS[i % 5]), vocabulary='alternate' if i >= 5 else 'standard',
                 split='train' if i < 6 else 'dev' if i < 8 else 'final')
            for kind in ('receipt', 'invoice') for i in range(10)]


def render_family(payload, family, font_path):
    width, height = PAGE_SIZE
    image = Image.new('RGB', PAGE_SIZE, 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 23)
    regions = []

    def text(value, x, y, pointer=None, limit=1400):
        lines, line = [], ''
        for word in value.split():
            if draw.textlength(word, font=font) > limit:
                raise ValueError('word exceeds family column')
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=font) > limit:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        for j, fragment in enumerate(lines):
            top = y + 30 * j
            box = list(draw.textbbox((x, top), fragment, font=font))
            if not (0 <= box[0] < box[2] < width and 0 <= box[1] < box[3] < height):
                raise ValueError('family layout overflow/clipping')
            draw.text((x, top), fragment, font=font, fill='black')
            regions.append(dict(text=fragment, pointer=pointer, page=0, bbox_px=box))
        return len(lines) * 30

    i = family['index']
    labels = ALTERNATE if i >= 5 else LABELS
    text(TITLES[family['document_type']], 45, 35)
    text('DỮ LIỆU HƯ CẤU — KHÔNG CÓ GIÁ TRỊ GIAO DỊCH', 45, 75)
    y, column_y = 130, [130, 130]
    scalars = [(k, v) for k, v in payload.items() if k != 'items' and k not in MONEY and v is not None]
    for index, (key, value) in enumerate(scalars):
        col = index % 2 if i >= 5 else 0
        top = column_y[col] if i >= 5 else y
        used = text(labels[key] + ': ' + raw(key, value), 45 + col * 730, top,
                    '/' + key, 680 if i >= 5 else 1400)
        if i >= 5:
            column_y[col] += used + 8
        else:
            y += used + 8
    y = max(column_y) + 20 if i >= 5 else y + 20

    def totals(top):
        for key, value in payload.items():
            if key in MONEY and value is not None:
                top += text(labels[key] + ': ' + raw(key, value), 650 if i < 5 else 45,
                            top, '/' + key, 800 if i < 5 else 1400) + 8
        return top

    if i >= 5:
        y = totals(y) + 30
    columns = []
    x = 45
    for key in ORDERS[i % 5]:
        size = dict(description=620, quantity=140, unit=140, unit_price=250, line_total=250)[key]
        columns.append((key, x, size - 15))
        x += size
    header_height = max(text(CELL_LABELS[k], x, y, limit=w) for k, x, w in columns)
    y += header_height + 12
    for index, row in enumerate(payload['items']):
        used = 30
        for key, x, size in columns:
            if row[key] is not None:
                used = max(used, text(raw(key, row[key]), x, y, f'/items/{index}/{key}', size))
        y += used + 12
        draw.line((45, y - 5, 1445, y - 5), fill='#bbbbbb')
    if i < 5:
        totals(y + 25)
    return image, dict(convention='renderer-local-v1; not approved shared geometry', page=0,
                       width=width, height=height, origin='top-left', units='pixels',
                       transform='identity; PNG is canonical', regions=regions)
