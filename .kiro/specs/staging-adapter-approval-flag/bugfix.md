# Bugfix Requirements Document

## Introduction

The Surgeon’s Table extraction flow fails when the staging adapter is constructed with the `require_human_approval` setting. `StagingManager` is aliased to `CompatibleStagingManager` in `src/ingestor/staging_adapter.py`, but the adapter constructor does not accept that keyword even though the underlying comprehensive staging manager supports it. The failure prevents users from starting PDF extraction and must be corrected without breaking existing staging-manager callers or approval behavior.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the Surgeon’s Table starts extraction and the aliased `StagingManager` is constructed with `require_human_approval` THEN the system raises a `TypeError` because `CompatibleStagingManager.__init__` rejects the keyword argument
1.2 WHEN a caller needs to configure human-approval behavior through the staging adapter THEN the system cannot pass the setting through the compatibility layer to the underlying comprehensive staging manager

### Expected Behavior (Correct)

2.1 WHEN the aliased `StagingManager` or `CompatibleStagingManager` is constructed with `require_human_approval` set to `True` or `False` THEN the system SHALL accept the keyword without raising a constructor error
2.2 WHEN the adapter receives `require_human_approval` THEN the system SHALL store or pass the exact boolean setting cleanly to the underlying comprehensive staging manager so that its approval workflow uses the requested mode
2.3 WHEN the adapter is constructed without `require_human_approval` THEN the system SHALL default the setting to `True`, preserving the human-approval requirement for existing HITL callers
2.4 WHEN the Surgeon’s Table starts extraction with the staging adapter configured for human approval THEN the system SHALL initialize the ingestion pipeline and proceed without the unexpected-keyword exception

### Unchanged Behavior (Regression Prevention)

3.1 WHEN existing callers construct the aliased `StagingManager` with only a staging path or with no arguments THEN the system SHALL CONTINUE TO construct a compatible staging manager using the default human-approval setting
3.2 WHEN callers use the adapter’s record, review, statistics, approval, editing, export, or reset methods THEN the system SHALL CONTINUE TO provide the existing compatibility behavior and delegate comprehensive operations to the underlying manager
3.3 WHEN `require_human_approval` is `True` THEN the system SHALL CONTINUE to keep valid extracted triples pending until an explicit review or approval action occurs
3.4 WHEN `require_human_approval` is `False` THEN the system SHALL CONTINUE to allow the underlying comprehensive manager’s existing non-human-approval behavior for valid triples
3.5 WHEN the full test suite is run with `pytest -q` after the fix THEN the system SHALL CONTINUE to pass all existing tests
