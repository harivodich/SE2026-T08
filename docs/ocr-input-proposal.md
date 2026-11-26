# AI-1 — OCR/page input, geometry và loader

**Proposed**, dành cho AI-1, Backend và AI-2 review. Types chạy được ở
[`contracts/ocr.py`](../src/vietdoc/contracts/ocr.py), ví dụ giả ở
[`ocr-page-proposal.json`](../tests/fixtures/ocr-page-proposal.json).
Đây chưa là shared JSON Schema được chấp nhận. Backend vẫn owns neutral schemas/
Java DTO; AI-2 owns compute envelope. Không thay [compute protocol](../specs/contracts/compute-api.md),
[result schema](../specs/contracts/extraction-result.schema.json) hay ADR status.

## Trạng thái bàn giao hiện tại — 2026-10-25

- Có loader/OCR pretrained/geometry/evidence và local HTML review report chạy được.
  AI-2 có entrypoint `recognize_document`; xem hướng dẫn ở Python README bên dưới.
- Versions hiện tại: geometry `pixel-edge-projective-relative-rows.v3`, evidence
  `exact-raw-scoped-spans-occurrence-guard.v4`; OCR có `cpu4.cooperative.v3`.
  Các observed snapshots cũ giữ version lịch sử.
- Đã sửa R01/R02/R03/R05/R06 của strict review PR4 ở increment dưới. R04 còn mở:
  người dùng xác nhận chưa có AI-2/Backend approval cho partial/unreadable policy.
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
  Source detector quads và canonical normalized input được kiểm bounds nghiêm.
  Riêng kết quả phép biến đổi có thể snap về biên nếu lệch ≤16 ULP theo image
  extent (dưới6e-8 pixel trong profile20MP); ngoài mức sai số máy này vẫn reject.
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
Contract và geometry dùng chung validator: entries finite float64, chia cho
max absolute entry trước determinant/projection. Determinant của matrix sau
normalization phải còn finite/nonzero trong float64; matrices quá ill-conditioned
ngoài miền đó vẫn reject. Global scales như ±1e-200/±1e200 không làm identity
bị reject; metadata giữ matrix gốc, không tự đổi JSON transform.

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
raw values lặp. O4.1b trước đây giữ text/context behavior khi thiếu PreparedPage;
R05 hiện fail closed khi có label_text mà thiếu PreparedPage.
Increment O4.1b dùng `exact-raw-label-row-spans.v2`, fix đầu dùng v3; R01/R02/R05
hiện dùng `exact-raw-scoped-spans-occurrence-guard.v4`.
Shared schema không đổi.

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

Checks cuối: **18 contract +96 pipeline tests pass**, native OCR bật, `pip check`
không có broken requirements. Có7 stage lifecycle/deadline checks và4 HTML report
checks (embedded pixels/data, blank/unavailable, mismatched image, script escaping).
Native20 format/error cases đi qua entrypoint thật; geometry/evidence giữ12 cases
và report limitation như trên. Kết quả local ở ignored
`artifacts/evaluation/ai1-fix-regression-formats/` và `ai1-fix-regression-geometry/`.
Browser interaction chưa được kiểm tự động: Computer Use dừng do chưa hỗ trợ
URL-policy enforcement trên Cốc Cốc/Windows; in-app browser từ chối file:// theo
URL security policy. Không chuyển sang server/protocol khác để né policy. Đã
kiểm `node --check` và bundle CLI có ảnh nhúng/JSON/dimensions/version khớp bytes
canonical, nhưng HTML parsing/data tests không được
gọi là browser E2E hoặc Java viewer acceptance.

### Regression fixes sau review

- Evidence kiểm label/row geometry khi caller cấp PreparedPage + label_text,
  kể cả chỉ có một text candidate. Ví dụ line total45.000 nhưng document total60.000:
  request total45.000 không được chọn vùng dòng hàng; source_regions rỗng + flag.
  Unique candidate thiếu geometry của nhãn, nằm sai dòng hoặc sai phía nhãn
  cũng không matched. Match đúng vẫn giữ raw text, quad/ID/score ban đầu.
- Quad sát mép sau resize2007→2000 từng bị reject vì `2007.0000000000002`;
  mapping/round-trip hiện xử lý sai số máy sát biên cho resize/rotate/reflection.
  Input ngoài bounds dù1 ULP và projection lệch thật1e-7px vẫn bị reject.
- Đã quan sát regression tests fail trên code trước fix, pass sau fix. Thêm
  adapter contract case cho detector quad sát mép; không sửa fixture OCR lịch sử
  hoặc nới threshold IoU. Sweep4500 geometry cases từng phát hiện34 forward và431
  round-trip failures; sau fix cả4500 đều qua. Đây là geometry checks, không D1 metrics.

## Phản hồi strict review PR4 — 2026-10-25

Review áp dụng cho head `26bd4e10172adbae8f16b3a6f15ed0ed058cd91c`, branch
`feature/AI1_preprocess_ocr`. Giữ Proposed và shared schemas hiện tại; không nhận
nghiệm thu consumer, CI, Data hay xử lý base develop thay Lead.

| Mục | Thay đổi ở increment này |
|---|---|
| R01 | Kiểm whole-token occurrences trong block ghép trước khi chọn source. Exact `45.000` ở dòng hàng + `Tổng tiền 45.000` không còn false unique; giữ candidates, empty regions và `SOURCE_OCCURRENCE_UNRESOLVED`. Không tạo substring bbox. |
| R02 | Span 2–4 blocks chỉ publish khi có explicit context IDs do consumer xác định cho cùng field/item. Không context thì `SOURCE_SPAN_CONTEXT_REQUIRED`; wrapped descriptions có scope vẫn hợp lệ, dùng page order. |
| R03 | Truyền một absolute monotonic deadline từ engine xuống composite predictor; kiểm trước detector/crop/recognition và trước publication. Không bắt đầu call tiếp sau deadline; Clear và slot release vẫn đúng. |
| R04 | Chưa sửa runtime policy, chưa đóng finding. Mixed empty crop hiện vẫn OUTPUT_INVALID; cần AI-2/Backend duyệt đề xuất dưới. |
| R05 | Label context thiếu PreparedPage trả uncertainty + `SOURCE_CONTEXT_GEOMETRY_UNAVAILABLE`, kể cả unique candidate/explicit IDs. Consumer calls và tests được cập nhật để truyền đúng metadata. |
| R06 | Contract/geometry dùng chung normalized matrix validation và normalized projection; giữ raw matrix metadata, không nới bounds. |

Occurrence guard tokenize NFC/casefold text, giữ dotted/comma-separated word/number
tokens: `5.000` không là occurrence của `45.000`, `15.000`, `5.000.000` hay
`5.0000`. Dấu phân cách như `:`/ngoặc không làm mất occurrence. Chỉ dùng token
occurrence để **từ chối chọn nguồn**, không dùng làm positive substring match.
Nếu còn occurrence trong scope, label-row heuristic cũng không tự loại block
ghép dựa trên bbox lớn; consumer có thể cấp scope đủ hẹp để phân biệt. Đây không
là parser tiền tệ/fuzzy alignment hoặc source precision baseline.

Test cũ cho bốn từ trên bốn dòng đã bỏ giả định “page adjacency chứng minh cùng
description” theo yêu cầu R02: không context phải uncertain, cùng input có explicit
item scope vẫn matched. Các positive label tests bổ sung PreparedPage theo R05;
negative wrong-row/wrong-side/missing geometry, repeated amounts và raw text vẫn giữ.

R03 fake-clock diagnostic budget50ms, native-double100ms trước fix bắt đầu3 calls
ở0/100/200ms; sau fix chỉ call đầu bắt đầu. Detector/crop/SetImage dùng hết budget
cũng chặn bước tiếp; timeout tại boundary, native exception và conversion/publication
cleanup có tests. Không khẳng định native call đang chạy bị dừng ngay, process
isolation, OS memory quota hay service recovery đã có. Những phần đó vẫn ở G4/AI-2.

### R04 — đề xuất partial/unreadable để AI-2 và Backend duyệt

