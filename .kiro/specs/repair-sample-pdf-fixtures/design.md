# Repair Sample PDF Fixtures Bugfix Design

## Overview

The three files named in `data/input/SAMPLE_DATA_README.md` are currently UTF-8/ASCII text files with `.pdf` extensions. They contain the intended sample regulatory text, but they do not contain a PDF header, object structure, page tree, or extractable page content. As a result, the repository's `pypdf`-based ingestion path cannot open them.

The fix will preserve the existing filenames and the complete local text payloads while replacing only the malformed file format. The current text payloads will first become canonical UTF-8 source fixtures under `data/input/fixture_sources/`. A new standard-library-only generator will render those sources into deterministic, text-based PDF 1.4 files at the existing paths. The generator will use fixed page dimensions, margins, font, line width, page capacity, object ordering, and PDF serialization. It will not use timestamps, random identifiers, downloaded documents, network access, or external regulatory content. The parser and the README's three PDF references will not be changed.

## Glossary

- **Bug_Condition (C)**: A named sample fixture is not a readable PDF, or its PDF extraction does not expose the intended local regulatory text.
- **Property (P)**: Every named fixture is a structurally valid, locally generated PDF that `pypdf` can open and whose extracted text retains the corresponding source document content and subject matter.
- **Preservation**: Existing parser behavior, chunk metadata, the other sample PDFs, the three documented filenames, and the README descriptions remain unchanged.
- **Canonical source fixture**: A UTF-8 text file containing the exact payload currently stored in one of the malformed `.pdf` files. It is the auditable input for regeneration.
- **Fixture generator**: `tools/generate_sample_pdf_fixtures.py`, a deterministic local utility that converts canonical source text into PDF page content.
- **Named fixtures**: `data/input/hkma_capital_requirements.pdf`, `data/input/basel_iii_framework.pdf`, and `data/input/risk_weighted_assets.pdf`.
- **`PDFParser`**: `src/ingestor/pdf_parser.py`'s existing `pypdf` parser and chunker. Its implementation is outside the scope of this fix.
- **Normalized extraction**: Text comparison after normalizing line endings and collapsing runs of whitespace to one space. This accounts for PDF line and page boundaries without discarding words, values, or punctuation.

## Bug Details

### Bug Condition

The bug occurs for a path in the named fixture set when the file is the current plain-text payload rather than a PDF, or when a replacement PDF does not preserve usable extracted content. The filename alone is insufficient to identify the format: the current files begin with document titles instead of `%PDF-` and therefore cannot be consumed by `pypdf.PdfReader`.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input containing path, bytes, and optional PDF extraction result
  OUTPUT: boolean

  namedFixture := input.path IN {
    "data/input/hkma_capital_requirements.pdf",
    "data/input/basel_iii_framework.pdf",
    "data/input/risk_weighted_assets.pdf"
  }

  invalidSignature := NOT input.bytes STARTS_WITH "%PDF-"
  unreadable := input.pdfReaderOpenFailed
  missingExtraction := input.pageCount < 1 OR input.normalizedExtractedText IS EMPTY

  RETURN namedFixture AND (invalidSignature OR unreadable OR missingExtraction)
