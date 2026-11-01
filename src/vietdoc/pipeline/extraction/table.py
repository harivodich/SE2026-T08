"""Header-driven table grouping; never infer amounts or zip incomplete rows."""

from __future__ import annotations

from collections import defaultdict
import re
from statistics import median
from typing import Callable

from .ocr_input import BaselineError, Block, Page, norm

HEADERS = {"tên hàng": "description", "hàng hóa": "description", "mô tả": "description",
           "sl": "quantity", "số lượng": "quantity", "đvt": "unit", "đơn vị": "unit",
           "đơn vị tính": "unit", "đơn giá": "unit_price", "thành tiền": "line_total"}
UNITS = {"kg", "g", "mét", "m", "hộp", "ly", "cái", "bộ", "chai", "gói", "tập", "quyển", "chiếc", "suất"}
NUMBER = re.compile(r"^-?\d[\d., ]*(?:\s*(?:đ|₫|vnd|vnđ))?$", re.IGNORECASE)


def _geometry_rows(headers: list[Block], cells: list[Block]) -> list[dict]:
    anchors = sorted((HEADERS[norm(block.text)], block.x) for block in headers)
    numeric = []
    role_cells = []
    for block in cells:
        distances = sorted((abs(block.x - x), role) for role, x in anchors)
        if len(distances) > 1 and abs(distances[0][0] - distances[1][0]) < 1e-12:
            raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
        role = distances[0][1]
        role_cells.append((role, block))
        if role != "description":
            numeric.append(block)
    if not cells:
        return []
    if not numeric:
        raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
    height = median(block.height for block in cells)
    groups: list[list[Block]] = []
    for block in sorted(numeric, key=lambda b: b.y):
        if not groups or abs(block.y - median(b.y for b in groups[-1])) > height * .75:
            groups.append([block])
        else:
            groups[-1].append(block)
    centers = [median(block.y for block in group) for group in groups]
    rows = [defaultdict(list) for _ in centers]
    for role, block in role_cells:
        choices = sorted((abs(block.y - y), i) for i, y in enumerate(centers))
        if (choices[0][0] > height * 3
                or len(choices) > 1 and abs(choices[0][0] - choices[1][0]) < 1e-12):
            raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
        rows[choices[0][1]][role].append(block)
    # Group spatially, then retain the declared reading order across and within rows.
    order = {block.block_id: index for index, block in enumerate(cells)}
    return sorted(rows, key=lambda row: min(order[block.block_id] for blocks in row.values() for block in blocks))


def _ordered_rows(headers: list[Block], cells: list[Block]) -> list[dict]:
    roles = [HEADERS[norm(block.text)] for block in headers]
    if roles[0] != "description" or len(roles) < 2:
        raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
    def starts_values(block):
        return norm(block.text) in UNITS if roles[1] == "unit" else bool(NUMBER.fullmatch(block.text.strip()))
    rows, cursor = [], 0
    while cursor < len(cells):
        row = defaultdict(list)
        while cursor < len(cells) and not starts_values(cells[cursor]):
            row["description"].append(cells[cursor])
            cursor += 1
        if not row["description"]:
            raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
        for role in roles[1:]:
            if cursor >= len(cells):
                raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
            block = cells[cursor]
            valid = norm(block.text) in UNITS if role == "unit" else bool(NUMBER.fullmatch(block.text.strip()))
            if not valid:
                raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
            row[role].append(block)
            cursor += 1
        rows.append(row)
        if len(rows) > 30:
            raise BaselineError("PROFILE_EXCEEDED")
    return rows


def table_rows(page: Page, is_scalar: Callable[[str], bool]) -> tuple[list[dict], bool]:
    blocks = page.blocks
    runs, cursor = [], 0
    while cursor < len(blocks):
        if norm(blocks[cursor].text) not in HEADERS:
            cursor += 1
            continue
        start = end = cursor
        while end < len(blocks) and norm(blocks[end].text) in HEADERS:
            end += 1
        roles = [HEADERS[norm(block.text)] for block in blocks[start:end]]
        if "description" in roles and "line_total" in roles:
            runs.append((start, end))
        cursor = end
    if len(runs) > 1:
        raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
    for start, end in runs:
        headers = list(blocks[start:end])
        roles = [HEADERS[norm(b.text)] for b in headers]
        if len(set(roles)) != len(roles):
            raise BaselineError("TABLE_LAYOUT_UNSUPPORTED")
        def boundary(index):
            block = blocks[index]
            if not is_scalar(block.text):
                return False
            description = next(h for h in headers if HEADERS[norm(h.text)] == "description")
            if block.quad is not None and description.quad is not None:
                others = [other for other in blocks[end:] if other is not block and other.quad is not None
                          and abs(other.y - block.y) <= max(other.height, block.height) * .75]
                located_headers = [header for header in headers if header.quad is not None]
                other_roles = {HEADERS[norm(min(located_headers, key=lambda h: abs(h.x - other.x)).text)]
                               for other in others} - {"description"}
                # A label-looking product description with several cells on its row
                # belongs to the table, not to the scalar footer.
                if abs(block.x - description.x) <= block.height and len(other_roles) >= 2:
                    return False
            return True
        stop = next((i for i in range(end, len(blocks)) if boundary(i)), len(blocks))
        cells = list(blocks[end:stop])
        geometric = all(b.quad is not None for b in headers + cells)
        rows = _geometry_rows(headers, cells) if geometric else _ordered_rows(headers, cells)
        if len(rows) > 30:
            raise BaselineError("PROFILE_EXCEEDED")
        return rows, True
    return [], False