**Trạng thái tại review 25/10: chưa implemented/accepted.** Xem increment 02/11 ở cuối
file cho implementation opt-in v2; consumer acceptance vẫn pending. Không đổi `OcrBlock.text` để chứa chuỗi rỗng, không
thêm fields vào shared result schema hoặc tự coi policy đã được duyệt.

Đề xuất mở rộng **OCR artifact nội bộ** ở version mới:

| Phần | Policy đề xuất |
|---|---|
| `blocks` | Chỉ recognized blocks có text nonblank; giữ nguyên text/ID/quad/engine score. |
| `unreadable_regions` | Mỗi detection rỗng/whitespace có `region_id`, canonical `quad` hoặc null + `geometry_reason`, engine `score` hoặc null và `reason=EMPTY_RECOGNITION`; không text giả. ID dùng cùng sequence detection với blocks, unique toàn page. |
| `recognition_status` | `complete` nếu mọi detection đọc được (kể cả không detect vùng nào), `partial` nếu có cả recognized/unreadable, `unreadable` nếu có detections nhưng tất cả rỗng. |
| `review_flags` | Có `OCR_UNREADABLE_REGIONS` cho partial/unreadable. Count được tính từ arrays, không lấy text rỗng làm blank-page success. |
| Invalid/runtime errors | Nonfinite/malformed quad, score, native exception, OOM/timeout vẫn typed error; không chuyển chúng thành unreadable crop để tiếp tục. |
| Downstream | AI-2 truyền page diagnostic/flags qua extraction/evidence; text không tìm thấy trên partial page không chứng minh field absent. AI-2/Backend quyết định field warning/blocker; OCR score không thành confidence. |

Ví dụ mixed page: `blocks=[p0-b0001]`, `unreadable_regions=[p0-b0002]`, status partial,
flag OCR_UNREADABLE_REGIONS. Không renumber block1/3 thành1/2 khi detection2 rỗng;
canonical identity/attempt provenance do G3 giữ như cũ. Geometry unavailable vẫn
giữ reason, không đoán box. Đây là shape đề nghị, chưa là API/service response mới.

Sau approval: thêm Python types/adapter/preview propagation và các regression
mixed valid+empty/whitespace, all unreadable, no detections, invalid quad/score,
native exception/timeout, metadata serialization và evidence missing-vs-absent.
Backend owns neutral schema/Java DTO nếu boundary này được đưa lên wire; cần
consumer fixtures/parity và severity acceptance trước khi đánh dấu R04 hoàn tất.

G1/G2/G3/G4/G5/G6 vẫn giữ owner/gate theo strict review. D1/D3 tiếp tục đợi Data;
không tạo dataset/evaluator hoặc tự merge branches để vượt acceptance gate.

### Kiểm chứng increment này

- **114 pipeline +19 OCR contract tests pass**, native OCR bật, không skip/failure/error.
  Cả10 package versions trong extra ai1-ocr trùng pins; native Tesseract5.5.3 được
  loader kiểm; `pip check` không broken requirements. Python3.13.7/Windows11/CPU4.
- Regression R01/R02/R03/R05/R06 đã tái hiện lỗi trên source trước sửa. Có một
  MemoryError của môi trường khi hash tiny fixture trong lượt red đầu; focused
  rerun và toàn suite native sau đó đều pass, không thay cấu hình Windows.
- Native20 format/error cases vẫn từ **một trang giả**; hai geometry families
  có6 transforms/family. Source selection giữ đúng quad/ID/score; geometry-base
  minIoU0.4445, repeated-values minIoU0.3878 và4/6 cases dưới0.40 như hạn chế cũ.
  Ink coverage1.0 không được đổi thành claim tight-box quality đạt chuẩn.
- **23 FieldMetadata outputs** (11 diagnostic +12 native) valid shared Draft2020-12,
  dùng jsonschema đã có, không thêm dependency. Schema-valid không chứng minh
  semantic source correctness; các regression còn kiểm selected regions/flags.
- Compile8 Python files đã đổi, diff whitespace và secret-pattern scan đều qua.
  Shared schemas/ADR/Java không đổi. Không chạy browser/Java/provider-service E2E,
  Data metrics hoặc native hang/OOM recovery; không claim các gate này hoàn tất.

