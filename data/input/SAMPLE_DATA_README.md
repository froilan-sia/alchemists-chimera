# Sample Data for The Alchemist's Chimera - HKMA/Basel III Regulatory Framework

## Overview

This directory contains fictional demo PDFs for testing the local PDF ingestion,
knowledge-graph, ChromaDB, provenance, and hybrid retrieval workflows. The
sample corpus covers HKMA, Basel III, and risk-weighted-asset requirements.

Every sample PDF is visibly watermarked with:

> **FICTIONAL DOCUMENT - for demo purpose only**

These files are demonstration fixtures, not official regulatory publications
and must not be used as production compliance evidence.

### PDF Documents

The baseline corpus currently contains four PDFs. The application pre-loads
these baseline PDFs during FastAPI startup. The loader checks each file's
SHA-256 digest and stable chunk IDs in ChromaDB and the baseline graph before
ingesting it, so restarting the application does not create duplicate records.

| File | Content and key concepts | Primary testing purpose |
| --- | --- | --- |
| `hkma_capital_requirements.pdf` | HKMA Supervisory Policy Manual SA-2 on capital adequacy requirements, including CET1 ratio, Tier 1 capital, total capital ratio, leverage ratio, liquidity coverage ratio. | Extract HKMA regulatory requirements and provenance. |
| `basel_iii_framework.pdf` | Basel III international regulatory framework, including Capital buffers, leverage ratio, liquidity standards, risk coverage, G-SIBs, and D-SIBs. | Extract international regulatory standards and finance ontology concepts. |
| `risk_weighted_assets.pdf` | Risk-weighted assets calculation methodology for Credit risk RWA, market risk RWA, operational risk RWA. | Test technical calculations, risk categories, and evidence grounding. |
| `test_hkma_basel.pdf` | Combined HKMA/Basel III test document covering the capital requirements framework. | Exercise mixed-framework extraction and regression scenarios. |

The baseline loader is separate from user uploads. User-submitted files are
stored under `data/uploads/jobs/{job_id}/source.pdf` and are processed through
the asynchronous ingestion queue. Baseline files remain under `data/input/`.

## Related ontology and graph files

### Ontology files

- **`ontology/finance-ontology.ttl`** contains financial institutions,
  regulatory concepts, capital requirements, risk categories, properties, and
  sample instances.
- **`ontology/shapes.ttl`** contains SHACL shapes for banks, capital ratios,
  regulations, provenance, and extracted-term validation.

### Knowledge graph

- **`data/graphs/approved_kg.ttl`** is the seeded approved graph used by the
  explorer and default graph retrieval path.
- **`data/knowledge_graph.ttl`** is the comprehensive staging manager's
  approved graph and receives approved extracted records and baseline markers.

## Key regulatory concepts

### Capital requirements

- **CET1 ratio:** 4.5% minimum
- **Tier 1 ratio:** 6.0% minimum
- **Total capital ratio:** 8.0% minimum
- **Capital conservation buffer:** 2.5% additional
- **Countercyclical buffer:** 0–2.5% variable

### Liquidity requirements

- **Liquidity Coverage Ratio (LCR):** 100% minimum
- **Net Stable Funding Ratio (NSFR):** 100% minimum

### Leverage requirements

- **Leverage ratio:** 3.0% minimum of total exposures

### Risk categories

- Credit Risk
- Market Risk
- Operational Risk
- Liquidity Risk

## Entities for testing

### Regulatory bodies

- HKMA (Hong Kong Monetary Authority)
- Basel Committee on Banking Supervision
- Financial Stability Board

- HKMA, banks, authorized institutions
- Basel Committee, G-SIBs, D-SIBs
- Financial Stability Board, banks with internal models

### Banks

- HSBC Hong Kong
- Standard Chartered Hong Kong
- Bank of China (Hong Kong)

### Regulations

- HKMA Capital Adequacy Requirements
- Basel III Framework
- HKMA Liquidity Coverage Ratio
- Basel III Leverage Ratio

## Sample Queries for Testing

### Entity relationship queries

