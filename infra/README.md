# Infrastructure đích

Backend owns Compose/build/runtime/runbooks; AI-2 review Python loader/GPU/capacity, AI-1 OCR dependencies. Chưa có config/container chạy.

Target services: app (Java web + Thymeleaf), job-runner (cùng Java artifact, runner profile), ai-service (Python private compute), postgres. Không Redis/Celery/web React container. AI/DB private network; model readonly; Python attempt volume không writable originals/committed assets/exports; Java promotes verified copies và streams authorized committed assets.

Pin env/deps/images sau actual smoke; test CPU/GPU profile và readiness trước handoff. Không deploy/cài dịch vụ tự động từ thiết kế. [Architecture](../docs/architecture.md), [Backend B7.1](../docs/team/backend.md).
