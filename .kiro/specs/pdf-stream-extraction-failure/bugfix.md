# Bugfix Requirements Document

## Introduction

The PDF stream extraction flow produces documents that cannot be reliably opened as independent PDF files and can omit the required demo-only watermark and company disclaimer. Project documentation also contains stale or malformed `Last updated` metadata, including the November 2024 date. This bugfix shall preserve the existing extraction behavior while making every generated PDF independently openable, retaining the exact visible watermark and company disclaimer, and enforcing accurate update-date metadata. For this correction, the required update date is November 16, 2026.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a PDF is produced through the stream extraction flow and opened independently THEN the system can produce a malformed or incomplete PDF that the viewer cannot open as a standalone document
1.2 WHEN a PDF is produced through the stream extraction flow THEN the system can omit, alter, or fail to visibly render the exact watermark `fictional document. For Demo purpose only`
1.3 WHEN a README or PDF names a company THEN the document can omit the requested visible company disclaimer stating that company names are used for demonstration only and that the fictional document is not affiliated with, endorsed by, or representative of any named company
1.4 WHEN a project document, README, or PDF contains a case-insensitive `Last updated` or `last updated` date label THEN the document can retain a stale date such as November 2024 or a malformed date that does not provide an accurate month, day, and year

### Expected Behavior (Correct)

2.1 WHEN a PDF is produced through the stream extraction flow and opened independently THEN the system SHALL produce a complete, valid PDF that opens without relying on another file, stream, temporary state, or prior PDF
2.2 WHEN a PDF is produced through the stream extraction flow THEN the system SHALL visibly render the exact watermark `fictional document. For Demo purpose only`, preserving its spelling, capitalization, punctuation, and spacing
2.3 WHEN a README or PDF names a company THEN the document SHALL visibly include the disclaimer `Company names are used for demonstration only. This fictional document is not affiliated with, endorsed by, or representative of any named company.`
2.4 WHEN any project document, README, or PDF contains a case-insensitive `Last updated` or `last updated` date label THEN the system SHALL require a complete, valid month-day-year date, and for this correction the date SHALL be `November 16, 2026`
2.5 WHEN the documentation metadata check scans a project document, README, or PDF THEN it SHALL flag the document as invalid if a `Last updated` or `last updated` label has a missing month, day, or year, an invalid calendar date, an ambiguous or unsupported date format, or a date other than `November 16, 2026`; it SHALL pass the document only when every such label has the required accurate date
2.11 WHEN the upload API is refactored to return a `job_id` asynchronously, THEN every existing frontend upload caller and automated test SHALL poll the new status endpoint until completion or failure, surface job progress, and surface any diagnostic error message.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a PDF is generated from a non-stream source or an already valid extraction result THEN the system SHALL CONTINUE TO produce a valid PDF that opens independently
3.2 WHEN a PDF does not name a company THEN the system SHALL CONTINUE to omit the company-specific disclaimer while retaining any other required document content
3.3 WHEN a README or PDF names one or more companies THEN the system SHALL CONTINUE to show the requested company disclaimer together with the named-company content
3.4 WHEN a generated PDF is inspected for demo labeling THEN the system SHALL CONTINUE to show the exact visible watermark `fictional document. For Demo purpose only`
3.5 WHEN a project document, README, or PDF contains no `Last updated` or `last updated` label THEN the system SHALL CONTINUE to preserve its existing content without requiring an unrelated date
3.6 WHEN a project document, README, or PDF contains a valid `Last updated` or `last updated` label after this correction THEN the system SHALL CONTINUE to preserve the document content and SHALL retain the accurate date `November 16, 2026`
