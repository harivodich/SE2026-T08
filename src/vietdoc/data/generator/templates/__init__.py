"""Versioned labels and fixed one-page layout identifiers."""
MONEY = {'unit_price', 'line_total', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount'}
LABELS = dict(merchant_name='Cửa hàng', merchant_address='Địa chỉ', transaction_date='Ngày bán',
              transaction_time='Giờ', invoice_number='Số hóa đơn', issue_date='Ngày lập',
              seller_name='Đơn vị bán', buyer_name='Đơn vị mua', subtotal='Cộng tiền hàng',
              tax_amount='Tiền thuế GTGT', discount_amount='Chiết khấu', total_amount='Tổng thanh toán')

TEMPLATE_VERSION = 'layout-v2'

PAGE_SIZE = (1500, 2600)
TITLES = {'invoice': 'HÓA ĐƠN BÁN HÀNG', 'receipt': 'PHIẾU THANH TOÁN'}


def columns(layout):
    """Return key/label/x/width in the template's logical reading order."""
    if layout not in (0, 1):
        raise ValueError('unsupported layout')
    result = [('description', 'Tên hàng', 45, 650), ('quantity', 'SL', 720, 100),
              ('unit', 'ĐVT', 850, 100), ('unit_price', 'Đơn giá', 1000, 190),
              ('line_total', 'Thành tiền', 1240, 210)]
    if layout:
        result = [result[0], result[2], result[1], result[3], result[4]]
        result = [(k, label, x, w) for (k, label, _, w), x in zip(result, [45, 720, 850, 1000, 1240])]
    return result
