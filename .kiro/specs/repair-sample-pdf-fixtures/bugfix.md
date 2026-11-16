# Bugfix Requirements Document

## Introduction

The three regulatory fixtures listed in `data/input/SAMPLE_DATA_README.md` use `.pdf` filenames but currently contain plain ASCII text rather than PDF documents. This prevents the repository's `pypdf`-based ingestion path from opening them as PDFs. The bugfix shall replace the invalid payloads with deterministic, locally generated, self-contained PDF fixtures while preserving the existing filenames, README references, and documented regulatory fixture content. No implementation code or fixture files are changed during this requirements phase.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `data/input/hkma_capital_requirements.pdf`, `data/input/basel_iii_framework.pdf`, or `data/input/risk_weighted_assets.pdf` is inspected by file content rather than by filename THEN the system finds ASCII text instead of a PDF file with a PDF document header
1.2 WHEN the PDF ingestion parser opens any of the three named fixture files with `pypdf.PdfReader` THEN the parser cannot treat the file as a valid PDF document and the fixture cannot be used for the documented PDF ingestion tests
1.3 WHEN the three fixture files are used as sample regulatory documents THEN their intended plain-text content is present as a text payload but is not packaged in a self-contained PDF structure with pages and extractable PDF text
1.4 WHEN replacement fixture content is prepared for these files THEN the repository has no defined requirement that the content be sourced from the existing local fixture text and generated locally without network retrieval or untracked external regulatory documents
1.5 WHEN `data/input/SAMPLE_DATA_README.md` references the three fixture filenames THEN those references describe files that are presented as PDFs but fail the file-format requirement

### Expected Behavior (Correct)

2.1 WHEN each of `data/input/hkma_capital_requirements.pdf`, `data/input/basel_iii_framework.pdf`, and `data/input/risk_weighted_assets.pdf` is inspected by file content THEN the file SHALL be a well-formed PDF with a `%PDF-` header and a matching PDF end marker, independent of its `.pdf` extension
2.2 WHEN `pypdf.PdfReader` opens any replacement fixture THEN it SHALL open without an exception, expose at least one page, and report a nonzero page count
2.3 WHEN text is extracted from each replacement fixture with `pypdf` THEN extraction SHALL return non-empty text that includes the document's existing local title and its documented subject matter: HKMA capital adequacy requirements for `hkma_capital_requirements.pdf`, Basel III international regulatory framework for `basel_iii_framework.pdf`, and risk-weighted-assets calculation methodology for `risk_weighted_assets.pdf`
2.4 WHEN replacement fixture content is created THEN it SHALL use the existing text payloads in the three repository files as the source content, render that content into PDFs through a deterministic local generation process, and require no network access, remote download, or external regulatory document at generation or validation time
2.5 WHEN the replacement fixtures are validated through the repository's PDF ingestion path THEN each SHALL be accepted by `PDFParser.parse_pdf`, produce at least one extracted chunk, and preserve page metadata sufficient for downstream ingestion
2.6 WHEN `data/input/SAMPLE_DATA_README.md` is checked after the replacement THEN it SHALL continue to reference the exact filenames `hkma_capital_requirements.pdf`, `basel_iii_framework.pdf`, and `risk_weighted_assets.pdf`, and its descriptions, key concepts, entities, and testing purpose for those files SHALL remain consistent with the extracted fixture text

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `data/input/sample.pdf` or `data/input/test_hkma_basel.pdf` is not part of this fixture correction THEN the system SHALL CONTINUE to preserve those files and their existing behavior
3.2 WHEN the parser processes an already valid PDF outside the three named fixtures THEN the system SHALL CONTINUE to open it, extract available page text, and produce chunks according to its existing configuration
3.3 WHEN the parser processes the corrected fixtures with normal chunking settings THEN the system SHALL CONTINUE to preserve the existing parser contract for non-empty text, one-based page numbers, document names, chunk identifiers, and source path metadata
3.4 WHEN the README is used to locate the sample regulatory documents THEN the system SHALL CONTINUE to use the same three filenames and SHALL NOT require callers or documentation users to migrate to renamed files
3.5 WHEN the corrected fixture content is compared with the current local text payloads THEN the system SHALL CONTINUE to preserve the substantive regulatory topics and representative values already documented, including capital ratios and buffers, liquidity and leverage requirements, and risk-weighted-assets methodologies
3.6 WHEN fixture validation is run in an environment without network access THEN the system SHALL CONTINUE to validate the three PDFs using only repository files and locally installed tooling
