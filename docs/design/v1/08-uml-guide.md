# 08 — UML và kiến trúc trực quan

Các sơ đồ mô tả **hệ thống đề xuất**, không phải code đang chạy. Nguồn `.puml` theo cú pháp PlantUML; SVG trình bày được tạo cục bộ từ cùng mô hình sơ đồ (Graphviz cho graph views, SVG renderer cho sequence và swimlane activity). Máy hiện không có Java/PlantUML compiler trong PATH: không tuyên bố các `.puml` đã compile bằng PlantUML. Xem verification report để biết check thực tế.

| Sơ đồ | Câu hỏi được trả lời |
|---|---|
| [01 — Use cases](uml/01-use-cases.puml) | Operator/admin được làm gì? |
| [02 — Components](uml/02-components.puml) | API, dispatcher, worker và storage liên hệ thế nào? |
| [03 — Processing sequence](uml/03-processing-sequence.puml) | Từ tạo job đến prediction/revision diễn ra ra sao? |
| [04 — Review sequence](uml/04-review-sequence.puml) | Save/approve/export có transaction và conflict gì? |
| [05 — Job state machine](uml/05-job-state.puml) | Retry/cancel/recovery/terminal states |
| [06 — Review state machine](uml/06-review-state.puml) | Head draft/approved, edit/rerun/adopt và historical export |
| [07 — Class model](uml/07-domain-classes.puml) | Entities, multiplicities, prediction/revision/approval ownership |
| [08 — Swimlane workflow](uml/08-activity-workflow.puml) | Trách nhiệm User/API/Worker/Reviewer trong xử lý |
| [09 — Deployment](uml/09-deployment.puml) | Containers, GPU worker, volumes, boundaries và offline training |
| [10 — Training workflow](uml/10-training-activity.puml) | Audit dữ liệu, chia tập theo template, fine-tune, freeze và release gate |

Quan hệ component/deployment dùng dependency; class dùng association/composition đúng đối tượng. Review state là trạng thái **head revision**; job state độc lập, rerun không làm mất approval của head hiện tại. Activity workflow giản lược retries; chi tiết recovery ở processing sequence và tài liệu 02.

Khi có Java/PlantUML ở môi trường team, render lại sources bằng compiler chính thức và review layout. Không cần gửi sources lên renderer public. Giữ source + diagrams cùng PR khi contract/state đổi; CI kiểm state enum/edges/contracts để tránh sơ đồ lạc code.
