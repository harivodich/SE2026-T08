# AI-1 — OCR/page input, geometry và loader

**Proposed**, dành cho AI-1, Backend và AI-2 review. Types chạy được ở
[`contracts/ocr.py`](../src/vietdoc/contracts/ocr.py), ví dụ giả ở
[`ocr-page-proposal.json`](../tests/fixtures/ocr-page-proposal.json).
Đây chưa là shared JSON Schema được chấp nhận. Backend vẫn owns neutral schemas/
Java DTO; AI-2 owns compute envelope. Không thay [compute protocol](../specs/contracts/compute-api.md),
[result schema](../specs/contracts/extraction-result.schema.json) hay ADR status.

## Trạng thái bàn giao hiện tại — 2026-10-24

- Có loader/OCR pretrained/geometry/evidence và local HTML review report chạy được.
  AI-2 có entrypoint `recognize_document`; xem hướng dẫn ở Python README bên dưới.
- Theo yêu cầu người dùng, **D1/D3 và baseline-dependent preprocess improvement
  để sau** khi Data bàn giao. Không tự tạo dataset/evaluator thay phần Data.
- Chưa nghiệm thu G0/O2.2/O3/O4/O5 toàn hệ thống: còn consumer review/wiring của
  AI-2, canonical asset promotion và viewer integration của Backend. Không sửa
  business DB/Java UI hoặc tự ghép các feature branches để thay consumer approval.
- Tests/synthetic outputs chứng minh code behavior; chưa là CER/WER/per-type
  quality evidence trên chứng từ độc lập. Detector vẫn có box rộng ở mẫu số lặp.

## Ảnh và pixel format

| Dạng | Ý nghĩa | Quy ước đề xuất |
|---|---|---|
| Original | Bytes JPEG/PNG/PDF upload bất biến | Không gán geometry OCR lên preview original |
| Canonical | Ảnh viewer sau EXIF orientation hoặc render PDF một trang | RGB, uint8, [0,255], width/height sau orientation/render, page=0 |
| Processed | Ảnh thực sự đưa vào OCR, có thể resize/deskew | RGB/BGR/GRAY uint8 [0,255], dimensions riêng, transform về canonical |

RGB/BGR array dự kiến shape `(height, width, 3)`; GRAY `(height, width)`.
Width là số cột, height là số dòng. Types chỉ mô tả metadata; O1.2 phải kiểm
pixels/shape/dtype thực khi decode. Không đưa ndarray hoặc đường dẫn caller vào
JSON. Canonical/processed asset keys và hashes thuộc attempt manifest của service.

Chưa chọn/pin OCR engine ở O1.1. BGR trong fixture chỉ minh họa format explicit,
không khẳng định API của một bản PaddleOCR. O1.3 phải smoke engine/model và adapter
convert đúng format được kiểm chứng; không đổi RGB/BGR âm thầm.

## Hệ tọa độ và quad

- Gốc trên trái; x tăng sang phải, y tăng xuống dưới. Dùng pixel-edge coordinates:
  khung canonical là `[0,width] × [0,height]`, không phải pixel-center indices.
- OCR output `quad` luôn ở canonical normalized coordinates: `x/width`, `y/height`.
  Mỗi số finite trong `[0,1]`; không clamp để che mapping sai.
- Bốn đỉnh đi clockwise theo hệ ảnh, convex và không trùng/collinear/self-crossing.
  Bắt đầu tại điểm có `(y,x)` nhỏ nhất: y nhỏ nhất, hòa thì x nhỏ nhất. Với rectangle
  nằm ngang là top-left → top-right → bottom-right → bottom-left. Với chữ nghiêng,
  anchor này không hứa là góc semantic top-left của dòng chữ.
- Adapter cần reorder corners vendor có chủ ý trước khi tạo type; validator reject
  thứ tự sai, không tự sửa hoặc đoán vùng nguồn.
- `blocks` là ordered array; thứ tự do OCR adapter cung cấp, giữ nguyên khi parse.
  `block_id` nonblank và unique trong page, dùng ổn định khi mapper tham chiếu cùng
  kết quả. Không tự sort theo x/y làm trộn bảng hay mô tả wrap.
- `score` là engine score trong `[0,1]` hoặc null, không phải field confidence.
  Thiếu score thì null. `ocr_version` phải nhận từ pinned runtime, không tự sinh.