Outputs ignored: `artifacts/evaluation/pr4-review-fixes-summary.json` (source hashes,
diagnostics, versions và giới hạn), `pr4-review-fixes-formats/` (actual OCR JSON/ảnh),
`pr4-review-fixes-geometry/` (reports/overlays/evidence). Không ghi đè observed fixture
lịch sử hay thêm report file tracked riêng. Commands: native env/model root như
[tests README](../tests/README.md), rồi:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit/pipeline -p "test_*.py" -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/contract -p test_ocr_contracts.py
.\.venv\Scripts\python.exe -B -m pip check
git diff --check
```

Đã recheck remote: feature head vẫn26bd4e1; develop đã lên4ed7302. Triple-dot diff
với feature HEAD vẫn165 paths kế thừa/increment như review snapshot; Lead tiếp tục
xử lý base. Không tự rebase/merge, commit/push hoặc chuyển Draft→Ready ở lượt fix này.

## Bàn giao O-N — 2026-11-02

Increment theo `next-ai1-2026-10-30.md`, làm trên `feature/AI1_preprocess_ocr`.
Đã sync develop `729be6f` bằng merge `862ce5a`; kiểm tra và xử lý 17 conflicts
theo từng phần, giữ Data extra/package-data/CI và AI-1 pins riêng. Không push
main/develop. Các số liệu và trạng thái phía trên là lịch sử, không kết quả lượt này.

| Mục | Kết quả và gate còn lại |
|---|---|
| O-N1/R01 | Guard v5 quét token occurrence qua block boundaries và currency attached; numeric separators/digits giữ nguyên. Unresolved occurrence chỉ gây abstention, không tạo substring box. Không đếm chính exact wrapped span lần nữa; explicit item scope giữ page order. Có regression IDs/flags cho cả hai repro Lead nêu. |
| O-N1/R04 | Internal artifact v2, adapter opt-in, preview/overlay/evidence propagation và golden migration cases đã có. Default v1 giữ behavior cũ đến khi AI-2/Backend nhận version/semantics; R04 **chưa đóng**. Invalid shape/geometry/score/native exception/OOM/timeout vẫn typed error. |
| O-N2 | Native receipt03/invoice04 đều chạy, parse local, có canonical/overlay/hash/PreparedPage/OcrPage. Helper offline export trong `with`, caller giữ lifecycle; không ghi production attempt storage. Actual consumer acceptance chờ AI-2. |
| O-N3 | Independent PNG identity oracle `d1-png-identity-pixel-edge.v1`, kiểm decoded RGB pixels/dimensions và sidecar hashes; tests map mọi renderer ink rect qua resize thực1154×2000 về canonical1500×2600. Fixture có matched/ambiguous/unavailable; không biến renderer box thành OCR gold hoặc neutral schema authority. |
| O-N4 | Chưa có accepted D3 evaluator/scope-order để chạy baseline; chưa tune preprocessing hoặc công bố CER/WER. |
| O-N5 | Đo native repeated-call smoke và D1 latency/RSS, giữ cap20MP/CPU4/deadline/Clear/slot. Native hang/isolation/restart, admission toàn pipeline và actual encrypted-PDF E2E vẫn chưa kiểm; thuộc integration với AI-2. |

### Consumer semantics của internal artifact v2

`blocks` vẫn nonblank, không sửa OCR text bằng transcript. `unreadable_regions`
giữ detection ID chung sequence, quad canonical hoặc null + geometry_reason, score
engine nullable, reason `EMPTY_RECOGNITION`. Mixed → `partial`, toàn detection rỗng
→ `unreadable`, không detection → `complete` với hai arrays rỗng. Có unreadable thì
`OCR_UNREADABLE_REGIONS`; evidence thêm `SOURCE_OCR_INCOMPLETE`. Unscoped unique
recognized candidate trên partial page cũng abstain; explicit scope có thể chọn
recognized source nhưng vẫn truyền flags. Missing/null là prediction thiếu evidence,
không là `absent`, không tự điền value/bbox/confidence. Backend vẫn phải enforce
blocker khi required field thiếu; chưa có actual consumer wiring chứng minh gate đó.

v1 deserialize/serialize giữ đúng shape cũ; v2 validate status/flags theo arrays,
reject metadata mâu thuẫn và trùng IDs. Migrate complete v1 bằng
`dataclasses.replace(page, artifact_version=2)`; không downgrade v2 partial về v1
và bỏ diagnostic. `OcrBlock.text`/shared JSON schemas/Java DTO không đổi. Fixture
`tests/fixtures/ocr-artifact-v2.json` là golden consumer proposal, không native gold.

### Native D1 và geometry provenance

Observed bundle tracked: `tests/fixtures/ocr-d1-native-handoff.json` (~60KB, chỉ dữ
liệu hư cấu Data đã cung cấp). Có native blocks/score/quads của hai type, SHA-256
input/canonical encoded PNG/canonical RGB pixels/source/model files, versions,
profile, latency/RSS, 18 unavailable IDs và evidence examples. Canonical PNG được
re-encode bằng Pillow12 nên encoded hash khác input; decoded pixels/dimensions
giống ảnh renderer đã được kiểm độc lập. Renderer-local rectangles dùng oracle
identity có version, không sửa theo OCR. Runtime files/model/env đều ignored.

Manifest D1.2.v2 gồm20 IDs: **2 native attempted, 2 ok, 0 failed, 18 not_run**
`INPUT_ARTIFACT_UNAVAILABLE`. Fallback tiny chỉ bật tường minh và vẫn kiểm exact
manifest hash; 18 missing không được gọi là native attempts. Data cần bàn giao
18 PNG còn lại trước khi claim OCR đủ20. Không chạy generator bằng env AI-1 thay Data.

Receipt giữ các số tiền và dấu chính, nhưng `hộp → nộp`, `SL → sL`; invoice có
`SL → SsL`. Cả hai wrapped descriptions có continuation sau cells số, khác transcript
Data; giữ raw output/order. Invoice lặp `90.000 đ`/`45.000 đ` cần explicit item scope.
Totals lặp trong merged label/value blocks không có substring box. Overlay receipt
đã xem trực tiếp; boxes phủ dòng chữ nhưng có margins. Không coi đây là tight-box
quality acceptance, field correctness hoặc baseline CER/WER.

Cold engine load ở lượt manifest20:2.20s; inference/memory chi tiết từng mẫu trong
bundle, đo Windows11/Python3.13.7/CPU4, processed long edge2000. Format smoke18 lượt
OCR thành công từ một trang synthetic có median0.079s/max0.103s, peak RSS~549MiB,
private~930MiB trong process test cuối. Không là OS quota hoặc cấu hình capacity production.
AI-1 env/model bền trên D `artifacts/models/.venv-ai1` và `artifacts/models/ocr-v1`;
10 direct dependency pins được kiểm riêng, transitive freeze lưu local ignored.

D2 PDF MediaBox1500×2600pt ở200DPI vượt20MP: đã reproduce qua actual loader và
test `PROFILE_EXCEEDED`; chưa rasterize hoặc tăng cap/đổi DPI để lách. Data/Lead
cần chốt render profile có version trước PDF handoff; PNG tiếp tục dùng được.

Commands/helper ở [Python README](../src/vietdoc/README.md#chạy-ocr-ai-1), checks ở
[tests README](../tests/README.md). Local parser/golden tests không thay actual
AI-2 parse result, Backend approval/viewer, Java E2E hoặc shared wire acceptance.

## Checkpoint C/D/E/F/G1 — 2026-11-15

Base đã nhận: `develop@b9bd7f478bb5037e3a14a1ca90375d462497d90f` (PR4,
PR81, PR82 đã merge). Increment này bổ sung regression/oracle và bằng chứng
offline; không đổi loader, engine, shared schema, default long edge2000 hoặc
artifact v1. Các phần lịch sử phía trên giữ nguyên provenance của lần chạy cũ.

### Geometry và PDF profile (C)

- `test_geometry.py`: JPEG thật đủ8 EXIF orientations, original/canonical dimensions
  riêng; canonical301×199 → processed113×75. Hai vùng fixture giữ text, IDs,
  scores, normalized corners và inverse round trip; không là recognition gold.
- `test_preprocess.py`: PDF vector với chữ7pt `80.000`, đủ rotation0/90/180/270.
  Oracle dùng source character boxes + công thức rotation độc lập. Loader thật
  render200DPI ra200×100 hoặc100×200; resize73×36 hoặc36×73. Ink bbox lệch tối đa
  1.5 raster pixels; OCR boundary double giữ text/ID/score/quad và round trip.
- Reject MediaBox1500×2600pt ở200DPI trước `PdfPage.render`: dự kiến4167×7223
  =30,098,241pixels, vượt20MP. Diagnostic override72DPI render1500×2600; đây không
  là thay đổi default hoặc profile Data đã chấp nhận.

Phương án physical size đã đo: chuyển hai PNG tiny Data thành **PDF ảnh** tại
200DPI, MediaBox540×936pt. Loader ở default200DPI render1500×2600px, processed
1154×2000; native OCR thành công cả hai loại. Raw text theo block order trùng PNG
tương ứng, gồm cả lỗi còn tồn tại. Đã mở Poppler renders và canonical overlays.
Không chứng minh vector-font PDF đại diện hoặc mọi chữ nhỏ đều đọc đúng; Data
cần giao PDF đại diện và chốt units/profile ở #42.

Artifact local ignored: `artifacts/evaluation/ai1-remaining-20261115/`.
`viewer-valid.html`, `viewer-unavailable.html`, `viewer-handoff.json` cung cấp
canonical bytes/hash1500×2600, metadata và29 vùng. Case unavailable giữ raw text,
IDs/scores, đặt quad=null + reason `NO_VERIFIED_MAPPING`. Backend cần gắn đúng
run/revision, kiểm hash/frame/promotion và trả acceptance; chưa gọi C4 Done.
Case hash/frame sai đã có trong `tests/fixtures/ocr-d1-canonical-assets.json`.

### Oracle, exporter review và lỗi quan sát (D)

Đã chạy lại15 known-score tests của Data trong env Data riêng: NFC/diacritics,
whitespace/case, tiền, insert/delete/substitute, empty reference/prediction,
QA/unknown scope và failure accounting. Regression AI1 mới dùng wrapped description
`Áo / Đỏ` và hai numeric cells: renderer draw-call join `Áo Đỏ 2 8`, OCR row join
`Áo 2 8 Đỏ`. Mọi token đúng nhưng WER=2/4. Giữ policy
`d31-canonical-nfc-v1-proposed`; không reorder OCR cho khớp gold.

Exporter AI2 `pipeline/extraction/predictions.py` đã xuất `vietdoc.predictions.v1`
và companion diagnostics, nhưng gọi extraction trước khi ghi record. Chưa thay
exporter của AI2 hoặc tạo OCR-only contract mới khi outcome convention chưa chốt.
Wrapper offline AI1 `pipeline/ocr/diagnose.py` tái dùng evaluator hiện có và chỉ
phục vụ diagnostic. Nó dùng payload={}, raw blocks join theo order hiện hành;
không đưa business gold vào predictions. Scalar metrics trong report **không áp dụng**.

Chẩn đoán tiny2 mẫu, scope/order còn Proposed; **không phải baseline dev chính thức**:

| Type | CER edits/reference chars | WER edits/reference words | Support |
|---|---|---|---|
| Receipt |38/426|10/97|1|
| Invoice |37/478|9/106|1|
| Tổng |75/904|19/203|2|

Reports giữ evaluator version/source hash, exact manifest/asset/prediction hashes,
denominators/exclusions và đầy đủ errors. `diagnostic-png/` và `diagnostic-pdf/`
có cùng OCR counts. Đây là5 ví dụ lỗi để Data/AI2 phân loại tiếp:

| Case | Expected / actual | Stage hoặc giả thuyết cần kiểm |
|---|---|---|
| Receipt header |`SL` / `sL`|Recognition/case; không sửa raw text|
| Receipt unit |`hộp` / `nộp`|Recognition crop resolution; có region, chưa kết luận detector bỏ chữ|
| Invoice header |`SL` / `SsL`|Recognition; có thể ảnh hưởng table grouping của AI2|
| Receipt wrapped description |Continuation trước numeric cells / sau numeric cells|Order protocol khác nhau, không quy hết thành glyph error|
| Invoice wrapped description |Continuation trước numeric cells / sau numeric cells|Cùng vấn đề order; cần Data/Lead chốt oracle|

Full D1 B3/B4 vẫn chờ `d12-handoff.zip`, `inventory.json`, `SHA256SUMS` từ Data;
không dùng hai tiny samples để đóng20 unique IDs. D3 chính thức cần dev split và
scope/order được Data/Lead chấp nhận; D2 production adapter còn cần AI2/Data thống nhất.

### Một biến preprocessing opt-in (E, diagnostic)

Protocol lưu trước chạy ở `paired/protocol.json`: chỉ đổi long edge2000→2600;
giữ input/model, canonical image, cap và budget. Mỗi profile/type có1 warm-up +3
lượt đo, đảo profile order ở lượt chẵn. Có16/16 outcomes ok, raw text ổn định giữa
ba lượt mỗi profile/type; geometry validate đạt. Regression giữ canonical pixel
hash và evidence frame giống nhau ở default/opt-in.

| Type | CER trước → sau | WER trước → sau | Median wall trước → sau (s) |
|---|---|---|---|
| Receipt |38/426 →37/426|10/97 →9/97|1.785 →1.815|
| Invoice |37/478 →37/478|9/106 →9/106|1.860 →1.903|

Receipt sửa `nộp→hộp`; invoice `SsL→sL`, vẫn chưa khớp `SL`. Numeric cell tokens
và totals quan sát được giữ nguyên; downstream extraction/items chưa đo. Parent
lifetime peak working set528MiB, không gồm decode child. Kết luận: **giữ default
2000**, candidate2600 chỉ là cấu hình opt-in đã có sẵn, chưa promote. Support2 và
order chưa Accepted không đủ chốt E trên dev; không tune tiếp nhiều profile trên
hai mẫu này. Paired outputs/versions/protocol/latency nằm trong `paired/` và
`diagnostic-paired-*`; giữ cả những lỗi không cải thiện.

### Resource và tái lập (F)

Native run dùng Windows11, i7-12700H14C/20T, RAM16GiB, adapter CPU4; pinned model
set `ppocrv5-det-tess-vie-50446e5d01ac-b6b49293d95d`, runtime/model/source hashes ở
`native/protocol.json`. Engine load8.628s (một cold load). Có11/11 outcomes ok:
2 warm-up,6 measured,1 blank PNG4000×4999 gần cap,2 PDF proposal. Receipt/invoice
wall median1.797/1.938s, max1.908/1.949s; native median1.490/1.557s.
Parent RSS sample mỗi10ms max671MiB; OS lifetime peak working set710MiB. Decode
subprocess không được tính; không công bố p95 từ3 samples, service SLA hoặc GPU quota.

Guards/deadline/cleanup/fatal/storage regressions có trong fixture gate; real
encrypted-PDF E2E, native hang/restart và service concurrent capacity chưa được
chứng minh ở đây. F4 vẫn cần người khác/máy thứ hai replay. Các local runner và
protocol/report ở artifact root; cần giao cả runner+inputs/pins khi team tái lập.

### Migration matrix chuẩn bị trước quyết định #63 (G1)

| Input/outcome | Legacy v1 | Opt-in v2 |
|---|---|---|
| Complete readable |Giữ blocks/text/IDs/quads/scores|Complete, cùng readable data|
| Mixed readable/empty |Adapter reject page|Partial; giữ readable blocks + unreadable IDs/reasons|
| All detections empty |Adapter reject page|Unreadable; không bịa readable text|
| No detections |Complete với blocks rỗng|Complete, cả hai arrays rỗng|
| Unsupported version |Reject|Reject|
| Invalid score/geometry, provider/OOM/timeout |Typed failure|Typed failure; empty text không che lỗi|

Regression thực: `test_ocr_contracts.py`, `test_paddle_adapter.py`,
`test_ocr_handoff.py`, `test_evidence.py`, `test_ocr_consumer.py`. Missing total
không thành absent; Backend vẫn phải chứng minh server-side approve blocker.
Đọc artifact lịch sử theo version gốc, không downgrade partial v2 để bỏ diagnostics.
Rollback chỉ đổi config lượt chạy **mới**: `--artifact-version 1` thay opt-in2.
Chưa đổi default: G2/G3 chờ AI2/Backend acceptance và Lead #63.

### Kiểm chứng checkpoint này

- Review trước commit ở `artifacts/evaluation/ai1-commit-review-20261115/`:
  fixture gate **745 passed,459 subtests,1 allowed Windows symlink skip**,
  policy_failures=[],exit0; JUnit/log `fixture.xml` / `fixture.log`.
- Focused preprocess/geometry:37 passed,85 subtests,0skip; handoff/replay:
  43 passed,86 subtests,0skip. Evaluation Data49 tests và actual replay integration6
  tests PASS trong env Data riêng. Fixture/native/Data `pip check` đạt.
  Workflow lint trước đó đạt (3 suppressions hiện có); workflows không thay đổi.
  `git diff --check` đạt.
- Native resource11/11 + paired16/16 là benchmark trước đó. Lượt review trước
  commit đã chạy lại **suite native3 methods,32 subtests,0skip**, dùng model/font
  đã pin, có fresh OCR/geometry overlays. Không phải20 documents full D1.
- Build wheel và cài vào target riêng: module replay được import từ wheel,
  chạy cả4 nhóm với cwd ngoài source và không dựa vào contracts env discovery;
  metrics/accounting khớp4/4. Không đổi default profile hoặc evaluator policy.
- Hosted CI trên increment này chưa chạy; kiểm tra local không thay acceptance
  còn chờ ở trên.

Commands đã dùng: fixture env `python -m scripts.ci.ai
--allow-windows-symlink-skip --junitxml <artifact-root>/fixture-final.xml`;
Data env `python -m unittest discover -s <byte-exact-checkout>/tests/unit
-p test_evaluation.py -v`. Byte-exact checkout được export bằng `git archive` từ
base ở đầu checkpoint để tránh checkout CRLF làm sai hash assets lịch sử.

Native prerequisites/env theo [Python README](../src/vietdoc/README.md#chạy-ocr-ai-1).
Native probe runners `measure.py`, `paired.py` nằm trong artifact root,
không thuộc production API. Để native replay, copy `measure.py`/`paired.py` vào
root **mới** dưới `artifacts/evaluation/`, giữ depth giống bản này, đặt `PYTHONPATH`
tới repo/src rồi chạy bằng native venv. Runner tạo output độc quyền và không ghi
đè lượt cũ. Scoring dùng Data env, root có fixtures **và** `specs/contracts/` để
Data verifier kiểm schema/asset hashes. Scoring CLI được version trong
`src/vietdoc/pipeline/ocr/diagnose.py`; gọi `python -m vietdoc.pipeline.ocr.diagnose`.
CLI nhận đường dẫn qua tham số, không phụ thuộc vị trí script, cwd hoặc thư mục
của lần review cũ. `diagnose.py` local trong artifact root chỉ còn là launcher.
`--manifest` tương đối theo `--data-root` hoặc tuyệt đối bên trong root đó;
`--manifest-sha256` phải là pin đã bàn giao, không tính lại từ input bất kỳ để bỏ
qua mismatch. `--input-root` chứa native/paired artifacts; `--output-dir` phải mới.

Ví dụ replay cả4 nhóm từ artifact bundle hiện có, không chạy native lần nữa.
Chạy từ repo root; `$dataPython` là executable của env Data đã provision:

```powershell
$repo = (Resolve-Path '.').Path
$artifactRoot = Join-Path $repo 'artifacts/evaluation/ai1-remaining-20261115'
$replayRoot = Join-Path $repo 'artifacts/evaluation/ai1-score-replay-01'
New-Item -ItemType Directory -Path $replayRoot -ErrorAction Stop
$replayZip = Join-Path $replayRoot 'reference.zip'
git archive --format=zip "--output=$replayZip" `
    b9bd7f478bb5037e3a14a1ca90375d462497d90f tests/fixtures/d12 specs/contracts
if ($LASTEXITCODE -ne 0) { throw 'Reference export failed' }
$dataRoot = Join-Path $replayRoot 'reference'
Expand-Archive -LiteralPath $replayZip -DestinationPath $dataRoot
$env:PYTHONPATH = Join-Path $repo 'src'
& $dataPython -m vietdoc.pipeline.ocr.diagnose `
    --data-root $dataRoot --manifest 'tests/fixtures/d12/manifest.json' `
    --manifest-sha256 b9fcb952f95f86e0c2c3bc1420acf2e43e1a47d1ed3c51ed5170dd3200ef989c `
    --input-root $artifactRoot --output-dir (Join-Path $replayRoot 'results') `
    --groups png pdf paired-baseline paired-candidate
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic replay failed; inspect the fresh output' }
```

