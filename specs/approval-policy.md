# Review, approval và export policy v1

Reference: [workflow gốc](../docs/design/v1/01-scope-workflows.md), [contracts gốc](../docs/design/v1/03-contracts.md).

## Save/adopt

Prediction của ExtractionRun không sửa in-place. Save gửi corrected payload đầy đủ, base revision, expected document version và reason. Structural invalid →422, stale head/version →409; rollback revision/audit nếu CAS fail. UI giữ local edits khi conflict.

Save hoặc adopt candidate append revision và đổi head; revision mới là DRAFT kể cả head cũ đã approved. Bản cũ và approval cũ giữ nguyên. Rerun thành công chỉ tạo initial draft nếu chưa có head; nếu đã có thì tạo candidate chờ adopt.

## Approval guards

1. Actor được authorize với document; revision là current head và expected version đúng.
2. Revalidate đúng payload snapshot, không dùng lại prediction issues như kết quả cuối.
3. `total_amount` non-null và không mơ hồ trong cả receipt/invoice. Thiếu phải sửa hoặc reject; không silent admin bypass.
4. Không có structural/profile/rule blocker; ngày/giờ kiểm semantic, không chỉ regex.
5. Operator xác nhận đã đối chiếu và completeness. Warnings cần acknowledge issue IDs với reason khi policy yêu cầu.
6. Transaction ghi Approval, tăng document version qua CAS và append audit. Mỗi revision tối đa một approval.

Scalar optional có thể null với warning. `items=[]` không chứng minh tài liệu không có bảng. Không bắt người dùng áp công thức thuế/discount khi chứng từ không có đủ operands hoặc khác monetary convention.

Arithmetic warning không được override số trên nguồn. Human correction không gán confidence=1.0; giữ original provenance và đánh dấu origin human.

## Export

Export chỉ revision thuộc document/owner và đã approved được chọn rõ bằng ID. Business JSON dùng schema version và decimal strings; không trộn editor metadata/evidence vào payload.

Cùng revision/format/exporter version phải cho cùng bytes/hash. Draft mới không thay artifact approved cũ. Yêu cầu latest trong khi latest head là draft →409; có thể chọn rõ approved revision cũ. Approval/save race phải có test: một transaction thắng, transaction còn lại conflict.
