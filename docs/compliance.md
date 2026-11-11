# HKMA GenAI Sandbox and ART Framework Controls

The ingestion path uses local Ollama, RDFLib, and ChromaDB components. The compliance controls in `src/compliance.py` make the operating assumptions explicit and preserve evidence for review.

## Air-gapped operation

`AirGapVerifier` checks that:

- Ollama uses the loopback address and the pinned `qwen2.5:3b` model.
- No SPARQL endpoint or other configured endpoint points outside the container.
- Vector storage uses a local filesystem path.
- The embedding model is a local model identifier or an existing local path.

Run the check before processing documents:

```python
from src.compliance import AirGapVerifier

report = AirGapVerifier().assert_compliant()
print(report.as_dict())
```

The check verifies configuration boundaries. Container network policy and model pre-caching must also be enforced by the deployment environment.

## Deterministic guardrails

`DeterministicGuardrails` rejects a candidate when any required triple field is empty, confidence is outside `0..1`, the evidence quote is missing, or the quote is not a case-insensitive substring of the source chunk. When a `SHACLValidator` is supplied, the candidate must also receive the `valid` classification. A quarantined or invalid candidate cannot be published through `assert_publishable`.

These checks run before a record is considered for the Surgeon’s Table workflow and do not depend on an LLM response.

## Provenance and audit trail

`ComplianceAuditTrail` writes append-only JSONL events under `data/audit/compliance_audit.jsonl` by default. Each event contains an actor, timestamp, action details, resource or chunk identifier, and a SHA-256 link to the preceding event. The trail records:

- AI-assisted extraction decisions, including model, confidence, evidence quote, source document, page, and chunk.
- Human staging decisions with reviewer attribution and an optional reason.
- User interactions such as opening provenance or reviewing a record.

Use `verify_completeness()` for an audit package. It checks required fields, event hashes, and hash-chain links.

## Surgeon’s Table workflow

`SurgeonsTableWorkflow` validates table records before publication. It blocks automated actors such as `auto_approval`, requires non-empty triple fields and evidence, and requires a reason or edit for quarantined records. The UI role selector supplies the reviewer identity used by the audit trail.

The workflow keeps extracted knowledge in staging until a named human reviewer approves it. The production `CompatibleStagingManager` enables `require_human_approval`, while the UI’s optional one-click action is still an explicit, role-attributed reviewer action. A review decision should be recorded with `record_human_decision()` before the graph merge.

## Retrieval transparency

`RetrievalTransparency.report(alpha, graph_results, vector_results)` reports the effective graph and vector weights, result counts, raw scores, and weighted contributions. The Hybrid Chimera Chat tab renders the same branch-level information and provenance links so an auditor can distinguish symbolic graph evidence from vector context.

## Validation

Run the focused compliance tests with the repository environment:

```bash
PYTHONPATH=. venv/bin/pytest -q tests/test_compliance.py
```