Đổi tên `$replayRoot` cho lần sau; không xóa/ghi đè kết quả cũ. Sai manifest pin
hoặc thiếu OCR input bị chặn trước output; Data evaluator vẫn reject asset hash
sai. Lỗi scoring sau khi tạo output có thể giữ predictions chẩn đoán dở dang,
trả exit nonzero và không có report thành công cho nhóm lỗi; dùng output root mới khi chạy lại.
Regression integration:6 tests PASS trong env Data, gồm launcher chuyển vị trí/cwd,
đường dẫn có spaces, manifest tương đối/tuyệt đối,4 nhóm metrics, sai pin/asset,
missing input và bảo toàn output hiện có. Evidence ở `fix-replay-01/`.
Suite fixture có thêm6 regression trong `test_ocr_handoff.py`, kiểm CLI/preflight,
source pins, không bịa business payload và real stdlib scoring core. File-boundary
validator của Data được isolate trong fixture env; integration ở env Data gọi
validator thật.

Giao native probe runners/protocol/inputs pins khi yêu cầu người khác tái lập;
những probe/output artifacts đó vẫn local ignored, chưa phát hành qua GitHub.
Scoring CLI và fixture regression nằm trong source của increment này. Local
results không thay chữ ký acceptance của AI2/Data/Backend/Lead.

