# Implementation Plan

## Overview

This plan repairs the three malformed regulatory PDF fixtures through canonical local source capture and deterministic generation. Tasks are ordered so bug-condition and preservation tests establish behavior before implementation, followed by fix validation and an offline final checkpoint. The plan does not authorize changes during task creation; implementation work is limited to the files listed in the implementation tasks.

## Tasks

- [x] 1. Write the bug-condition exploration test before changing fixtures
  - **Property 1: Bug Condition** - Named regulatory fixtures are invalid PDF payloads
  - **IMPORTANT**: Write and run this test against the unfixed checkout before creating replacement PDFs or changing ingestion code.
  - Define `isBugCondition(input)` for the three named paths: `data/input/hkma_capital_requirements.pdf`, `data/input/basel_iii_framework.pdf`, and `data/input/risk_weighted_assets.pdf`; the condition is an invalid `%PDF-` signature, `pypdf.PdfReader` open failure, or missing/non-empty page extraction.
  - Assert that each current file begins with its plain-text title rather than `%PDF-`, and record the concrete `pypdf` reader failure and absence of PDF pages.
  - Capture each current UTF-8 payload exactly, including headings, percentages, named entities, section order, and ending lines, so the later canonical source fixtures can be checked against the pre-fix content.
  - Confirm the README identifies these paths as PDFs while the files fail the PDF-format check.
  - **EXPECTED OUTCOME**: The exploration test fails on the unfixed files with reproducible counterexamples; do not weaken the test or repair the files to make this first run pass.
  - Document the counterexamples in the test output or task notes, then retain the same test for post-fix verification.
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 2. Write preservation and regression property tests before implementing the fix
  - **Property 2: Preservation** - Existing names, parser contracts, README content, and unrelated PDFs remain stable
  - **IMPORTANT**: Follow observation-first methodology. Run these checks on the unfixed checkout and record the behavior that must remain unchanged.
  - Verify `data/input/SAMPLE_DATA_README.md` contains the exact three documented filenames, their existing subjects/key concepts, named entities, sample-query context, and ingestion instructions.
  - Verify `data/input/sample.pdf` and `data/input/test_hkma_basel.pdf` exist, are outside the named fixture mapping, and preserve their pre-fix bytes and existing readable-PDF/parser behavior.
  - Exercise `PDFParser.parse_pdf()` on an already valid PDF and assert the existing public contract: non-empty text, one-based page numbers, chunk identifiers, document name, source path metadata, character offsets, and configured chunk behavior.
  - Add a preservation check that the generator's output mapping cannot overwrite unrelated PDFs or change README/parser files.
  - Add an offline boundary check or mock proving preservation checks use repository files and locally installed tooling only; no download, OCR service, PDF service, or network request is allowed.
  - **EXPECTED OUTCOME**: Preservation tests pass on the unfixed checkout and establish the baseline to retain after fixture repair.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_