## Transform và unavailable

`inverse_transform` là ma trận homogeneous 3×3 từ **processed pixel-edge** về
**canonical pixel-edge**, nhân column vector `[x_processed,y_processed,1]^T`.
Với kết quả `[u,v,w]`, canonical là `[u/w,v/w]`, sau đó mới normalize theo canonical
width/height. O1.2/O2.1 phải kiểm denominator khác 0, finite/bounds và round-trip;
O1.1 chỉ validate matrix shape/finite/nonsingular, không thực thi preprocess/mapping.

Ví dụ resize 1000×1200 → 500×600: inverse là `diag(2,2,1)`.
Điểm processed `(250,420)` → canonical `(500,840)` → normalized `(0.5,0.7)`.
Ví dụ crop origin `(100,200)` không resize: inverse
`[[1,0,100],[0,1,200],[0,0,1]]`; nếu pipeline dùng pixel-center conventions,
adapter phải encode cả offset cần thiết trong matrix.

Khi không có inverse đáng tin, `geometry_status="unavailable"`, matrix null và
`geometry_reason` nonblank. Block có text vẫn giữ được nhưng `quad=null` cùng
reason. Không thay missing transform bằng identity. Một block không định vị được
cũng dùng dạng này dù mapping chung available. `OcrPage.validate_against` kiểm
canonical dimensions và chặn quads khi page mapping unavailable.

`quad=null` là proposal cho OCR artifact nội bộ. Khi sang extraction result,
mapper phải dùng `source_regions=[]` và review flag thích hợp; schema hiện có không
nhận SourceRegion với quad null. Không tạo bbox/score/value giả. Blank page có thể
có `blocks=[]` sau engine thực chạy; OCR engine fail không được giả thành blank.

## Admission và decode/render limits cần review

Theo [scope](../specs/scope.md), chỉ JPEG/PNG hoặc PDF không mã hóa một trang;
profile dự kiến **20 MiB = 20,971,520 bytes**, canonical ≤20,000,000 pixels,
total job deadline 180s. Đây là target chưa benchmark, không là số đo.

Backend admission kiểm streaming bytes/signature/profile và reject ngoài scope;
Python decode/render kiểm lại file bytes/hash, page count, dimensions/pixel product
trước cấp phát lớn. Không cắt trang/rows âm thầm. `ImageInfo` chỉ kiểm dimensions
positive, không thay byte/pixel/decoder checks của O1.2 hay Java admission.

Backend/AI-2 cần thống nhất thêm render DPI, decode/render timeout và bounds cho
intermediate buffers/processed pixels sau spike. 200 DPI trong snapshot v1 chỉ là
đề xuất cũ; chưa khóa tại đây. Python dùng remaining job budget theo protocol,
không reset deadline. Caller không cung cấp arbitrary local path/URL.

## Consumer review và phạm vi kiểm chứng

- Backend: xác nhận canonical dimensions/page, quad winding/anchor và pixel-edge
  convention; chuyển approved proposal thành neutral schema/Java DTO trong B1.2.
- AI-2: xác nhận PreparedPage/OcrPage, block order/IDs và unavailable; chọn runtime
  engine versions/attempt assets trong M2.3, không đưa DB/business logic vào types.
- Data: cung cấp D1 samples/gold/transcripts/regions để kiểm orientation và overlay.

Fixture O1.1 là metadata giả, không có canonical/OCR image bytes hoặc score đã đo.
Chưa có xác nhận consumer, D1 samples hoặc viewer integration; engine O1.3 có evidence bên dưới. Chưa nghiệm
thu ở mức team. Contract tests không phải Draft2020-12 compiler hoặc Java parity.

## Loader O1.2

[`pipeline/preprocess.py`](../src/vietdoc/pipeline/preprocess.py) có `load_document(bytes)`:
PNG/JPEG qua Pillow, PDF một trang qua PDFium; không lấy text layer PDF làm OCR.
Canonical luôn RGB, EXIF orientation/PDF rotation đã áp dụng; alpha composite nền
trắng, loại metadata orientation để không xoay hai lần. Processed chỉ resize xuống,
giữ aspect ratio, matrix dùng dimensions sau làm tròn. Chưa deskew/crop/auto-rotate
ảnh không có EXIF; các bước đó cần baseline và geometry tests riêng.

