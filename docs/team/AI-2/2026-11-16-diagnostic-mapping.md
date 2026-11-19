# AI2 → Backend diagnostic mapping proposal

Uses existing wire v1 Issue/FieldMetadata fields only. Consumer/Backend/Lead review still required; this document does not activate OCR v2 runtime.

| Diagnostic | Existing shared representation | Review consequence |
|---|---|---|
| OCR_UNREADABLE_REGIONS / SOURCE_OCR_INCOMPLETE | warning Issue at `/`, field review_flags; full region IDs/reasons in OCR/diagnostics artifact | Source partially unreadable; unknown remains unknown, never inferred absent |
| SOURCE_AMBIGUOUS / SOURCE_OCCURRENCE_UNRESOLVED | field review_flags; source_regions empty | No arbitrary occurrence highlighted |
| SOURCE_GEOMETRY_UNAVAILABLE | field review_flags; source_regions empty | Value may be extracted but location unavailable |
| FIELD_NOT_LOCATED / FIELD_VALUE_NOT_LOCATED | null payload, warning Issue and field review_flags | Missing evidence, not absent gold |
| CONFIDENCE_UNCALIBRATED | confidence=null, confidence_method=null, review_flags | No correctness probability claimed; OCR score stays separate |
| EVIDENCE_INVALID | existing OUTPUT_INVALID error envelope | Reject response rather than publish another source's geometry |

Runtime engine stays artifact v1. Partial v2 fixtures/adapter supported offline; activating runtime v2 remains blocked pending AI1/AI2/Backend acceptance of representation and Java artifact validation. Clean v1 requests do not establish partial-policy acceptance.