```text
"What are the capital requirements for HSBC Hong Kong?"
Which regulations apply to Bank of China Hong Kong?
Who regulates Standard Chartered in Hong Kong?
```

### Regulatory compliance queries

```text
What is the minimum CET1 ratio under Basel III?
What liquidity ratios does HKMA require?
How is the leverage ratio calculated?
```

### Technical calculation queries

```text
"How are risk-weighted assets calculated for credit risk?"
What are the risk weights for sovereign exposures?
What methods can banks use for operational risk RWA?
```

## Startup and ingestion behavior

1. Start the local stack with `./start.sh`, or run the backend with
   `PYTHONPATH=. uvicorn src.api.main:app --port 8000` alongside Streamlit on
   port `7860`.
2. FastAPI's startup lifespan checks the baseline corpus before starting the
   asynchronous upload workers.
3. Missing baseline records are loaded into ChromaDB and the baseline graph.
   Existing SHA-256 markers and stable chunk IDs are reused rather than
   duplicated.
4. User uploads use `POST /ingestion/jobs`, which returns a job ID before
   extraction begins. Poll `GET /ingestion/jobs/{job_id}` for stage progress,
   diagnostics, checkpoints, and the final `completed` or `partial` result.
5. Document chunks remain available for vector retrieval even when extraction
   produces no triples or only `QUARANTINED` triples. Graph publication still
   follows the staging and human-approval workflow.

## Usage for Testing PDF Ingestion Pipeline

### Document processing

- Upload PDFs to Surgeon's Table tab.
- Upload an additional PDF through the Surgeon's Table.
- Verify entity extraction, evidence grounding, and page-level provenance.

### Knowledge graph building

- Extract triples with proper provenance.
- Extract triples with canonical finance and Chimera namespaces.
- Validate candidates against SHACL shapes.
- Stage records for human-in-the-loop approval.

### Hybrid retrieval testing

- Compare deterministic graph facts with ChromaDB vector chunks.
- Test graph/vector fusion and dynamic `α(t)` weighting.
- Open cited source PDFs through FastAPI's `/documents/{file_name}` endpoint.

### Compliance verification

- Verify air-gapped operation.
- Verify local, air-gapped operation.
- Check audit trail completeness.
- Validate the human approval workflow.
- Confirm that a restart does not duplicate baseline records.

## Data characteristics

### Realistic complexity

- Multiple regulatory frameworks: HKMA and Basel III
- Technical calculation methodologies
- Financial institutions and regulatory bodies
- Provenance and audit metadata

### Extraction challenges

- Numerical values with percentages
- Regulatory hierarchies and relationships
- Evidence grounding in source text
- SHACL validation and quarantine behavior

### Compliance requirements

- Air-gapped local operation
- Human-in-the-loop approval
- Audit trail maintenance
- Transparent AI-assisted extraction

## Maintenance

### Adding a new baseline document

1. Place the PDF in `data/input/`.
2. Add it to the baseline loader's configured corpus when it should be
   automatically indexed.
3. Update the ontology if the document introduces new concepts.
4. Extend SHACL shapes when new validation constraints are required.
5. Add representative queries to this document.

### Updating the ontology

1. Add classes to `ontology/finance-ontology.ttl`.
2. Define properties and relationships.
3. Add corresponding SHACL shapes.
4. Add sample instances where useful.

### Updating the knowledge graph

1. Add only approved triples to the configured approved graph.
2. Include provenance metadata and evidence quotes.
3. Track approval history and preserve the audit trail.

## Notes for developers

- Unit tests should cover each regulatory concept and edge case.
- Integration tests should exercise baseline and uploaded-document paths.
- Performance tests should use realistic document sizes.
- Compliance tests should verify provenance, audit records, and approval rules.
- The baseline PDFs are fictional demonstrations and are not substitutes for
  official HKMA, Basel Committee, or other regulatory publications.

## Contact and support

- Project repository: https://github.com/froilan-sia/alchemists-chimera
- Documentation: See `README.md`
- Issues: Use the GitHub issue tracker

## License

Sample data is provided for testing purposes only. It is based on publicly
available regulatory topics and is not for production use.

Last Updated: November 17, 2026
