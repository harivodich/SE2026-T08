# UML v1

Mười `.puml`/`.svg` là copy nguyên trạng từ [snapshot](../design/v1/08-uml-guide.md). SVG track là presentation từ canonical model, không output PlantUML compiler. [Verification 07/10](../reviews/verification-2026-10-07.md) đã compile 20 sources active/snapshot và render 10 active diagrams bằng PlantUML 1.2026.8; outputs local ignored .verification, không ghi đè SVG track.

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

Khi code thay state/contract, sửa source/diagram ở `docs/uml` trong cùng PR và review semantic relationships. Không sửa bản lưu `docs/design/v1`; khi có compiler local, compile lại và báo verification thực tế. Không gửi tài liệu lên renderer public mặc định.