END FUNCTION
```

The fixed artifacts will be generated from the local source text rather than obtained from live HKMA, Basel Committee, or Financial Stability Board publications. The fixtures are test data, not authoritative production legal documents.

### Examples

- **HKMA fixture, current defect:** `data/input/hkma_capital_requirements.pdf` begins with `HKMA Supervisory Policy Manual SA-2: Capital Adequacy Requirements`, not `%PDF-`. `PdfReader` cannot open it as a PDF. After the fix, extraction will include the title, HKMA identity, the 4.5% CET1, 6.0% Tier 1, 8.0% total capital, 2.5% conservation buffer, 3% leverage, and 100% liquidity requirements already present in the source payload.
- **Basel III fixture, current defect:** `data/input/basel_iii_framework.pdf` is a long ASCII text document despite its extension. The replacement will retain its existing capital buffers, 3% leverage ratio, 100% LCR and NSFR, risk coverage, G-SIB/D-SIB, 72.5% output floor, and implementation timeline text in extractable PDF pages.
- **Risk-weighted-assets fixture, current defect:** `data/input/risk_weighted_assets.pdf` begins with `Risk-Weighted Assets: Calculation Methodology and Regulatory Requirements` rather than a PDF signature. The replacement will retain the source's credit, market, and operational risk methodologies, exposure risk weights, internal-model approaches, securitization, counterparty risk, mitigation, reporting, and validation sections.
- **Page and chunk boundary example:** A source paragraph that crosses a deterministic page boundary may be extracted with a newline between lines or pages. Normalized source parity must still hold, and `PDFParser.parse_pdf()` must return non-empty chunks with one-based page numbers and the existing document name and metadata fields.
- **Out-of-scope example:** `data/input/sample.pdf` and `data/input/test_hkma_basel.pdf` are not rewritten, renamed, or regenerated by this fix. Their existing parser behavior remains covered by preservation checks.

## Expected Behavior

### Correct Behavior

The fixed artifacts must satisfy all of the following:

- Each named path contains a well-formed PDF with a `%PDF-1.4` header and a terminal `%%EOF` marker.
- `pypdf.PdfReader` opens each artifact in strict validation mode without an exception and exposes at least one page.
- Every artifact has non-empty extracted text. Normalized extracted text contains the complete normalized canonical source text in the same order, so no source paragraphs, representative values, headings, or conclusions are silently removed.
- The extracted text retains the README's intended subject matter: HKMA capital adequacy, Basel III international requirements, and risk-weighted-assets calculation methodology.
- `PDFParser.parse_pdf()` accepts each artifact and returns at least one `PDFChunk` with the existing chunk fields, one-based page number, correct filename in `document_name` and metadata, and page metadata sufficient for downstream ingestion.
- Re-running generation from unchanged canonical sources produces byte-identical PDFs.

The expected correct behavior is formalized as the bug-condition property in the Correctness Properties section below.

### Preservation Requirements

**Unchanged Behaviors:**

- `data/input/SAMPLE_DATA_README.md` continues to reference the exact filenames `hkma_capital_requirements.pdf`, `basel_iii_framework.pdf`, and `risk_weighted_assets.pdf`.
- The README's descriptions, key concepts, named entities, testing purposes, sample queries, and ingestion instructions remain consistent with the extracted fixture content. No caller needs to migrate to a new filename.
- `src/ingestor/pdf_parser.py` is not modified. Existing defaults remain `chunk_size=1000`, `chunk_overlap=200`, whitespace cleanup enabled, and one-based page numbers.
- The parser continues to expose `PDFChunk.id`, `text`, `page_number`, `chunk_index`, `total_chunks`, `metadata`, character offsets, `document_id`, and `document_name` with the same semantics.
- Existing valid PDFs continue to be opened, have available page text extracted, and be chunked according to the current parser configuration.
- `data/input/sample.pdf` and `data/input/test_hkma_basel.pdf` remain unchanged and continue to follow their existing behavior.
- Generation and validation remain air-gapped. No network request, remote download, system PDF service, OCR service, or external regulatory document is required.

**Scope:**

Only the three malformed named fixtures, their canonical local source copies, the deterministic generator, and focused regression tests are in scope. README references and parser/ingestion code are intentionally preserved. A source change is not a reason to rewrite the README or to broaden the fix to unrelated PDFs.

## Hypothesized Root Cause

1. **Incorrect file payload under a PDF extension**: The three files were created as plain text but named with `.pdf`, so their first bytes are document text rather than a PDF header.

2. **No reproducible fixture build step**: The repository contains no generator or canonical source location that defines how the sample PDFs should be recreated. The original text payloads therefore cannot be validated as PDF artifacts or regenerated deterministically.

3. **Format and extraction were not checked together**: Existing documentation describes PDF ingestion, but the fixture creation path did not verify both PDF structure and `pypdf` text extraction before the files were treated as ready.

4. **Potential content drift during a naive replacement**: Replacing the files with abbreviated or externally downloaded regulatory documents could make the filenames valid while breaking README concepts, evidence examples, and existing local test expectations. The canonical source parity check is needed to prevent that regression.

## Correctness Properties

Property 1: Bug Condition - Named Fixtures Are Valid and Extractable PDFs

_For any_ input path in the named fixture set where `isBugCondition(input)` returns true, the fixed artifact SHALL be generated from its canonical local source, open successfully with strict `pypdf.PdfReader`, contain at least one page, expose non-empty extracted text containing the complete normalized source payload and document-specific regulatory markers, and produce at least one chunk through `PDFParser.parse_pdf()`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.5**

Property 2: Preservation - Existing Names, Content, and Ingestion Contracts Remain Stable

_For any_ input that does not satisfy `isBugCondition(input)`, the fixed change SHALL preserve the original behavior, including README lookup by the three existing filenames, parser chunking and metadata semantics for valid PDFs, the two unrelated sample PDFs, and the substantive regulatory topics and values represented by the local source payloads.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 3: Deterministic Offline Fixture Reproduction

_For any_ unchanged canonical source fixture and fixed generator configuration, running the generator in an environment without network access SHALL produce byte-identical PDF bytes and normalized extracted text, with no dependency on timestamps, random identifiers, current working directory, or remote content.

**Validates: Requirements 2.4, 3.6**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct:

**Files**:

- `data/input/fixture_sources/hkma_capital_requirements.txt`
- `data/input/fixture_sources/basel_iii_framework.txt`
- `data/input/fixture_sources/risk_weighted_assets.txt`
- `tools/generate_sample_pdf_fixtures.py`
- `tests/unit/test_sample_pdf_fixtures.py`
- `data/input/hkma_capital_requirements.pdf`
- `data/input/basel_iii_framework.pdf`
- `data/input/risk_weighted_assets.pdf`

**Specific Changes**:

1. **Capture canonical local source text**: Before overwriting the malformed `.pdf` files, copy each current file's UTF-8 text payload byte-for-byte into the corresponding `.txt` source file. The generator will treat these files as authoritative and will fail if a source is missing. The text content, section order, headings, percentages, named entities, effective dates, and conclusions will not be rewritten or fetched from the internet.

2. **Implement a deterministic standard-library PDF writer**: Add `tools/generate_sample_pdf_fixtures.py` with an explicit mapping from each output PDF to its source text and document metadata. Read UTF-8 text, normalize only CRLF/CR to LF for layout, preserve every non-empty source line and blank paragraph, and wrap only at fixed word boundaries. Use fixed page geometry, margins, font (`Helvetica`), font size, leading, line width, and lines per page. Use a small PDF 1.4 serializer built from the Python standard library to emit a catalog, pages tree, page objects, font resource, and text content streams with escaped PDF string literals.

3. **Make output reproducible**: Serialize objects in a fixed order, calculate xref offsets from the exact bytes being written, and omit timestamps, random IDs, host paths, and nondeterministic metadata. The command will accept an optional output directory for tests but will default to the three existing `data/input/*.pdf` paths when run from the repository root. It will write only the named outputs and report the source-to-output mapping.

4. **Replace only the malformed artifacts**: Run the generator once to replace the three current ASCII payload files with generated PDFs. Do not change `data/input/SAMPLE_DATA_README.md`, `src/ingestor/pdf_parser.py`, other PDFs, ontology data, or ingestion configuration. The README will continue to point to the same paths.

5. **Add focused fixture checks**: Add `tests/unit/test_sample_pdf_fixtures.py` with reusable fixture metadata, source normalization, and PDF validation helpers. Tests will check signature/trailer, strict reader opening, page count, normalized source parity, document-specific markers, deterministic regeneration, README references, and direct `PDFParser` chunk output. Tests will not call the full Ollama/spaCy pipeline because this bug concerns local PDF format and parser ingestion, not model-backed extraction.

6. **Keep generation and checks local**: The generator must import only Python standard-library modules. Validation may use the already-declared `pypdf`, `pytest`, and repository `PDFParser`; it must not download dependencies or retrieve source documents. A test can run the generator twice into separate temporary directories and compare bytes and SHA-256 digests without modifying tracked fixtures.

### Generation and Content Details

The generator's content contract will be explicit:

- **HKMA source**: Preserve the full current text beginning with `HKMA Supervisory Policy Manual SA-2: Capital Adequacy Requirements` and ending with `Revision: SA-2.5`. Required extraction markers include `4.5%`, `6.0%`, `8.0%`, `2.5%`, `3%`, `100%`, `Hong Kong Monetary Authority`, and `authorized institutions`.
- **Basel III source**: Preserve the full current text beginning with `Basel III: International Regulatory Framework for Banks` and ending with the publication/effective-date lines. Required extraction markers include `Basel Committee on Banking Supervision`, `4.5%`, `6.0%`, `8.0%`, `2.5%`, `3%`, `100%`, `72.5%`, `G-SIBs`, and `D-SIBs`.
- **Risk-weighted-assets source**: Preserve the full current text beginning with `Risk-Weighted Assets: Calculation Methodology and Regulatory Requirements` and ending with its effective-date line. Required extraction markers include `credit risk`, `market risk`, `operational risk`, `PD`, `LGD`, `EAD`, `15%`, `1,250%`, `Financial Stability Board`, and `Basel Committee on Banking Supervision`.

The marker assertions supplement, rather than replace, normalized full-source parity. Full parity catches omissions that a short list of key phrases could miss.

## Testing Strategy

### Validation Approach

The testing strategy follows the bug-condition workflow: establish the malformed-file counterexample, generate local replacements from the canonical source files, verify PDF structure and extraction, then check that README references and existing parser behavior remain unchanged. Tests are deterministic and do not require Ollama, spaCy model downloads, network access, or a full application startup.

### Exploratory Bug Condition Checking

**Goal**: Confirm the original defect before replacing the artifacts and record the concrete failure mode.

**Test Plan**: On the pre-fix checkout, inspect the first bytes of each named path, assert that they do not begin with `%PDF-`, and attempt `PdfReader` opening. Record that the files are rejected as PDFs. Also compare their current bytes with the captured canonical source files to establish that the payload is valuable text rather than disposable corruption.

**Test Cases**:

1. **Signature counterexample**: Each pre-fix file begins with its document title rather than `%PDF-`.
2. **Reader counterexample**: `PdfReader` cannot open each pre-fix file as a PDF.
3. **Content capture check**: Each pre-fix file's decoded text is copied exactly into its matching canonical source file before replacement.
4. **README mismatch check**: The README identifies these files as PDF documents even though their contents are plain text.

**Expected Counterexamples**:

- `file`-style content inspection reports ASCII text, not PDF data.
- `pypdf.PdfReader` raises while opening the malformed files.
- No page count or PDF page text can be obtained from the pre-fix payload.

### Fix Checking

**Goal**: Verify that every input satisfying the bug condition is repaired without loss of the intended local content.

**Pseudocode:**

```
FOR ALL path IN namedFixtures DO
  source := readUtf8(canonicalSourceFor(path))
  pdfBytes := readBytes(path)
  reader := PdfReader(path, strict=True)
  extracted := normalize(join(page.extract_text() FOR page IN reader.pages))

  ASSERT pdfBytes STARTS_WITH "%PDF-"
  ASSERT pdfBytes contains terminal "%%EOF"
  ASSERT len(reader.pages) >= 1
  ASSERT extracted == normalize(source)
  ASSERT PDFParser().parse_pdf(path) contains at least one chunk
  ASSERT every returned chunk.page_number >= 1
END FOR
```

**Fix Test Cases**:

1. Validate the PDF header, EOF marker, strict reader opening, page count, and non-empty extraction for all three outputs.
2. Compare normalized extracted text against the corresponding canonical source and assert document-specific markers.
3. Parse each output through `PDFParser.parse_pdf()` with default settings and assert non-empty chunks, filename/document metadata, one-based pages, and positive page text lengths.
4. Generate each fixture twice into separate temporary output directories and assert byte-for-byte equality and equal SHA-256 digests.

### Preservation Checking

**Goal**: Verify that all inputs outside the bug condition retain the behavior and interfaces that existed before the fixture replacement.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalParserContract(input) == fixedParserContract(input)
  ASSERT read(SAMPLE_DATA_README.md) contains all original named PDF references
  ASSERT unrelated fixture bytes and paths are unchanged
END FOR
```

**Testing Approach**: Keep the parser implementation unchanged and test its public outputs around the newly valid artifacts. Use source parity and README assertions to detect content or documentation drift. For unrelated valid PDFs, run the same parser acceptance check without rewriting or comparing their binary payloads. Use property-based generation for source/layout variations and deterministic serialization, while keeping the checked-in fixture tests focused on the three named files.

**Preservation Test Cases**:

1. **README path preservation**: Read `data/input/SAMPLE_DATA_README.md` and assert the exact three filenames plus their documented subjects and key concepts remain present.
2. **Parser contract preservation**: Assert each corrected fixture still returns the existing `PDFChunk` fields, `document_name == path.name`, matching metadata document name/id, one-based page numbers, valid offsets, and configured chunk behavior.
3. **Unrelated fixture preservation**: Confirm `data/input/sample.pdf` and `data/input/test_hkma_basel.pdf` still exist, are not outputs of the generator, and remain readable by the existing parser contract.
4. **Offline preservation**: Run generation and all fixture validation with network access unavailable or mocked at the network boundary; no network call should be made.

### Unit Tests

- Test the three fixture mappings and canonical source files exist with UTF-8 text.
- Test `%PDF-1.4` headers, terminal `%%EOF`, strict `PdfReader` opening, nonzero page counts, and non-empty page extraction.
- Test normalized extracted text equals normalized canonical source text for each document.
- Test required HKMA, Basel III, and RWA markers, including the documented percentages and risk categories.
- Test deterministic generation by comparing bytes and digests from two temporary output runs.
- Test the generator rejects a missing source or an unsupported fixture mapping rather than silently producing an incomplete PDF.
- Test README filename and subject/key-concept references remain unchanged.

### Property-Based Tests

- Generate ASCII source lines containing parentheses, backslashes, blank lines, and variable line lengths, then verify the PDF string escaping and normalized extraction preserve the generated source text.
- Generate source documents with varying numbers of lines around page-capacity boundaries and verify every generated page is readable, page order is stable, and no source line disappears.
- Generate repeated runs from the same source/configuration and assert identical serialized bytes, while changing the source asserts a changed digest and changed extracted text.
- Generate valid non-bug inputs outside the named fixture mapping and verify the generator does not overwrite unrelated paths.

### Integration Tests

- Run `PDFParser.parse_pdf()` on all three checked-in PDFs and verify at least one chunk per document, correct filename/document metadata, one-based page numbers, and non-empty text.
- Run the parser's streaming path on the corrected PDFs and verify it emits the same ordered page/chunk text contract without changing parser code.
- Verify README-discovered paths resolve to the corrected files and can be parsed without renaming or caller migration.
- Confirm `data/input/sample.pdf` and `data/input/test_hkma_basel.pdf` remain available and pass their pre-existing valid-PDF/parser checks.
- Run the focused test module from an offline environment; the checks must complete using repository files and installed local tooling only.