## Checkpoint giao việc O1/O2 — 2026-11-23

Đối chiếu `AI1-giao-viec.md` v2. Candidate kiểm chứng dùng
`develop@1f03d8d120f7c3052fbc440d2779a030148a837e` (đã gồm PR83 và PR88),
hai commit AI1 `f9e1465` / `537d34d`, cùng delta source/tests của lượt này.
Checkout kiểm chứng riêng ở `.verification/ai1-20261123`; nhánh feature và hai
commit local được giữ nguyên. Source hashes thực chạy nằm trong protocol, không
coi base SHA là toàn bộ source candidate. Chưa có commit/push/hosted CI cho delta này.

### O1-B — receiver verify và native20 thực

Đã nhận [full20 của Data](https://github.com/harivodich/SE2026-T08/issues/22#issuecomment-6711644580).
Outer transfer SHA256 `f3b17ce81d7bb83a2417ab8aa402082c5a304508c7b72756503b13f184b3a84a`.
Ba inner files khớp exact size/hash của receipt Data. Verifier hiện hành chạy
trong env Data Python3.12.10/Pillow10.2.0/jsonschema4.10.3, xuất sang root mới:
**20 IDs, 10 receipt/10 invoice, 204 rows, 102 members**. Manifest SHA256
`093b8f772d19e5357ee6209f3358f44d7a072f457aaef64507f38081c0e70e9a`.
Không render/repack gold hoặc dùng fixture fallback.

| Native20 accounting | Kết quả |
|---|---:|
| Requested / native attempted |20 /20|
| OK /failed /NOT_RUN |20 /0 /0|
| Engine port calls quan sát độc lập /report |20 /20|
| Model load /engine closed sau batch |1 /true|

`handoff.py` bổ sung additive fields trong local report v2: `stage_seconds`
cho input/preprocess/OCR/export, `engine_calls`, `observed_engine_calls`,
`artifact_paths`, byte cap và decode timeout trong profile. Stage không chạy
giữ null. Timings là exclusive wall time; OCR gồm kiểm tra output của stage,
không cộng lại vào preprocess. Không tính ghi `run.json`/`report.json` vào các
stage này. Fatal/storage failures và NOT_RUN vẫn giữ denominator và mã lỗi cũ.
Đây là local report, không đổi shared wire schema hoặc business state.

Native env Python3.13.7, pretrained model set
`ppocrv5-det-tess-vie-50446e5d01ac-b6b49293d95d`, runtime/model hashes trong
`native20-protocol.json`. Profile giữ artifact v1, long edge2000, PDF200DPI,
20MiB/20MP, decode15s và budget180000ms mỗi sample. Windows11/i7-12700H,
20 logical CPUs/RAM16GiB, CPU4. Cold load7.422s; total batch wall64.661s.

| Type | Support | Median sample wall(s) | Max(s) |
|---|---:|---:|---:|
| Receipt |10|2.267|4.788|
| Invoice |10|2.509|4.950|

Parent lifetime peak working set543080448bytes; post-sample RSS đầu/cuối
374648832/380379136bytes. Đây là một batch tuần tự20 tài liệu khác nhau;
không là chứng minh leak-free dài hạn, child-process peak, service capacity hay
hard cancellation của native inference. Không đổi cơ chế cooperative deadline.

### O1-A/C/F — packet và actual consumer readback local

Artifact root local ignored: `artifacts/evaluation/ai1-20261123/`.

| Artifact | Nội dung /trạng thái |
|---|---|
| `native20/report.json`, `native20-execution.json` |20 records và counter độc lập, model close, actual stage timings|
| `native20-cache-index.json` |ID→OCR/prepared/canonical/overlay/preview/run paths, hashes và versions; integration cache|
| `consumer-readback.json` |Actual AI2 B0 + BoundEvidence trên20 outputs native;6 partial/blank fixture cases qua hai types|
| `consumer-packet.json` |33 cases; verdict producer/local AI2, expected outcomes/IDs/reasons, owner ACK và Backend NOT_RUN|
| `geometry-example.json` |Numeric forward/inverse, encoded canonical hash/dimensions và overlay|
| `stress-and-disposition.json` |Measured limits và critical-field disposition|
| `ai1-handoff.zip`, `packet-inventory.json` |Portable local packet, exact member hashes; chưa gửi hoặc được consumer ACK|

Native readback **20/20 PASS** về input/canonical hashes, RGB pixels/dimensions,
typed OCR/prepared pairing, canonical quad round-trip và actual B0 execution.
Max round-trip error5.7732e-13pixel, tolerance1e-7pixel. Đã mở overlay
`d12-receipt-01` và `d12-invoice-01`; không có failure/frame mismatch trong batch.

Numeric example: `d12-receipt-01`, `p0-b0015`, text `Tổng thanh toán: 37.500 đ`,
score0.94. Canonical1500×2600, processed1154×2000. Processed corner(740,235)
→ canonical(961.8717504333,305.5); inverse diagonal(1500/1154,1.3,1).
Quads giữ cyclic point order của region; normalized coordinates thuộc canonical.
Encoded canonical SHA256 `526259bdc0bb7561b9d7b51189e49f607a0bb1658f195e7171facb0abbee7ca3`.

Actual local AI2 readback nhận mixed-empty-whitespace/all-unreadable/no-detection
ở cả receipt/invoice,6/6 PASS: readable IDs và unreadable reasons được giữ;
required total vẫn null/unknown, không suy thành absent. Scoped `80.000` giữ
`p0-b0004`; unscoped partial/repeated values abstain. Packet có crossed geometry,
unsupported version, wrong frame/hash và required-total-missing cases. Hash
verification/Java viewer/approval semantics chưa được gọi PASS từ B0 object adapter.

**Giới hạn critical field:** actual B0 nhận total values ở20/20 samples, nhưng
`/total_amount.source_regions` rỗng cả20 với `SOURCE_OCCURRENCE_UNRESOLVED`.
Raw amount nằm trong OCR block ghép label+amount; existing guard không sinh
substring geometry. Raw OCR region có quad hợp lệ và được overlay. Giữ closure
occurrence guard của PR4; AI2/Lead cần xem serialization/evidence semantics,
Backend cần thể hiện highlight unavailable. Đây không là field-quality PASS.

Producer/AI2-local verdict khác owner ACK. AI2 cần nhận packet và trả case verdict;
Backend cần thử DTO, canonical promotion/viewer zoom và required-field blocker.
Current `ManagedPipeline` chỉ nhận pinned profile artifact v1; runtime HTTP opt-in
v2 và quyết định default #63 vẫn chưa nghiệm thu. Không sửa wiring của AI2.

### O1-D/E và O2 — phần đã đo và dependency còn thiếu

Existing replay CLI đã chấm20 OCR snapshots byte-exact qua evaluator Data thật,
payload={} và `business_metrics_applicable=false`. Kết quả **integration diagnostic**,
policy/order vẫn Proposed, không phải accepted dev baseline:

| Type | CER edits/chars | WER edits/words | Support |
|---|---:|---:|---:|
| Receipt |384/6843|222/1619|10|
| Invoice |412/7785|250/1818|10|
| All |796/14628|472/3437|20|

Outputs: `integration-ocr-diagnostic/diagnostic-png/{predictions,report}.json`.
Replay input layout chỉ copy exact native OCR bytes; index pins originals. Không
dùng D1 metrics để chọn preprocess. Thử long edge2000→2600 trước đây giữ trạng
thái tiny diagnostic; default vẫn2000. PR88 đã merge nhưng pilot plan vẫn có71
pending duplicate pairs,80 samples quarantine,0 eligible train/dev members.

| Increment | Trạng thái sau lượt này /input cần tiếp |
|---|---|
| O1-A |Packet producer và local actual AI2 sẵn; AI2/Backend owner ACK pending|
| O1-B |Receiver verify20 +native20 +readback/overlays PASS; cần giao packet và AI2 B0 ACK|
| O1-C |Numeric geometry và regressions sẵn; cần Backend viewer ACK, Data oracle/profile ACK|
| O1-D |Harness/known-score/integration diagnostic có; Data/Lead giao accepted train/dev IDs/assets/split/order để build cache và baseline|
| O1-E |Tiny comparison trước đây có; dev comparison/critical coverage chờ O1-D và AI2|
| O1-F |Producer/offline partial semantics PASS; actual HTTP v2/Backend blockers/owner verdict chưa có|
| O2-A |Chờ Lead #63 và consumer acceptance; chưa đổi default|
| O2-B |Chờ AI2 dev failure packet, accepted cache generation và candidate freeze #59|
| O2-C |Native batch/resource evidence có; repeated-job leak/hang isolation/slot/fence acceptance còn mở đúng owner|
| O2-D |Runbook/portable packet sẵn; peer clean subset replay và tổng nghiệm thu chưa có|

### Checks và replay

Recheck phát hiện và sửa metadata của packet case `unsupported-version`:
`artifact_version=99` khớp payload cố ý ngoài supported versions; expected outcome
vẫn là error. Kiểm consistency cả33 cases, negative control trên bản lỗi, rebuild
ZIP/inventory/checksums và readback toàn169 members. Bản trước sửa được giữ ở
`packet-history-v1/`; receipt sửa lỗi ở `packet-fix-verification.json`.
OCR source/model/outputs không đổi; không tính việc rebuild packet là native run mới.

- Combined candidate AI gate: **827 passed,473 subtests,1 allowed Windows symlink
  skip**, policy_failures=[],exit0. `combined-final.log` /`combined-final.xml`.
- Focused handoff44 tests/86 subtests PASS; geometry/PDF38 tests/87 subtests PASS.
  Encrypted-file test dùng hai PDF trắng thật, empty/nonempty user password:
  parser mở/render được với password đúng, production decoder từ chối
  PROFILE_EXCEEDED. Không mock security API trong test mới, không cài thêm package.
- Native suite thực **3 tests/32 subtests PASS,0 skip**; output mới ở
  `native-formats/`, `native-geometry/`. Bộ synthetic32 subtests này tách khỏi
  native20 manifest run ở trên.
- Data evaluator49 tests PASS; fixture/native/Data `pip check` PASS.
- Hosted CI, Java/viewer/HTTP-v2 acceptance và peer reproduction: NOT_RUN.

Từ source candidate có hashes đã pin, chọn đường dẫn output mới cho mỗi lần.
Model/env setup và license/hash pins giữ runbook ở `tests/README.md`.

```powershell
$repo = (Get-Location).Path
$env:PYTHONPATH = Join-Path $repo 'src'
$ocrPython = Join-Path $repo 'artifacts/models/.venv-ai1/Scripts/python.exe'
$dataPython = Join-Path $repo 'artifacts/models/.venv-ai1-data/Scripts/python.exe'
$evidence = Join-Path $repo 'artifacts/evaluation/ai1-20261123'
$assetRoot = Join-Path $evidence 'full20-verified'
# Receiver verify vào root mới; inner bundle cần đúng ba file pinned của Data.
& $dataPython -B -m vietdoc.data.generator.handoff verify `
  --bundle (Join-Path $evidence 'received-full20') --output $assetRoot
if ($LASTEXITCODE -ne 0) { throw 'Full20 verification failed' }
# Replay subset sạch: dùng verified asset root có sẵn và output chưa tồn tại.
& $ocrPython -B -m vietdoc.pipeline.ocr.handoff --root $assetRoot `
  --manifest (Join-Path $assetRoot 'datasets/manifests/d12-integration-v2.json') `
  --model-root (Join-Path $repo 'artifacts/models/ocr-v1') `
  --artifact-version 1 --sample-ids d12-receipt-01 d12-invoice-01 `
  --output-dir (Join-Path $evidence 'peer-subset-new')
if ($LASTEXITCODE -ne 0) { throw 'Native subset failed; inspect records' }
```

Root `full20-verified` trong evidence hiện đã tồn tại. Khi chạy lại receiver verify,
chọn root mới và cập nhật `$assetRoot`; khi chỉ replay, dùng root đã verify và bỏ
bước verify. Bỏ `--sample-ids` để chạy đủ20. Đọc report/counts, hashes và overlays;
ghi environment/commands/PASS/FAIL/NOT_RUN của người chạy lại trước khi ACK.

## PR89 review delta — 2026-11-24

F01/F02 được sửa riêng tại offline `ocr.diagnose`, giữ closure geometry/PDF,
handoff instrumentation và pretrained provider. CLI dùng evaluator helper
`dataset_version(manifest)`; manifest format version và dataset identity không
còn bị gộp. OCR snapshots phải là UTF-8 JSON không duplicate keys, nonfinite
numbers hoặc lone surrogates và qua `OcrPage.from_dict` trước khi tạo output.
Toàn bộ groups được preflight; overwrite, manifest pin và path guards giữ nguyên.

Mapping diagnostic dùng outcomes hiện có của scalar evaluator:

| Source OCR | Prediction outcome | Text / diagnostics |
|---|---|---|
| Legacy v1 hoặc v2 complete, kể cả blank không detection | `ok` | Giữ readable text; source version/status/flags explicit |
| v2 partial | `ok` | Giữ toàn bộ readable text, unreadable regions, scores/quads và flags; `ok` không có nghĩa recognition complete |
| v2 all-unreadable | `failed`, `OCR_UNREADABLE_REGIONS` | Không gọi blank success; sample vẫn trong CER/WER denominator, `missing_or_failed_ocr` tăng |
| Unsupported version / invalid OCR | Reject trước output | Không tạo prediction/report để chấm input không hợp lệ |

`predictions[*].ocr_diagnostics` là source diagnostics nội bộ của replay,
không phải wire OcrPage schema mới. Report thêm `source_ocr_states` theo sample ID;
prediction vẫn `payload={}`, business metrics không applicable và diagnostic
vẫn PROVISIONAL. Không đổi evaluator policy, shared schemas, Java, service
default v1, longedge2000 hoặc PDF200DPI.

Regression và evidence tại ignored `artifacts/evaluation/ai1-pr89-fix-20261124/`:

- AI fixture gate: **829 PASS /484 subtests**, một Windows symlink skip đúng
  policy, `policy_failures=[]`; `ai.log`, `ai.xml`.
- Actual Data renderer/file evaluator: D1 hợp lệ và freshly rendered D2.2
  5 bases/10 images, dataset version khác format; CLI normal và `-O` PASS.
  Partial/unreadable/blank và unsupported99 qua public replay; 4 tests PASS.
  `tests/unit/test_data_ocr_replay.py` được Data CI matrix tự thu thập.
- Negative control chạy 3 regression bằng đúng source CLI cũ `36434a8`:
  fail assertions dataset version, missing diagnostics, unreadable accounting
  và unsupported99; **0 setup/import errors,0 skip**. Bản sửa PASS.
- Full Data gate local có lỗi Windows privilege `WinError1314` tại symlink
  trong test pre-existing `test_data_d21.D21Test.test_manifest_tampering`;
  focused repro xác nhận cùng lỗi ngoài vùng sửa. Không bỏ test hoặc đổi OS
  settings để che lỗi. Hosted CI trên head mới phải được kiểm tra riêng.
- Native inference **NOT_RUN trong delta này**. ZIP cũ SHA256
  `a3f3b398ec3c37f3dafdbb2b1842cff39cdae1a334a435371093f2f1ea4b90aa`
  vẫn 169 members: 168 payload hashes/sizes khớp inventory, inventory member
  byte-exact; cả 6 core source pins khớp. Không cần chạy lại model vì chỉ sửa
  diagnostic replay. Packet accessibility, independent verification và
  AI2/Backend ACK vẫn phải ghi nhận riêng trước nghiệm thu milestone native20.
- Replay score từ 20 raw OCR đã pin bằng CLI sửa PASS: CER796/14628,
  WER472/3437, support20; giữ nguyên integration diagnostic cũ, không gọi
  official dev baseline. Output mới `native20-rescore/`, không sửa packet cũ.

## Pilot160 — O1 increment, 2026-11-26

Task hiện hành: `GUI_AI1.zip`, `01_CONG_VIEC.md` O1–O5; bước này chỉ nhận
inputs và audit native outputs đã có. PR89 đã merge; nhánh mới từ
`develop@277ce86` (PR93). Không chạy lại native, đổi model/default hoặc train.
`adaptive-engineering`/`software-architect` không có trong skill catalog; dùng
inspect → criteria → smallest change → verify → diff review.

Outer inventory24/24 size/hash PASS, giữ25 ZIP members trong ignored
`artifacts/evaluation/ai1-v1-20261126/received/`. Data receiver hiện hành verify
968 members/960 assets vào root mới `verified-data/`; không sửa reviewed plan,
gold, splits hoặc source trong packet. Native archive được pin
`4c8de673d14633c00ed2c12bdf9c27e5a21414ab7a1f61f36e1ce97b95f22c00`,
chỉ giải nén1620 regular members với safe paths/bounds, không thực thi source cũ.

Tool mới `python -m vietdoc.pipeline.ocr.audit` nhận manifest/report/cache-index
SHA256 từ handoff, reuse actual Data validator/scorer và OCR contracts. Tool kiểm
đủ IDs/raw input pins/report-run/canonical encoded+RGB pixels/processed frames/
OCR-prepared/cache provenance/profile trước output mới; giữ failed/not_run và
all-unreadable trong denominator, không suy fields absent. Groups gồm type,
base/family, augmentation variant, row_count và split; mỗi sample có evidence path.
Numeric/marks/order mismatches là triage signals, không gán nguyên nhân detection
hay model mapping khi chưa có matching policy/labels phù hợp.

Public CLI đã chạy toàn160; `audit-final/report.json` và `summary.md` ở ignored
root nêu trên. Accounting160 requested/160 attempted/160 execution-ok,
0 failed/0 not_run; recognition **144 complete/12 partial/4 unreadable**,
**15 no-detection** đếm riêng (thuộc complete, không cộng thêm160). Roundtrip max
3.3306690738754696e-13pixel, tolerance1e-7. Cả7 core source files byte-exact với
`source-host.tar.gz`. Model ZIP có4/4 native files đúng hash/size; `pipeline.json`
trong declared engine inventory không có ở model ZIP, nên chưa chứng nhận full
runtime release hoặc activation từ riêng archive này.

| Slice | Samples | CER edits/reference | WER edits/reference |
|---|---:|---:|---:|
| receipt | 80 | 1192/32130 | 1165/7349 |
| invoice | 80 | 1199/37431 | 1229/8331 |
| clean | 40 | 840/26915 | 865/6043 |
| mild | 40 | 923/26915 | 1010/6043 |
| crop | 40 | 433/15731 | 443/3594 |
| unreadable variant | 40 | 195/0 → null | 76/0 → null |

Reading-order/evaluator policy vẫn Proposed. Unreadable variants có40 empty
transcripts: zero denominator trả null, không gọi100% accuracy và không dùng
empty transcription làm gold cho obscured business fields. Native execution-ok
khác recognition complete/field correctness; producer report không thay owner ACK.

Case ưu tiên dev `v0-2-pilot-20261126-receipt-f06-b0002-mild`:12 hàng,
quantity `0,5` đọc thành `05`, lỗi dấu trong title/product; đã xem overlay trên
canonical frame. Giả thuyết cho increment tiếp: một explicit longedge2600 profile
giữ nguyên engine/dtype/threads và cùng dev membership để kiểm small glyphs/
digits của12/30-row pages. **Chưa benchmark giả thuyết, không đổi default2000
hoặc cache AI2 đang dùng.** Detection recall/precision, causal skew/crop attribution,
total/item evidence quality và independent consumer acceptance còn chưa đo.

Lệnh trên checkout hiện hành sau receiver (output phải mới):

```powershell
$env:PYTHONPATH='src'
$base='artifacts/evaluation/ai1-v1-20261126'
$native="$base/native-received"
python -m vietdoc.pipeline.ocr.audit --data-root "$base/verified-data" `
  --manifest "$base/verified-data/dataset/manifest.json" `
  --manifest-sha256 99a66a13f555892b61abb93272b582a042d26947bd0af45210ee50ad2319619d `
  --handoff-root "$native/native-ocr-v2" `
  --report-sha256 ef23e8f63b8e18a86736d5fa2a9d98b6b1d79dac8b638969c55a5aaa4f8244ec `
  --index "$native/ocr-train/index.json" ef2c79ddf623f5ea3c27025a32e39bd0c9b367259791fb3601dcb9a3a77c9dc7 `
  --index "$native/ocr-dev/index.json" 9de82517d20370787794d5b43e9827b5d3e879844ef39859fe087fdced2522fd `
  --output-dir "$base/peer-audit-new"
```

Review follow-up sửa hai guard: đối chiếu cache canonical dimensions/encoded hash/
pixel hash/size với ảnh đã verify; đối chiếu counts và excluded IDs/reasons với
native report cho từng split export. JSON đầu vào phải là object; report array,
null hoặc scalar trả exit2 với diagnostic cố định, không traceback/output.
Không đổi bridge producer contract hoặc kết quả OCR.

Recheck actual Data boundary trên160 mẫu PASS, giữ nguyên counts/recognition/
per-sample metrics/slices/geometry so với audit trước. Evidence mới ở
`audit-fixed-20261126/report.json` và `verification.json` trong ignored root;
report SHA256 `bb1a83d04dfc351f55cde8792f61a1dc4bc3988fce453aded6952e2851ae00e4`.
Hai negative controls dùng bản sao index đã repin (width999 và exported999)
đều bị từ chối trước output; subprocess CLI với report `[]` trả exit2, không
traceback/output. Packet gốc giữ nguyên pins. Đây là replay audit, không chạy
lại native inference.

Focused handoff/audit/bridge **146 tests/125 subtests PASS**; mở rộng thêm OCR
contract/geometry **186 tests/314 subtests PASS**; audit chạy Python `-O`
**15 tests PASS**. Sau khi bổ sung đúng `PyYAML==6.0.3` và
`torch==2.14.1+cpu` vào fixture env riêng, `pip check` PASS. Full AI gate local:
`python -m scripts.ci.ai --allow-windows-symlink-skip --junitxml=artifacts/evaluation/ai1-v1-20261126/ai-full-pr.xml`
**1266 tests/518 subtests PASS**, 1 symlink test skip đúng ngoại lệ Windows,
1267 collected, policy_failures=[], exit0; log/XML ở ignored root.
Đây là local fixture gate, hosted CI phải kiểm tra trên head PR sau push.
Native OCR inference và actual-provider backend/live E2E NOT_RUN ở increment
này; không suy acceptance O2–O5 từ fixture gate. Evidence lớn vẫn ignored,
packet nguồn người dùng cung cấp được giữ nguyên.

## R1 — Dev triage và oracle, 2026-11-26

Task: `AI1-ke-hoach-hoan-thien-V1-sau-PR97.md`. Khi bắt đầu, PR97 còn mở ở
`a875753`, PR98 đã merge; `origin/develop=4af6b88`. Tiếp tục trên branch97
theo kế hoạch; trạng thái head/base và CI bàn giao được cập nhật tại PR97.
Không làm lại O1; R2–R6 chưa được nghiệm thu từ kết quả bên dưới.

`python -m vietdoc.pipeline.ocr.triage` xuất packet gồm full audit `report.json`
và ledger `triage.json`. CLI bắt buộc pin manifest/report/index như audit97,
kiểm full population trước khi lấy 8–12 dev IDs; reject duplicate/unknown/train
IDs hoặc thiếu coverage hai type, bốn variants, các mức 0/12/30 hàng.
Annotation/transcript và observed OCR giữ riêng; không ghép regions theo index,
không đưa gold vào OCR hoặc tự kết luận nguyên nhân từ CER. Thư mục đích phải
mới và parent đã tồn tại; failure không publish packet thành công.

Canary cố định **12 IDs**, prefix `v0-2-pilot-20261126-`, lấy tích Descartes của
type `receipt`, `invoice` với sáu suffix dưới đây. Không chọn lại membership sau
khi xem candidate; full paired experiment tiếp theo vẫn dùng cùng 80 dev IDs.

| Suffix sau type | Hàng | Vai trò triage |
|---|---:|---|
| `f07-b0003-clean` | 0 | Clean control, title/spacing và total zero |
| `f06-b0002-mild` | 12 | Quantity/dấu, có case receipt đã giao |
| `f07-b0002-clean` | 30 | Dense-page clean control |
| `f07-b0002-mild` | 30 | Cùng base dense-page, giữ degradation |
| `f06-b0002-crop` | 12 | Visible-only support, không suy fields bị cắt là absent |
| `f06-b0004-unreadable` | 0 | Empty-reference/no-detection control |

Packet local: `artifacts/evaluation/ai1-v1-20261126/r1-triage-12/`;
triage SHA256 `e571386cfcee1b8a930cf8ceba94cc3e5f379c620dccf6ef203d9bcf97ec5d5c`.
Đã chạy actual Data validator/full160 audit bằng CLI này, xuất đúng12 cases.
`review-notes.json` riêng ghi manual inspection, source/canonical pins, block IDs,
focus crop bounds, certainty, impact và phép kiểm tiếp. Contact sheet12 case và
canonical/processed crops bốn case trọng điểm ở ignored root; không upload raw pilot.

| Case (rút prefix) | Expected → actual | Region | Kết luận có giới hạn |
|---|---|---|---|
| receipt-f06-b0002-mild | `0,5` → `05` | `p0-b0017` | Có detection tại vùng; cần tách crop/recognizer |
| invoice-f06-b0002-mild | `1` → `4` | `p0-b0021` | Glyph nhìn thấy trong canonical/processed; nguyên nhân chưa chốt |
| invoice-f07-b0002-clean | `0,5` → `05` | `p0-b0024` | Lỗi xảy ra cả clean, không chỉ augmentation mild |
| invoice-f07-b0002-mild | `0,5` → `05` | `p0-b0024` | Giữ cùng focus region cho paired comparison |

Các total block được kiểm ở bốn case trên giữ đúng digits theo annotation; không
gán lỗi total/extraction khi chưa có evidence. Hai crop cases có52 OCR blocks;
header/quantity column bị cắt không là detector miss. Hai unreadable controls
không có detection, recognition `complete`; không đổi thành all-unreadable,
không gọi empty-reference accuracy100%. Bbox overlap chỉ giúp tìm candidate để
xem bằng mắt, không là accepted matching policy/recall/precision.

Oracle C03/C04: reuse wrapped-table known-score WER2/4, two-column/jitter/tall-row,
EXIF/resize/projective và evidence scope tests hiện có. Bổ sung đúng gap30 hàng
trong `ReadingOrderTest`: drawing schedule độc lập, detector order bị đảo,
hai scale, amount lặp30 lần; phải giữ đủ60 region, thiếu context abstain,
context hàng29 trả `p0-b0060` với quad tính tay
`[(.7,.88),(.99,.88),(.99,.89),(.7,.89)]`. Đây là fixture oracle, không phải
native quality. Policy `d31-canonical-nfc-v1-proposed` giữ nguyên: NFC,
whitespace collapse, case/digits/dấu giữ nguyên; renderer draw order khác OCR
row order được báo riêng, không sort hypothesis để cải thiện CER.

Lệnh tái lập ledger dùng các tham số pin/root trong phần Pilot160, đổi module
thành `vietdoc.pipeline.ocr.triage`, output thành root mới và thêm12 lần
`--sample-id <full-ID>` theo bảng cố định trên. `--help` đã kiểm thực tế.
Oracle và regression chạy được trên fresh checkout với fixture env:

```powershell
python -m pytest tests/unit/pipeline/test_ocr_audit.py tests/unit/pipeline/test_geometry.py tests/unit/pipeline/test_evidence.py tests/unit/pipeline/test_paddle_adapter.py -q
```

Kết quả focused:126 tests/172 subtests PASS. Full local AI gate trên R1:
1273 tests/524 subtests PASS, 1 symlink skip theo ngoại lệ Windows,
1274 collected, policy_failures=[], exit0. Log/XML `r1-full-ai.*` ở ignored
root; chưa là hosted CI trên base sau PR98. Packet/evidence paths/source hash
recheck PASS; CLI duplicate selection trả exit2, không output. Chưa chạy native candidate2600,
chưa xác nhận causal resize, chưa nhận policy C03/C04 hoặc consumer ACK.
R3 cần preregister điều kiện giữ/bỏ và runtime/resource pins trước native run;
giữ baseline2000/B0-v1/cache cũ. Thí nghiệm có kết quả âm vẫn hợp lệ.

### R1 review fix — Overlay verification

Review phát hiện exporter có thể publish đường dẫn overlay thiếu/hỏng hoặc PNG
hợp lệ nhưng sai nội dung. Bản sửa đọc snapshot PNG có byte cap, kiểm RGB/single
frame/dimensions, đối chiếu decoded pixels với `draw_overlay` từ canonical đã pin
và typed OCR đúng case. Sai pixels/frame hoặc thiếu/hỏng ảnh đều reject; chỉ
khác PNG compression/metadata nhưng cùng pixels vẫn hợp lệ. Không sửa packet
nguồn hoặc tự sửa ảnh sai. Canonical/overlay được rehash trước publish để phát
hiện thay đổi sau snapshot. Ledger ghi encoded/RGB hashes, dimensions, size,
renderer source hash và Pillow version cho từng overlay đã verify.

Regression mới gồm missing/corrupt/wrong pixels/wrong size/wrong mode,
PNG encoding tương đương và đổi bytes sau snapshot; audit/triage focused
22 tests/37 subtests PASS. Packet cũ `r1-triage-12` giữ làm lịch sử trước fix;
replay mới ở `r1-triage-overlay-verified/`, không overwrite report cũ.
Đối chiếu overlay là kiểm rendering evidence với phiên bản renderer đã ghi;
không thay kiểm native detector localization hoặc chứng nhận OCR đúng text.

Actual Data/full160 replay PASS, verify12/12 overlay; annotations/OCR/accounting
không đổi. Negative control trên bản sao native packet (PNG đúng kích thước nhưng
sai pixels) trả CLI exit2, không output, staging cleanup PASS; inputs gốc giữ hash.
Receipt `r1-triage-overlay-verified/verification.json`, triage SHA256
`c67024acfed45e40844138cc41d2bec230096afeeabd2cb1a3334bf4fd181643`.
Full AI gate sau fix:1276 tests/529 subtests PASS, 1 permitted Windows symlink
skip,1277 collected, policy_failures=[], exit0 (`r1-overlay-ai.log/.xml`).
Native inference NOT_RUN. Các số local trên được đo trước tích hợp PR98;
hosted CI phải kiểm trên head bàn giao mới, không kế thừa kết quả CI head cũ.
