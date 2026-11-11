"""
Staging Adapter for backward compatibility between old and new StagingManager.

This module provides adapter classes to ensure the comprehensive StagingManager
is compatible with existing code that expects the simpler StagingManager from pipeline.py.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .pipeline import StagingRecord, ValidationStatus
from ..staging_manager import StagingManager, StagingTriple, ApprovalDecision

logger = logging.getLogger(__name__)


class CompatibleStagingManager:
    """Adapter that makes the comprehensive StagingManager compatible with existing code."""
    
    def __init__(self, staging_path: Optional[Path] = None):
        """Initialize compatible staging manager.
        
        Args:
            staging_path: Path to staging data
        """
        self.comprehensive_manager = StagingManager(
            staging_path,
            require_human_approval=True,
        )
        self.staging_path = staging_path
        self.staging_records: Dict[str, StagingRecord] = {}
        
        logger.info(f"CompatibleStagingManager initialized with comprehensive backend")
    
    def add_record(self, record: StagingRecord) -> str:
        """Add a staging record (compatible with existing code).
        
        Args:
            record: StagingRecord from pipeline
            
        Returns:
            Record ID
        """
        # Convert StagingRecord to StagingTriple
        staging_triple = StagingTriple(record.triple)
        
        # Valid candidates stay pending in compliance mode. The optional UI
        # auto-approval action remains an explicit, attributed reviewer action.
        # Add to comprehensive manager
        record_id = self.comprehensive_manager.add_triple_for_staging(
            triple=staging_triple,
            validation_status=record.validation_status,
            validation_messages=record.validation_messages,
            provenance_record=record.provenance_record,
        )
        
        # Also maintain backward compatibility storage
        self.staging_records[record_id] = record
        
        logger.debug(f"Added compatible record {record_id} with status {record.validation_status}")
        return record_id
    
    def get_pending_review(self) -> List[StagingRecord]:
        """Get records pending human review (compatible with existing code).
        
        Returns:
            List of StagingRecord objects
        """
        # Get pending from comprehensive manager
        pending_triples = self.comprehensive_manager.get_pending_review()
        
        # Convert back to StagingRecord format
        pending_records = []
        
        for record_id, staging_triple in pending_triples:
            # Create StagingRecord from StagingTriple
            record = StagingRecord(
                triple=staging_triple.triple,
                validation_status=ValidationStatus.QUARANTINED,  # Default to quarantined for pending
                validation_messages=["Pending human review"],
                provenance_record=None,  # Would need to reconstruct from metadata
                quarantine_reason="Pending human review",
                reviewed=False,
                reviewed_by=None,
                review_timestamp=None,
                metadata=staging_triple.metadata,
            )
            pending_records.append(record)
        
        return pending_records
    
    def mark_as_reviewed(self, record_id: str, reviewer: str, decision: ValidationStatus) -> bool:
        """Mark a record as reviewed (compatible with existing code).
        
        Args:
            record_id: Record identifier
            reviewer: Reviewer name/ID
            decision: Final validation decision
            
        Returns:
            True if successful, False otherwise
        """
        # Map ValidationStatus to ApprovalDecision
        approval_decision = None
        if decision == ValidationStatus.VALID:
            approval_decision = ApprovalDecision.APPROVED
        elif decision in [ValidationStatus.QUARANTINED, ValidationStatus.INVALID]:
            approval_decision = ApprovalDecision.REJECTED
        
        if approval_decision:
            # Use comprehensive manager's approve_triple method
            success = self.comprehensive_manager.approve_triple(
                record_id=record_id,
                reviewer=reviewer,
                edited_triple=None,
                rejection_reason=f"Marked as {decision.value} by {reviewer}",
            )
            
            if success and record_id in self.staging_records:
                # Update local record
                record = self.staging_records[record_id]
                record.reviewed = True
                record.reviewed_by = reviewer
                record.review_timestamp = datetime.now()
                record.validation_status = decision
            
            return success
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get staging manager statistics (compatible with existing code).
        
        Returns:
            Dictionary with statistics
        """
        # Get stats from comprehensive manager
        comprehensive_stats = self.comprehensive_manager.get_stats()
        
        # Map to compatible format
        status_counts = {}
        for status_key, count in comprehensive_stats.get("status_counts", {}).items():
            # Map approval status to validation status
            if status_key in ["approved", "edited_and_approved"]:
                val_status = ValidationStatus.VALID.value
            elif status_key == "rejected":
                val_status = ValidationStatus.QUARANTINED.value
            else:  # pending
                val_status = ValidationStatus.PENDING_REVIEW.value
            
            status_counts[val_status] = status_counts.get(val_status, 0) + count
        
        return {
            "total_records": comprehensive_stats.get("total_triples", 0),
            "status_counts": status_counts,
            "pending_review": comprehensive_stats.get("pending_review", 0),
            "staging_path": str(self.staging_path),
        }
    
    # Proxy methods to comprehensive manager for new functionality
    def approve_triple(self, *args, **kwargs):
        """Proxy to comprehensive manager's approve_triple method."""
        return self.comprehensive_manager.approve_triple(*args, **kwargs)
    
    def get_approved_triples(self):
        """Proxy to comprehensive manager's get_approved_triples method."""
        return self.comprehensive_manager.get_approved_triples()
    
    def get_rejected_triples(self):
        """Proxy to comprehensive manager's get_rejected_triples method."""
        return self.comprehensive_manager.get_rejected_triples()
    
    def edit_triple(self, *args, **kwargs):
        """Proxy to comprehensive manager's edit_triple method."""
        return self.comprehensive_manager.edit_triple(*args, **kwargs)
    
    def export_approved_kg(self, *args, **kwargs):
        """Proxy to comprehensive manager's export_approved_kg method."""
        return self.comprehensive_manager.export_approved_kg(*args, **kwargs)
    
    def reset_staging(self, *args, **kwargs):
        """Proxy to comprehensive manager's reset_staging method."""
        return self.comprehensive_manager.reset_staging(*args, **kwargs)


def get_staging_manager(staging_path: Optional[Path] = None, use_comprehensive: bool = True):
    """Factory function to get appropriate StagingManager.
    
    Args:
        staging_path: Path to staging data
        use_comprehensive: Whether to use comprehensive StagingManager (True) or simple one (False)
        
    Returns:
        StagingManager instance
    """
    if use_comprehensive:
        logger.info("Using comprehensive StagingManager with backward compatibility")
        return CompatibleStagingManager(staging_path)
    else:
        logger.info("Using simple StagingManager from pipeline")
        from .pipeline import StagingManager as SimpleStagingManager
        return SimpleStagingManager(staging_path)


# For direct import convenience
StagingManager = CompatibleStagingManager