Extra `ai1` pin Pillow 12.0.0 và pypdfium2 5.14.0. Defaults ban đầu: 20 MiB,
20 MP, processed long edge 2000 px, PDF 200 DPI, stage timeout 15s; DPI/resize/timeout
cần consumer review và benchmark trên D1. Mỗi decode/render chạy trong subprocess,
timeout lấy min(stage cap, remaining job budget), quá hạn kill và reap child.
Pixel caps kiểm trước raster decode/PDF render và kiểm lại output; chưa có OS-level
memory quota, không bảo đảm cap mọi allocation nội bộ của native decoder.

`LoadedPage` trả hai PIL images, PreparedPage và input hash; dùng context manager
hoặc `close()` để giải phóng. Đây là memory output, không ghi artifact/storage/business
DB. AI-2 service sẽ serialize vào attempt assets, Backend promote verified copies.
Transcript nếu có dùng để đối chiếu OCR về sau, không được dùng để điền prediction.

Tests thực decode pixels, vị trí vùng màu qua 8 EXIF tags, PDF rotation, resize,
hash/byte/pixel caps và timeout. PDF encryption guard chỉ có native-error injection,
chưa file encrypted thật. Loader tests riêng không chứng minh OCR quality; native smoke ở phần O1.3 bên dưới.