- [ ] 3. Repair the three invalid PDF fixtures with deterministic local generation

  - [x] 3.1 Capture canonical source fixtures and implement the generator
    - Create `data/input/fixture_sources/hkma_capital_requirements.txt`, `data/input/fixture_sources/basel_iii_framework.txt`, and `data/input/fixture_sources/risk_weighted_assets.txt` as byte-for-byte UTF-8 copies of the three pre-fix `.pdf` text payloads captured in task 1.
    - Add `tools/generate_sample_pdf_fixtures.py` using only Python standard-library modules. Define an explicit source-to-output mapping for exactly the three named PDFs and fail clearly for a missing source or unsupported mapping.
    - Preserve every source line, blank paragraph, heading, representative value, named entity, effective date, and conclusion. Normalize only CRLF/CR to LF for layout and wrap at fixed word boundaries without dropping source text.
    - Serialize a self-contained PDF 1.4 with fixed geometry, margins, Helvetica font settings, leading, page capacity, object order, escaped PDF strings, xref offsets, `%PDF-1.4` header, and terminal `%%EOF` marker.
    - Keep generation deterministic: omit timestamps, random identifiers, host paths, nondeterministic metadata, network access, remote downloads, and external regulatory content. Support an optional output directory for tests while defaulting to the existing `data/input/*.pdf` paths from the repository root.
    - _Bug_Condition: `isBugCondition(input)` from design for any named fixture with an invalid signature, unreadable PDF, or empty extraction.
    - _Expected_Behavior: `expectedBehavior(result)` requires a strict-readable PDF, at least one page, complete normalized source extraction, and local deterministic reproduction.
    - _Preservation: Keep `SAMPLE_DATA_README.md`, `src/ingestor/pdf_parser.py`, unrelated PDFs, ontology data, and ingestion configuration unchanged.
    - _Requirements: 1.4, 2.1, 2.2, 2.3, 2.4, 3.6_

  - [x] 3.2 Generate replacements only for the named fixture paths
    - Run the generator once after canonical source capture to replace `data/input/hkma_capital_requirements.pdf`, `data/input/basel_iii_framework.pdf`, and `data/input/risk_weighted_assets.pdf` with generated PDFs.
    - Confirm the generator writes no other tracked file and does not rename the fixtures, edit the README, modify `src/ingestor/pdf_parser.py`, or rewrite `data/input/sample.pdf` or `data/input/test_hkma_basel.pdf`.
    - Verify extracted text retains the required subject matter and markers: HKMA capital adequacy and `4.5%`, `6.0%`, `8.0%`, `2.5%`, `3%`, `100%`; Basel III international requirements, `72.5%`, `G-SIBs`, and `D-SIBs`; and risk-weighted-assets credit, market, and operational risk with `PD`, `LGD`, `EAD`, `15%`, and `1,250%`.
    - _Bug_Condition: The three existing named files are plain-text payloads under `.pdf` names and fail the PDF ingestion path.
    - _Expected_Behavior: Each existing filename points to a valid, self-contained, extractable PDF generated from its matching canonical local source.
    - _Preservation: Preserve the documented filenames and the complete substantive regulatory payloads rather than substituting abbreviated or externally sourced documents.
    - _Requirements: 2.1, 2.3, 2.4, 2.6, 3.4, 3.5_

  - [x] 3.3 Add and run focused fix-validation and deterministic-generation tests
    - Add `tests/unit/test_sample_pdf_fixtures.py` with reusable fixture metadata, source normalization, PDF validation helpers, and document-specific marker assertions.
    - Validate each checked-in replacement has a `%PDF-1.4` header, terminal `%%EOF`, strict `pypdf.PdfReader` opening without exception, at least one page, non-empty extraction, and normalized extracted text equal to the corresponding canonical source text in the same order.
    - Run `PDFParser.parse_pdf()` for all three replacements with default settings and assert non-empty chunks, one-based pages, positive page text, correct `document_name`, matching document metadata, chunk identifiers, offsets, and sufficient page metadata.
    - Generate each fixture twice into separate temporary directories and assert byte-for-byte equality, equal SHA-256 digests, and equal normalized extraction. Assert a changed source changes the output digest and extracted text.
    - Test source escaping and page-boundary behavior with local generated inputs containing parentheses, backslashes, blank lines, and varying line lengths; ensure no source line disappears and page order remains stable.
    - Test missing-source and unsupported-mapping failures, and verify the focused module runs without Ollama, spaCy downloads, network access, or full application startup.
    - _Bug_Condition: Every named fixture that previously satisfied `isBugCondition(input)` must satisfy the fixed PDF structure, extraction, and parser acceptance properties.
    - _Expected_Behavior: The repaired files are strict-readable, content-complete, deterministic PDFs that yield valid parser chunks.
    - _Preservation: The README references, parser contract, unrelated fixtures, and offline behavior remain unchanged.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5, 3.6_

  - [x] 3.4 Verify the bug-condition exploration test now passes
    - **Property 1: Expected Behavior** - Named fixtures are valid and extractable PDFs
    - Re-run the exact exploration test from task 1; do not write a replacement test.
    - Confirm all three named paths now satisfy the expected behavior: valid signature/trailer, strict reader opening, nonzero pages, non-empty complete normalized source extraction, required regulatory markers, and at least one `PDFChunk` with one-based page metadata.
    - **EXPECTED OUTCOME**: The same test that failed on the unfixed checkout passes after generation, demonstrating that every scoped counterexample is repaired.
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [~] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing names, parser contracts, README content, and unrelated PDFs remain stable
    - Re-run the exact preservation tests from task 2; do not write replacement tests.
    - Confirm the README still resolves the same three filenames, parser behavior and metadata semantics remain compatible, unrelated PDFs remain unchanged and readable, and no network access is required.
    - **EXPECTED OUTCOME**: All preservation tests pass after the repair, demonstrating no regression outside the bug condition.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_

- [~] 4. Checkpoint - Perform final local verification
  - Depends on tasks 1 through 3.5 being complete.
  - Run the focused fixture test module, the bug-condition exploration test, the preservation property tests, and the relevant existing parser tests in one offline-capable test command.
  - Inspect the final change set to confirm it contains only the three canonical source fixtures, the deterministic generator, focused regression tests, and the three repaired PDF artifacts; no README, parser, unrelated PDF, or application implementation changes are included.
  - Verify all three README-referenced paths resolve, strict PDF validation succeeds, normalized source parity holds, `PDFParser.parse_pdf()` produces valid chunks, deterministic regeneration remains byte-identical, and all preservation checks pass.
  - Record the final test command and results, including any environment limitation that prevents local validation.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

## Notes

- Dependencies are explicit: task 1 captures the bug and source payloads; task 2 records preservation baselines; task 3 depends on both; task 3.4 and task 3.5 reuse the exact pre-fix tests; task 4 depends on all prior tasks.
- This artifact only defines coding and test activities. It does not modify implementation files or PDF fixtures while the task plan is being created.
- The canonical sources and generated PDFs are fixture artifacts, not authoritative live regulatory publications; generation and validation must remain local and offline.
