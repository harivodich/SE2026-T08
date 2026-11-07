"""Deterministic, lossless single-page raster PDF (no timestamps or file ID)."""
import zlib


def pdf_bytes(image):
    width, height = image.size
    pixels = zlib.compress(image.convert('RGB').tobytes(), 9)
    content = f'q {width} 0 0 {height} 0 0 cm /Im0 Do Q\n'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>'.encode(),
               f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n'.encode() + pixels + b'\nendstream',
               f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'endstream']
    output = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    start = len(output)
    output.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)
