# UML hiện hành: Java/Thymeleaf + Python AI

10 views theo target architecture, không claim code đã implement. Component/processing/deployment/activity cập nhật ADR-0009; domain/review invariants giữ nguyên. SVG hiện hành được tạo bằng PlantUML local, verification ghi trong [redesign report](../reviews/architecture-redesign-2026-10-07.md).

| View | Source | SVG |
|---|---|---|
| Use case | [source](01-use-cases.puml) | [view](01-use-cases.svg) |
| Components | [source](02-components.puml) | [view](02-components.svg) |
| Processing sequence | [source](03-processing-sequence.puml) | [view](03-processing-sequence.svg) |
| Review sequence | [source](04-review-sequence.puml) | [view](04-review-sequence.svg) |
| Job state | [source](05-job-state.puml) | [view](05-job-state.svg) |
| Review state | [source](06-review-state.puml) | [view](06-review-state.svg) |
| Domain class | [source](07-domain-classes.puml) | [view](07-domain-classes.svg) |
| Processing activity | [source](08-activity-workflow.puml) | [view](08-activity-workflow.svg) |
| Deployment | [source](09-deployment.puml) | [view](09-deployment.svg) |
| Training activity | [source](10-training-activity.puml) | [view](10-training-activity.svg) |


Sửa .puml trước, compile/render lại bằng local PlantUML, inspect SVG và semantic relationships. Snapshot docs/design/v1 bất biến, HTML snapshot còn stack cũ không dùng làm deployment authority. Không gửi source lên renderer public mặc định.