Tham khảo API đã đối chiếu: [Pillow EXIF transpose](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html),
[PDFium rendering/lifecycle](https://pypdfium2.readthedocs.io/en/stable/python_api.html),
[PDFium encryption indicator](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdfview.h).

## OCR O1.3

`pipeline/ocr/paddle_adapter.py` có `VietnameseOcrEngine.load/recognize/close`,
`provision_models` (setup explicit), CLI và `draw_overlay`. `OcrPort` ở package
`ocr/__init__.py`; không tạo thêm port/manifest/report files rời trong source.
AI-2 vẫn owns FastAPI/service wiring/readiness/hard timeout của native OCR.

### Candidate và cấu hình đã kiểm chứng

Latin PP-OCRv5 recognizer thử đầu đọc sai `Tổng tiền` thành `Tng tin`; character
dictionary tải về thiếu `ổ`, `ề`. Không dùng candidate đó cho output chính.
Giữ **PP-OCRv5_mobile_det** làm detector và dùng **Tesseract LSTM `vie`** cho từng
crop do detector tìm được. CropByPolys rectifies crop cho recognition, còn source
quad luôn giữ ở processed image rồi map về canonical. Không sinh grid hay dùng
transcript để sửa prediction.

- PaddleOCR 3.3.2, PaddleX 3.3.13, PaddlePaddle 3.3.1, NumPy 2.2.6.
- OpenCV contrib 4.10.0.84, Shapely 2.2.0, Pyclipper 1.4.0.
- Tesserocr 2.12.0, native Tesseract 5.5.3; `vie.traineddata` từ tessdata_best
  revision `e12c65a915945e4c28e237a9b52bc4a8f39a0cec`.
- Detector CPU, 4 threads, MKLDNN off, detection limit side 960 (`max`). Recognizer
  LSTM_ONLY/SINGLE_LINE, giữ Unicode, chỉ strip whitespace đầu/cuối block.
- Model set `ppocrv5-det-tess-vie-50446e5d01ac-b6b49293d95d`. Constants `MODELS`/
  `RUNTIME_VERSIONS` chứa exact file set và full SHA-256. Detector archive SHA-256
  `50446e5d01ac2a73d5319c89513281f6578414c888c602f9af13f93feefffc58`; traineddata
  SHA-256 `b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45`.
  Đây là hash pin bytes đã tải/smoke, không claim upstream published checksums.
- `load()` verify versions/native/file set/hash, reject symlink/junction model files;
  không tải weights. Setup downloader dùng fixed official URLs, byte cap, checksum,
  exact archive member allowlist và staged publish; không extractall/overwrite model lỗi.

Nguồn: [PaddleOCR v3.3.2 multilingual](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.3.2/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md),
[tessdata_best revision](https://github.com/tesseract-ocr/tessdata_best/tree/e12c65a915945e4c28e237a9b52bc4a8f39a0cec),
[tesserocr](https://github.com/sirfz/tesserocr). API adapter đã đối chiếu với source
package versions thực đang cài; không suy ra hỗ trợ dấu chỉ từ bảng language codes.

### Output engine thật cho consumer

Cặp fixture nhỏ đã audit nội dung giả:
[`ocr-vietnamese-source.png`](../tests/fixtures/ocr-vietnamese-source.png) và
[`ocr-vietnamese-observed.json`](../tests/fixtures/ocr-vietnamese-observed.json).
PNG 800×400 RGB; input SHA-256
`2ce95a4decc84a125280edeb6a92f12469340aa911848cb14848d81839b9e595`.
JSON là **observed engine snapshot để parse/highlight**, không phải train/evaluation
gold. Nội dung trang được tạo trước khi OCR: `Tổng tiền`, `80.000`; không có PII.

| Block ID | Text thực | Quad canonical, pixel edges | Score |
|---|---|---|---|
| p0-b0001 | Tổng tiền | (60,206), (228,206), (228,266), (60,266) | 0.93 |
| p0-b0002 | 80.000 | (472,214), (596,214), (596,260), (472,260) | 0.96 |

JSON lưu quad normalized: divide x by800, y by400. `score` là recognizer
`MeanTextConf()/100`; không phải detector score hay field correctness probability.
IDs stable trong cùng immutable result/order, không cam kết stable qua reruns.
`ocr_version` ghi model set, versions và score method. Đã nhìn overlay trên đúng
canonical; nhãn/số tiền có hai source regions riêng. CLI với transcript cố tình sai
vẫn trả hai text/regions này, comparison=false; không điền prediction từ reference.

### Commands và evidence local — 2026-10-24

Setup/run từ [Python README](../src/vietdoc/README.md#chạy-ocr-ai-1), native test env
và commands ở [tests README](../tests/README.md). Không cần hardcode đường dẫn D
của máy này trong source; model/cache/output roots do người vận hành chọn.

Đã chạy `pip check` (no broken requirements), 18 contract tests và 46 pipeline
tests (loader + adapter + native). Native test chứa **20 case từ một trang giả**:
PNG/JPEG×8 EXIF tags, PDF rotations0/90, blank và corrupt. 19 input hợp lệ có OCR
output parse được, text đúng expected (blank=[]); corrupt trả INPUT_INVALID, không
fake OCR success. Tất cả 36 text boxes qua 18 case có dấu/số đều overlap ink bbox
độc lập, min IoU=0.5014, threshold smoke0.45. Resize800→400 rồi map về800; tests
khác kiểm inverse rotate/reflection/unavailable và reject out-of-bounds/self-crossing.

Hardware: Windows11 x64, Python3.13.7, i7-12700H14cores/20logical, RAM15.63GiB.
Run native cuối: first model load trong process **2.649s**, warm inference median
**0.139s**, max **0.166s** (19 calls, gồm blank; chưa tính decode/render).
Process RSS **320.89MiB**, peak RSS **351.27MiB**, private commit **905.55MiB**.
Không tính child decoder vào peak này. Lần process đầu trước đó load8.65s; OS caches
không được reset, không gọi đây là benchmark cold-cache hoặc latency D1/production.

Output đầy đủ ở ignored `artifacts/evaluation/o1_3-verified/report.json` và từng case;
CLI example ở `artifacts/evaluation/o1_3-example/` có canonical/overlay/OCR/run.
Chỉ cặp fixture nhỏ trên được commit, không commit 20 bộ ảnh/outputs hoặc weights.

### Giới hạn và handoff

- Chưa có D1 documents/transcript/region gold, CER/WER/per-type metrics, Data evaluator
  hoặc AI-2/Backend consumer acceptance; chưa đóng G0 hay tuyên bố chất lượng receipt/invoice.
- Snapshot O1.3 dùng SortQuadBoxes native (10px tolerance). O2.1 bên dưới thay sorter;
  chưa semantic table grouping và không bảo đảm word-level boxes.
- Chưa auto-detect orientation cho raster không có EXIF, deskew/contrast nâng cao,
  evidence matching, Java viewer/API hoặc extraction. Những phần đó thuộc increment sau.
- OCR budget kiểm trước/sau native call, giữ slot đến khi native thực sự xong;
  không claim hard native cancellation. AI-2 phải isolate/timebox khi compose M2.3.
- Blank detection thực có blocks=[]; native failure/invalid output không biến thành
  blank. Một detected crop không đọc được text hợp lệ hiện làm output invalid,
  chưa silent-drop block. Score không phải calibrated field confidence.
- Shared schemas và ADR status vẫn giữ nguyên Proposed; backend cần review wire contract.

## Geometry và reading order O2.1 — 2026-10-24

[`geometry.py`](../src/vietdoc/pipeline/geometry.py) chứa mapping pixel-edge thuần
Python, dùng cùng convention homogeneous column vectors của PreparedPage. Adapter
map từng detected quad về canonical, normalize theo đúng dimensions, sửa winding
khi phản chiếu; không clamp tọa độ lỗi hoặc tự điền box khi mapping unavailable.
Projection reject singular matrix, undefined denominator và polygon cắt projective
horizon. Ngưỡng denominator tương đối giữ kết quả khi nhân toàn matrix với scalar.

Repro sorter cũ: hai cột x=10/70, hai dòng y=10/17, vùng cao4px. Ở scale1, native
sorter trả trái-dòng1 → trái-dòng2 → phải-dòng1 → phải-dòng2; scale3 lại đúng.
Sorter mới dùng overlap/độ cao tương đối và top/center alignment. Ô ngắn cùng mép
trên làm row anchor để ô cao không nối nhiều dòng. Trong dòng sắp trái→phải, giữ
mọi vùng riêng, gồm mô tả xuống dòng và số tiền lặp. Đây là geometric row order,
không phải semantic column traversal hay association mô tả với sản phẩm.

Order được xác định trên **processed frame** đã thẳng để OCR. Khi canonical xoay
90°/180° hoặc phản chiếu, giữ nguyên bộ text/quad/score theo thứ tự đó, không sort
lại theo trục viewer. Block IDs đánh theo output order trong immutable result.
Version mới có `cpu4.v2;pixel-edge-projective-relative-rows.v1`; model/package pins
không đổi. Fixture observed O1.3 vẫn giữ version cũ, không sửa lịch sử prediction.

Kiểm tra thực đã chạy:

- 18 OCR contract tests và 55 pipeline tests đều pass, có bật native OCR.
- Round-trip identity/resize/crop/90°/17°/reflection/perspective so với NumPy inverse
  độc lập: tolerance `1e-7` pixel. Matrix scales ±1e-15/±1e15 cho cùng projection.
- Native geometry smoke: **6 biến thể từ một trang giả**, 7 vùng có dấu/số tiền,
  mô tả `loại nhỏ` riêng: identity, resize, crop+resize, 90°/180°+resize, reflection.
  Cả 42 regions đúng reference text và đúng row order; min ink-bbox IoU=0.4445,
  ink coverage=1.0. Ink masks tạo từ text/font trước OCR, rồi transpose bằng Pillow,
  độc lập với helper mapping; ngưỡng smoke IoU≥0.40 và ink coverage≥0.95.
- 20 format/EXIF/PDF/blank/corrupt cases O1.3 vẫn pass với sorter mới. Hai bộ smoke
  không phải 26 D1 documents, chưa thay evaluator/CER/WER hay consumer acceptance.

Commands/env ở [tests README](../tests/README.md). Lần kiểm cuối lưu local ignored
`artifacts/evaluation/o2_1-geometry-verified/report.json` và mỗi case có canonical,
overlay, OCR JSON; format smoke ở `artifacts/evaluation/o2_1-formats-verified/`.
Các outputs này được sinh khi chạy, không đưa toàn bộ ảnh vào Git.

Native geometry test chủ động dựng LoadedPage với inverse crop/rotate/reflection
đã biết để kiểm mapping về viewer pixels. Production loader vẫn chỉ EXIF/PDF
orientation + resize; chưa auto-deskew/crop/orientation cho raster không có EXIF.
AI-2/Backend cần review version và kiểm consumer overlay trước khi chốt O2.1.

## Source evidence O4.1a — exact raw text/context

[`evidence.py`](../src/vietdoc/pipeline/evidence.py) nhận `OcrPage` và
`EvidenceRequest(path, raw_value, context_block_ids=(), label_text=None)` từ AI-2.
`raw_value` là text nguồn trước business normalization, ví dụ `80.000`; không
truyền normalized decimal `80000` rồi yêu cầu mapper suy ra cách viết trên ảnh.
Increment đầu dùng version `exact-raw-context-spans.v1`; phiên bản hiện tại ở
O4.1b bên dưới. Helper thuần Python, không load model/ghi DB.

```python
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence

# IDs từ observed fixture; consumer xác định context từ extraction của mình.
request = EvidenceRequest(
    "/total_amount", "80.000", ("p0-b0001", "p0-b0002"), "Tổng tiền",
)
match = match_evidence(ocr_page, request)
field_metadata = match.to_field_metadata()
```

- So complete blocks, NFC/whitespace/case; giữ dấu, số và punctuation. Có thể nối
  tối đa4 blocks liên tiếp trong context theo page order; không sửa OCR bằng value.
- Số tiền xuất hiện nhiều nơi trả `ambiguous`, candidate IDs và source_regions rỗng.
  Consumer cấp context IDs đúng row/field để phân biệt. Label chỉ xác nhận xuất
  hiện duy nhất trong scope, chưa tự thiết lập quan hệ label→value bằng khoảng cách.
- Mô tả xuống dòng cần context chứa các description blocks; mỗi block giữ region
  riêng. Không union rectangles qua dòng/cột. Context IDs không tồn tại/duplicate
  là lỗi input; thứ tự hint IDs không thay page reading order.
- `matched` giữ nguyên canonical quads/block IDs và single-block engine score.
  Multi-block ocr_score=null, confidence/confidence_method luôn null để AI-2 xử lý.
- Không match, thiếu geometry/context hoặc thiếu prediction trả source_regions=[]
  cùng SOURCE_* review flags. raw_value=null vẫn value_origin=prediction; không
  suy diễn field absent. Candidate IDs nằm trong internal EvidenceMatch, không
  thêm key ngoài schema vào FieldMetadata hoặc thay business payload.

Đã chạy **18 contract + 70 pipeline tests**, gồm15 evidence unit checks và native
OCR. Native kiểm `/total_amount` ở cả6 transform cases: region bằng đúng source
quad của `40.000`, cùng block ID/score sau xoay/crop/resize. Output local ignored
ở `artifacts/evaluation/o4_1a-evidence-versioned/`: report pin evidence_version,
có total_evidence và từng
case có `total-overlay.png` chỉ highlight vùng số tiền đã chọn. Đã xem overlay.
Đối chiếu Draft2020-12 FieldMetadata từ shared schema:6 native outputs +5 trạng
thái negative/unavailable đều valid (checker Python có sẵn, không thêm dependency).

Đây là matcher increment đầu, chưa hoàn tất O4.1: chưa fuzzy/substring alignment,
tự chọn row context/semantic geometry, extraction pipeline wiring, Java viewer
integration hoặc AI-2/Backend acceptance. O2.2 vẫn cần Data D1 transcripts/regions
và evaluator D3; smoke synthetic không thay baseline chất lượng theo từng type.

## Source evidence O4.1b — label và row geometry

`match_evidence(..., prepared=loaded.metadata)` bổ sung context theo vị trí cho
raw values lặp. Không truyền PreparedPage thì giữ hành vi exact/context O4.1a.
Version hiện tại `exact-raw-label-row-spans.v2`; shared schema không đổi.

```python
request = EvidenceRequest("/total_amount", "40.000", label_text="Tổng tiền")
match = match_evidence(ocr_page, request, prepared=loaded.metadata)
field_metadata = match.to_field_metadata()
```

Nhãn phải match duy nhất một complete OCR block. Mapper đảo inverse transform để
đưa quads canonical trở lại processed pixel-edge frame; kiểm đúng dimensions,
projection và bounds. Sau đó chỉ chọn khi **đúng một candidate bên phải nhãn,
cùng row**: vertical overlap≥nửa độ cao nhỏ hơn, center delta≤nửa độ cao nhỏ hơn.
Không chọn nearest candidate khi có hai số cùng row. Context IDs vẫn có thể giới
hạn scope trước; mọi candidate ID ban đầu giữ trong internal diagnostics.

Thiếu label/geometry hoặc nhiều candidates còn hợp lệ vẫn trả uncertainty/flags;
unknown geometry không bị loại như thể chắc chắn nằm ở row khác. Quads output
giữ nguyên canonical coordinates, không dùng processed coordinates để highlight.
Row rule là heuristic cho label→value bên phải, chưa hỗ trợ mọi layout/table,
value bên dưới nhãn, substring hoặc fuzzy OCR. Confidence vẫn null; caller phải
gắn đúng page/metadata cùng run, dimensions không chứng minh asset identity.

Đã chạy **18 contract +77 pipeline tests** (21 evidence unit checks; native bật).
Inverse projective helper đối chiếu NumPy inverse và tolerance `1e-7` pixel, gồm
perspective/scalar scales. Native có6 geometry-base cases giữ nguyên mẫu7 regions
và6 repeated-value cases (mẫu9 regions), cả hai dùng PNG source giả cùng font.
Hai số `40.000` ở Tổng tiền/Đã trả được đọc đúng, chỉ chọn block tổng tiền, giữ
quad/ID/score sau resize/crop/90°/180°/reflection. 12 FieldMetadata outputs đã
validate với shared Draft2020-12 schema; chưa có AI-2/Java viewer acceptance.

Output local ignored: `artifacts/evaluation/o4_1b-label-row-verified/`, mỗi family
có report/version/transform/candidate IDs và canonical/OCR/total-overlay images.
Geometry-base min IoU=0.4445, ink coverage=1.0. Mẫu số lặp có **4/6 cases IoU<0.40**,
min=0.3878 do detector box rộng, ink coverage vẫn1.0; report ghi indices của các
boxes đó. Bài số lặp kiểm source selection/coverage, không chứng minh detector
đạt tight-box threshold hay có cải thiện OCR quality. Ngưỡng0.40 trên geometry
regression cũ giữ nguyên; chưa tune detector theo sample này. D1/D3 baseline còn thiếu.

## Local review report và entrypoint bàn giao

CLI hiện xuất thêm `preview.html` cùng canonical/overlay/OCR/run. File chứa PNG
canonical và OCR JSON/transcript; chọn vùng để xem text, ID, engine score, quad
pixel/normalized, hoặc bật/tắt/tất cả vùng. Dùng trình duyệt ngoài VS Code để tránh
lỗi vscode-media-preview. Không tải tài nguyên ngoài/server; OCR/transcript được
escape JSON và đưa vào DOM bằng textContent, không dùng innerHTML.

`pipeline.ocr.recognize_document(data, engine, limits=..., remaining_budget_ms=...,
expected_sha256=...)` dùng engine do service đã load; không tải model hoặc sở hữu
engine lifecycle. Context trả loaded canonical/processed images và immutable
OcrPage; cả hai ảnh đóng khi thoát, kể cả lỗi OCR/consumer. Một monotonic deadline
cho decode/OCR, `stage.remaining_budget_ms` tính live để consumer chuyển sang stage
sau. Result sai canonical metadata trả typed OUTPUT_INVALID. Stage version
`bounded-preprocess-ocr.v1` được ghi trong local CLI run report.

Usage/config/commands ở [Python README](../src/vietdoc/README.md#chạy-ocr-ai-1).
AI-2 vẫn owns extraction/attempt storage/compute envelope/hard native isolation;
Backend owns verified asset promotion và viewer theo run/revision. Entry point
này không tự trả business result hoặc ghi DB. Caller phải dùng ảnh trong context,
giữ cùng image/run/provenance cho OCR và evidence.

Checks cuối: **18 contract +88 pipeline tests pass**, native OCR bật, `pip check`
không có broken requirements. Có7 stage lifecycle/deadline checks và4 HTML report
checks (embedded pixels/data, blank/unavailable, mismatched image, script escaping).
Native20 format/error cases đi qua entrypoint thật; geometry/evidence giữ12 cases
và report limitation như trên. Kết quả local ở ignored
`artifacts/evaluation/ai1-handoff-formats/` và `ai1-handoff-geometry/`.
Browser interaction chưa được kiểm tự động: Computer Use dừng do chưa hỗ trợ
URL-policy enforcement trên Cốc Cốc/Windows; in-app browser từ chối file:// theo
URL security policy. Không chuyển sang server/protocol khác để né policy. Đã
kiểm `node --check` và bundle CLI có ảnh nhúng/JSON/dimensions/version khớp bytes
canonical, nhưng HTML parsing/data tests không được
gọi là browser E2E hoặc Java viewer acceptance.
