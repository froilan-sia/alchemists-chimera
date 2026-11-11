"""
Staging Manager for Alchemist's Chimera Hybrid RAG Engine

Provides comprehensive HITL (Human-In-The-Loop) workflow management for triple approval,
including live reload functionality, transaction semantics, and proper RDFLib handling.

Key Features:
1. Live Reload Functionality: approve_triple() triggers live reload on active GraphStore instance
2. Consistent Model Fields: Uses ExtractedTriple consistently to avoid AttributeError mismatches
3. HITL Workflow: Approval workflow with user attribution, triple editing, rejection tracking
4. Transaction Semantics: Rollback support for approval operations
5. Proper RDFLib Handling: Namespace binding as in Provenance Manager
6. TTL Serialization: Merge approved triples into knowledge graph with proper Turtle serialization
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import copy

# RDFLib imports for proper namespace handling
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD
from rdflib.namespace import RDF, RDFS, XSD

# Local imports
from .ingestor.triple_extractor import ExtractedTriple
from .ingestor.pipeline import ValidationStatus, StagingRecord
from .ingestor.provenance_manager import ProvenanceManager, ProvenanceRecord
from .graph_store import GraphStore, get_graph_store
from .config import settings

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """Decision types for triple approval."""
    
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED_AND_APPROVED = "edited_and_approved"


class StagingTriple:
    """Wrapper for ExtractedTriple with staging-specific metadata.
    
    This ensures consistent field access and avoids AttributeError mismatches.
    """
    
    def __init__(self, extracted_triple: ExtractedTriple):
        """Initialize with an ExtractedTriple."""
        self.triple = extracted_triple
        self.chunk_id = extracted_triple.chunk_id
        self.subject = extracted_triple.subject
        self.predicate = extracted_triple.predicate
        self.object = extracted_triple.object
        self.evidence = extracted_triple.evidence
        self.confidence = extracted_triple.confidence
        self.entity_anchors = extracted_triple.entity_anchors
        self.metadata = extracted_triple.metadata
        self.extraction_timestamp = extracted_triple.extraction_timestamp
        
        # Staging-specific fields
        self.approval_status: Optional[ApprovalDecision] = None
        self.reviewed_by: Optional[str] = None
        self.review_timestamp: Optional[datetime] = None
        self.edit_history: List[Dict[str, Any]] = []
        self.rejection_reason: Optional[str] = None
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "triple": self.triple.to_json() if hasattr(self.triple, 'to_json') else {},
            "chunk_id": self.chunk_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "entity_anchors": self.entity_anchors,
            "metadata": self.metadata,
            "extraction_timestamp": self.extraction_timestamp.isoformat(),
            "approval_status": self.approval_status.value if self.approval_status else None,
            "reviewed_by": self.reviewed_by,
            "review_timestamp": self.review_timestamp.isoformat() if self.review_timestamp else None,
            "edit_history": self.edit_history,
            "rejection_reason": self.rejection_reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StagingTriple':
        """Create StagingTriple from dictionary."""
        # Create ExtractedTriple from nested data
        triple_data = data.get("triple", {})
        extracted_triple = ExtractedTriple(
            subject=triple_data.get("subject", data.get("subject", "")),
            predicate=triple_data.get("predicate", data.get("predicate", "")),
            object=triple_data.get("object", data.get("object", "")),
            evidence=triple_data.get("evidence", data.get("evidence", "")),
            confidence=triple_data.get("confidence", data.get("confidence", 0.0)),
            chunk_id=triple_data.get("chunk_id", data.get("chunk_id", "")),
            entity_anchors=triple_data.get("entity_anchors", data.get("entity_anchors", [])),
            metadata=triple_data.get("metadata", data.get("metadata", {})),
            extraction_timestamp=datetime.fromisoformat(
                triple_data.get("extraction_timestamp", data.get("extraction_timestamp"))
            ) if triple_data.get("extraction_timestamp") or data.get("extraction_timestamp") else datetime.now(),
        )
        
        # Create StagingTriple
        staging_triple = cls(extracted_triple)
        
        # Set staging-specific fields
        approval_status = data.get("approval_status")
        if approval_status:
            staging_triple.approval_status = ApprovalDecision(approval_status)
        
        staging_triple.reviewed_by = data.get("reviewed_by")
        
        review_ts = data.get("review_timestamp")
        if review_ts:
            staging_triple.review_timestamp = datetime.fromisoformat(review_ts)
        
        staging_triple.edit_history = data.get("edit_history", [])
        staging_triple.rejection_reason = data.get("rejection_reason")
        
        return staging_triple


@dataclass
class TransactionContext:
    """Context for transaction rollback support."""
    
    backup_graph: Optional[Graph] = None
    backup_records: Dict[str, Any] = field(default_factory=dict)
    backup_state: Dict[str, Any] = field(default_factory=dict)


class StagingManager:
    """Comprehensive staging manager with HITL workflow and live reload capabilities."""
    
    def __init__(self, 
                 staging_path: Optional[Path] = None,
                 approved_kg_path: Optional[Path] = None,
                 provenance_manager: Optional[ProvenanceManager] = None):
        """Initialize staging manager.
        
        Args:
            staging_path: Path to store staging data
            approved_kg_path: Path to approved knowledge graph file
            provenance_manager: ProvenanceManager instance for provenance handling
        """
        # Path configuration
        self.staging_path = Path(staging_path or settings.get("staging_path", "./data/staging"))
        self.approved_kg_path = Path(approved_kg_path or settings.get("approved_kg_path", "./data/knowledge_graph.ttl"))
        
        # Ensure directories exist
        self.staging_path.mkdir(parents=True, exist_ok=True)
        self.approved_kg_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.provenance_manager = provenance_manager or ProvenanceManager()
        
        # Load existing staging data
        self.staging_triples: Dict[str, StagingTriple] = {}
        self._load_staging_data()
        
        # Transaction support
        self.current_transaction: Optional[TransactionContext] = None
        
        # Graph store instance (singleton pattern)
        self.graph_store: Optional[GraphStore] = None
        
        # RDF namespaces (aligned with ProvenanceManager)
        self._init_namespaces()
        
        logger.info(f"StagingManager initialized with staging_path: {self.staging_path}")
        logger.info(f"Approved KG path: {self.approved_kg_path}")
        logger.info(f"Loaded {len(self.staging_triples)} staging triples")
    
    def _init_namespaces(self) -> None:
        """Initialize RDF namespaces consistent with ProvenanceManager."""
        # Core namespaces from ProvenanceManager
        self.CHIMERA = self.provenance_manager.CHIMERA
        self.PROV = self.provenance_manager.PROV
        self.DC = self.provenance_manager.DC
        
        # Additional namespaces for staging
        self.STAGING = Namespace("http://alchemists-chimera.org/staging#")
        self.APPROVAL = Namespace("http://alchemists-chimera.org/approval#")
        
        # Namespace dictionary for easy access
        self.namespaces = {
            "chimera": self.CHIMERA,
            "prov": self.PROV,
            "dc": self.DC,
            "staging": self.STAGING,
            "approval": self.APPROVAL,
            "rdf": RDF,
            "rdfs": RDFS,
            "xsd": XSD,
        }
    
    def _load_staging_data(self) -> None:
        """Load staging data from disk."""
        staging_files = list(self.staging_path.glob("*.json"))
        
        for file_path in staging_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                staging_triple = StagingTriple.from_dict(data)
                record_id = file_path.stem
                self.staging_triples[record_id] = staging_triple
                
            except Exception as e:
                logger.warning(f"Failed to load staging file {file_path}: {e}")
    
    def _save_staging_triple(self, record_id: str, staging_triple: StagingTriple) -> None:
        """Save staging triple to disk."""
        file_path = self.staging_path / f"{record_id}.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(staging_triple.to_dict(), f, indent=2)
    
    def get_graph_store(self) -> GraphStore:
        """Get or create GraphStore instance (singleton pattern)."""
        if self.graph_store is None:
            self.graph_store = get_graph_store()
        return self.graph_store
    
    def add_triple_for_staging(self, 
                             triple: Union[ExtractedTriple, StagingTriple],
                             validation_status: ValidationStatus,
                             validation_messages: List[str] = None,
                             provenance_record: Optional[ProvenanceRecord] = None) -> str:
        """Add a triple to staging with validation results.
        
        Args:
            triple: The triple to stage (ExtractedTriple or StagingTriple)
            validation_status: Validation status from SHACL
            validation_messages: Validation messages from SHACL
            provenance_record: Provenance record for the triple
            
        Returns:
            Record ID
        """
        # Convert to StagingTriple if needed
        if isinstance(triple, ExtractedTriple):
            staging_triple = StagingTriple(triple)
        else:
            staging_triple = triple
        
        # Auto-approve VALID triples (as per requirements)
        if validation_status == ValidationStatus.VALID:
            staging_triple.approval_status = ApprovalDecision.APPROVED
            staging_triple.reviewed_by = "auto_approval"
            staging_triple.review_timestamp = datetime.now()
            
            # Auto-merge into approved KG
            self._auto_approve_triple(staging_triple)
        
        # Generate record ID with hash for uniqueness
        triple_hash = hashlib.md5(
            f"{staging_triple.subject}{staging_triple.predicate}{staging_triple.object}".encode()
        ).hexdigest()[:12]
        record_id = f"staging_{triple_hash}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Save to memory and disk
        self.staging_triples[record_id] = staging_triple
        self._save_staging_triple(record_id, staging_triple)
        
        logger.info(f"Added triple to staging: {record_id} with status {validation_status}")
        logger.debug(f"Triple: {staging_triple.subject} {staging_triple.predicate} {staging_triple.object}")
        
        return record_id
    
    def get_pending_review(self) -> List[Tuple[str, StagingTriple]]:
        """Get triples pending human review.
        
        Returns:
            List of (record_id, staging_triple) tuples
        """
        pending = []
        
        for record_id, staging_triple in self.staging_triples.items():
            # Include triples that are quarantined or pending review AND not approved/rejected
            if (staging_triple.approval_status is None or 
                staging_triple.approval_status in [None, ApprovalDecision.REJECTED]) and \
               staging_triple.triple:
                pending.append((record_id, staging_triple))
        
        return pending
    
    def get_approved_triples(self) -> List[Tuple[str, StagingTriple]]:
        """Get approved triples.
        
        Returns:
            List of (record_id, staging_triple) tuples
        """
        approved = []
        
        for record_id, staging_triple in self.staging_triples.items():
            if staging_triple.approval_status in [ApprovalDecision.APPROVED, ApprovalDecision.EDITED_AND_APPROVED]:
                approved.append((record_id, staging_triple))
        
        return approved
    
    def get_rejected_triples(self) -> List[Tuple[str, StagingTriple]]:
        """Get rejected triples.
        
        Returns:
            List of (record_id, staging_triple) tuples
        """
        rejected = []
        
        for record_id, staging_triple in self.staging_triples.items():
            if staging_triple.approval_status == ApprovalDecision.REJECTED:
                rejected.append((record_id, staging_triple))
        
        return rejected
    
    def approve_triple(self, 
                      record_id: str, 
                      reviewer: str,
                      edited_triple: Optional[ExtractedTriple] = None,
                      rejection_reason: Optional[str] = None) -> bool:
        """Approve or reject a triple with transaction support and live reload.
        
        This is the core method that implements live reload functionality.
        
        Args:
            record_id: Record identifier
            reviewer: Reviewer name/ID
            edited_triple: Optional edited version of the triple
            rejection_reason: Reason for rejection (if rejecting)
            
        Returns:
            True if successful, False otherwise
        """
        if record_id not in self.staging_triples:
            logger.warning(f"Record {record_id} not found")
            return False
        
        # Start transaction
        transaction = self._begin_transaction(record_id)
        
        try:
            staging_triple = self.staging_triples[record_id]
            
            if edited_triple:
                # Save edit history
                original_triple = copy.deepcopy(staging_triple.triple)
                edit_record = {
                    "original": original_triple.to_json() if hasattr(original_triple, 'to_json') else {},
                    "edited": edited_triple.to_json() if hasattr(edited_triple, 'to_json') else {},
                    "editor": reviewer,
                    "edit_timestamp": datetime.now().isoformat(),
                }
                staging_triple.edit_history.append(edit_record)
                
                # Update with edited triple
                staging_triple.triple = edited_triple
                staging_triple.subject = edited_triple.subject
                staging_triple.predicate = edited_triple.predicate
                staging_triple.object = edited_triple.object
                staging_triple.evidence = edited_triple.evidence
                staging_triple.confidence = edited_triple.confidence
                
                # Edited and approved
                staging_triple.approval_status = ApprovalDecision.EDITED_AND_APPROVED
                staging_triple.reviewed_by = reviewer
                staging_triple.review_timestamp = datetime.now()
                
                # Merge edited triple into KG
                self._merge_into_approved_kg(staging_triple)
                
            elif rejection_reason:
                # Reject triple
                staging_triple.approval_status = ApprovalDecision.REJECTED
                staging_triple.reviewed_by = reviewer
                staging_triple.review_timestamp = datetime.now()
                staging_triple.rejection_reason = rejection_reason
                
            else:
                # Approve as-is
                staging_triple.approval_status = ApprovalDecision.APPROVED
                staging_triple.reviewed_by = reviewer
                staging_triple.review_timestamp = datetime.now()
                
                # Merge approved triple into KG
                self._merge_into_approved_kg(staging_triple)
            
            # Save updated triple
            self._save_staging_triple(record_id, staging_triple)
            
            # TRIGGER LIVE RELOAD - Key functionality
            self._trigger_live_reload()
            
            # Commit transaction
            self._commit_transaction(transaction)
            
            logger.info(f"Triple {record_id} processed by {reviewer}: {staging_triple.approval_status}")
            return True
            
        except Exception as e:
            # Rollback on error
            self._rollback_transaction(transaction)
            logger.error(f"Failed to approve triple {record_id}: {e}")
            return False
    
    def _trigger_live_reload(self) -> None:
        """Trigger live reload of GraphStore instance.
        
        This ensures newly approved triples are immediately queryable without
        restarting Streamlit or other applications.
        """
        try:
            # Get the singleton graph store instance
            graph_store = self.get_graph_store()
            
            # Reload the ontology from the updated file
            if graph_store._loaded:
                logger.info("Triggering live reload of GraphStore...")
                
                # Clear and reload the graph
                graph_store.graph = Graph()
                graph_store._loaded = False
                graph_store.load_ontology()
                
                logger.info("GraphStore live reload completed")
            else:
                logger.warning("GraphStore not loaded, cannot trigger live reload")
                
        except Exception as e:
            logger.error(f"Failed to trigger live reload: {e}")
    
    def _merge_into_approved_kg(self, staging_triple: StagingTriple) -> None:
        """Merge approved triple into the approved knowledge graph with proper Turtle serialization.
        
        Args:
            staging_triple: Approved staging triple
        """
        try:
            # Load or create approved graph
            approved_graph = Graph()
            
            # Bind all namespaces (CRITICAL for proper Turtle serialization)
            for prefix, namespace in self.namespaces.items():
                approved_graph.bind(prefix, namespace)
            
            # Load existing graph if it exists
            if self.approved_kg_path.exists():
                try:
                    approved_graph.parse(self.approved_kg_path, format="turtle")
                    logger.debug(f"Loaded existing approved KG with {len(approved_graph)} triples")
                except Exception as e:
                    logger.warning(f"Failed to parse existing approved KG, creating new: {e}")
            
            # Create URIRefs for the triple
            # Use normalized URIs from provenance manager
            subject_uri = URIRef(self.provenance_manager.create_subject_uri(staging_triple.subject))
            predicate_uri = URIRef(self.provenance_manager.create_predicate_uri(staging_triple.predicate))
            
            # Check if object is a literal or URI
            if staging_triple.object.startswith("chimera:"):
                object_uri = URIRef(self.provenance_manager.create_object_uri(staging_triple.object))
                obj = object_uri
            else:
                obj = Literal(staging_triple.object)
            
            # Add the triple to the graph
            approved_graph.add((subject_uri, predicate_uri, obj))
            
            # Add labels for original text preservation
            approved_graph.add((subject_uri, RDFS.label, Literal(staging_triple.subject)))
            approved_graph.add((predicate_uri, RDFS.label, Literal(staging_triple.predicate)))
            
            # Add approval metadata
            approval_uri = URIRef(f"{self.APPROVAL}approval_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            approved_graph.add((approval_uri, RDF.type, self.APPROVAL.Approval))
            approved_graph.add((approval_uri, self.APPROVAL.approvedTriple, subject_uri))
            approved_graph.add((approval_uri, self.APPROVAL.approvedBy, Literal(staging_triple.reviewed_by)))
            approved_graph.add((approval_uri, self.DC.created, Literal(datetime.now().isoformat(), datatype=XSD.dateTime)))
            
            # Add confidence and evidence if available
            if hasattr(staging_triple, 'confidence'):
                approved_graph.add((subject_uri, self.CHIMERA.confidence, 
                                  Literal(staging_triple.confidence, datatype=XSD.float)))
            
            if hasattr(staging_triple, 'evidence') and staging_triple.evidence:
                approved_graph.add((subject_uri, self.CHIMERA.evidence, Literal(staging_triple.evidence)))
            
            # Serialize to Turtle format
            turtle_data = approved_graph.serialize(format="turtle")
            
            # Write to file
            with open(self.approved_kg_path, 'w', encoding='utf-8') as f:
                f.write(turtle_data)
            
            logger.info(f"Merged triple into approved KG: {staging_triple.subject} {staging_triple.predicate} {staging_triple.object}")
            logger.debug(f"Approved KG now has {len(approved_graph)} triples")
            
        except Exception as e:
            logger.error(f"Failed to merge triple into approved KG: {e}")
            raise
    
    def _auto_approve_triple(self, staging_triple: StagingTriple) -> None:
        """Auto-approve a triple that passed validation.
        
        Args:
            staging_triple: Staging triple to auto-approve
        """
        try:
            # Merge into approved KG
            self._merge_into_approved_kg(staging_triple)
            
            # Trigger live reload
            self._trigger_live_reload()
            
            logger.info(f"Auto-approved triple: {staging_triple.subject} {staging_triple.predicate} {staging_triple.object}")
            
        except Exception as e:
            logger.error(f"Failed to auto-approve triple: {e}")
    
    def _begin_transaction(self, record_id: str) -> TransactionContext:
        """Begin a transaction with backup state.
        
        Args:
            record_id: Record ID for transaction
            
        Returns:
            TransactionContext with backup state
        """
        context = TransactionContext()
        
        # Backup current state
        if record_id in self.staging_triples:
            context.backup_records[record_id] = copy.deepcopy(self.staging_triples[record_id])
        
        # Backup graph if it exists
        if self.approved_kg_path.exists():
            try:
                backup_graph = Graph()
                backup_graph.parse(self.approved_kg_path, format="turtle")
                context.backup_graph = backup_graph
            except Exception as e:
                logger.warning(f"Failed to backup graph for transaction: {e}")
        
        self.current_transaction = context
        logger.debug(f"Transaction started for record {record_id}")
        
        return context
    
    def _commit_transaction(self, context: TransactionContext) -> None:
        """Commit transaction and clean up.
        
        Args:
            context: Transaction context
        """
        self.current_transaction = None
        logger.debug("Transaction committed")
    
    def _rollback_transaction(self, context: TransactionContext) -> None:
        """Rollback transaction to backup state.
        
        Args:
            context: Transaction context with backup state
        """
        try:
            # Restore staging triples
            for record_id, backup_triple in context.backup_records.items():
                self.staging_triples[record_id] = backup_triple
                self._save_staging_triple(record_id, backup_triple)
            
            # Restore graph if backed up
            if context.backup_graph is not None:
                turtle_data = context.backup_graph.serialize(format="turtle")
                with open(self.approved_kg_path, 'w', encoding='utf-8') as f:
                    f.write(turtle_data)
            
            logger.info("Transaction rolled back successfully")
            
        except Exception as e:
            logger.error(f"Failed to rollback transaction: {e}")
        
        self.current_transaction = None
    
    def edit_triple(self, 
                   record_id: str, 
                   editor: str,
                   subject: Optional[str] = None,
                   predicate: Optional[str] = None,
                   object: Optional[str] = None,
                   evidence: Optional[str] = None,
                   confidence: Optional[float] = None) -> Optional[ExtractedTriple]:
        """Edit a triple and return the edited version for review.
        
        Args:
            record_id: Record identifier
            editor: Editor name/ID
            subject: New subject (optional)
            predicate: New predicate (optional)
            object: New object (optional)
            evidence: New evidence (optional)
            confidence: New confidence (optional)
            
        Returns:
            Edited ExtractedTriple or None if record not found
        """
        if record_id not in self.staging_triples:
            return None
        
        staging_triple = self.staging_triples[record_id]
        original_triple = staging_triple.triple
        
        # Create edited triple
        edited_triple = ExtractedTriple(
            subject=subject if subject is not None else original_triple.subject,
            predicate=predicate if predicate is not None else original_triple.predicate,
            object=object if object is not None else original_triple.object,
            evidence=evidence if evidence is not None else original_triple.evidence,
            confidence=confidence if confidence is not None else original_triple.confidence,
            chunk_id=original_triple.chunk_id,
            entity_anchors=original_triple.entity_anchors,
            metadata={
                **original_triple.metadata,
                "edited_by": editor,
                "edit_timestamp": datetime.now().isoformat(),
            },
            extraction_timestamp=datetime.now(),
        )
        
        # Add to edit history
        edit_record = {
            "original": original_triple.to_json() if hasattr(original_triple, 'to_json') else {},
            "edited": edited_triple.to_json() if hasattr(edited_triple, 'to_json') else {},
            "editor": editor,
            "edit_timestamp": datetime.now().isoformat(),
        }
        
        staging_triple.edit_history.append(edit_record)
        
        # Save updated staging triple
        self._save_staging_triple(record_id, staging_triple)
        
        logger.info(f"Triple {record_id} edited by {editor}")
        logger.debug(f"Edit: {original_triple.subject} -> {edited_triple.subject}")
        
        return edited_triple
    
    def get_stats(self) -> Dict[str, Any]:
        """Get staging manager statistics.
        
        Returns:
            Dictionary with comprehensive statistics
        """
        total = len(self.staging_triples)
        
        # Count by approval status
        status_counts = {}
        for staging_triple in self.staging_triples.values():
            status = staging_triple.approval_status
            status_key = status.value if status else "pending"
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
        
        # Get approval KG stats
        kg_stats = {}
        if self.approved_kg_path.exists():
            try:
                kg_graph = Graph()
                kg_graph.parse(self.approved_kg_path, format="turtle")
                kg_stats = {
                    "triple_count": len(kg_graph),
                    "last_modified": datetime.fromtimestamp(self.approved_kg_path.stat().st_mtime).isoformat(),
                }
            except Exception as e:
                kg_stats = {"error": str(e)}
        
        # Get pending review count
        pending_review = len(self.get_pending_review())
        
        return {
            "total_triples": total,
            "status_counts": status_counts,
            "pending_review": pending_review,
            "approved_kg_stats": kg_stats,
            "staging_path": str(self.staging_path),
            "approved_kg_path": str(self.approved_kg_path),
        }
    
    def reset_staging(self, include_approved: bool = False) -> int:
        """Reset staging area, optionally including approved triples.
        
        Args:
            include_approved: If True, also remove approved triples
            
        Returns:
            Number of triples removed
        """
        triples_to_remove = []
        
        for record_id, staging_triple in self.staging_triples.items():
            if include_approved or staging_triple.approval_status not in [ApprovalDecision.APPROVED, ApprovalDecision.EDITED_AND_APPROVED]:
                triples_to_remove.append(record_id)
        
        # Remove from memory and disk
        for record_id in triples_to_remove:
            del self.staging_triples[record_id]
            file_path = self.staging_path / f"{record_id}.json"
            if file_path.exists():
                file_path.unlink()
        
        logger.info(f"Reset staging: removed {len(triples_to_remove)} triples")
        return len(triples_to_remove)
    
    def export_approved_kg(self, output_path: Optional[Path] = None) -> Path:
        """Export the approved knowledge graph.
        
        Args:
            output_path: Optional output path
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.staging_path / f"approved_kg_export_{timestamp}.ttl"
        
        # Copy the approved KG file
        if self.approved_kg_path.exists():
            import shutil
            shutil.copy2(self.approved_kg_path, output_path)
            logger.info(f"Exported approved KG to {output_path}")
        else:
            # Create empty graph if file doesn't exist
            empty_graph = Graph()
            
            # Bind namespaces
            for prefix, namespace in self.namespaces.items():
                empty_graph.bind(prefix, namespace)
            
            # Write empty graph
            turtle_data = empty_graph.serialize(format="turtle")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(turtle_data)
            
            logger.info(f"Created empty approved KG export at {output_path}")
        
        return output_path


def create_default_staging_manager() -> StagingManager:
    """Create a StagingManager with default configuration.
    
    Returns:
        StagingManager instance
    """
    return StagingManager()


def main():
    """Example usage and testing of StagingManager."""
    import sys
    from pathlib import Path
    
    print("Testing StagingManager...")
    print("=" * 60)
    
    # Create a test staging manager
    staging_manager = create_default_staging_manager()
    
    # Create test triple
    from datetime import datetime
    from .ingestor.triple_extractor import ExtractedTriple
    
    test_triple = ExtractedTriple(
        subject="chimera:Basel_Committee",
        predicate="chimera:develops",
        object="chimera:Basel_III_framework",
        evidence="The Basel III framework was developed by the Basel Committee",
        confidence=0.95,
        chunk_id="test-chunk-001",
        entity_anchors=["Basel Committee", "Basel III"],
        metadata={"test": True},
        extraction_timestamp=datetime.now()
    )
    
    # Add triple to staging
    print("\n1. Adding triple to staging...")
    record_id = staging_manager.add_triple_for_staging(
        triple=test_triple,
        validation_status=ValidationStatus.VALID,
        validation_messages=["Valid triple"],
    )
    
    print(f"   Added with record_id: {record_id}")
    
    # Get statistics
    print("\n2. Getting statistics...")
    stats = staging_manager.get_stats()
    print(f"   Total triples: {stats['total_triples']}")
    print(f"   Status counts: {stats['status_counts']}")
    print(f"   Pending review: {stats['pending_review']}")
    
    # Get pending review (should be empty due to auto-approval)
    print("\n3. Getting pending review...")
    pending = staging_manager.get_pending_review()
    print(f"   Pending review count: {len(pending)}")
    
    # Create another triple for manual review
    print("\n4. Adding triple requiring manual review...")
    test_triple2 = ExtractedTriple(
        subject="chimera:AI_system",
        predicate="chimera:analyzes",
        object="Financial transactions",
        evidence="The AI system analyzes financial transactions",
        confidence=0.6,
        chunk_id="test-chunk-002",
        entity_anchors=["AI", "financial"],
        metadata={"test": True},
        extraction_timestamp=datetime.now()
    )
    
    record_id2 = staging_manager.add_triple_for_staging(
        triple=test_triple2,
        validation_status=ValidationStatus.QUARANTINED,
        validation_messages=["Low confidence", "Requires human review"],
    )
    
    print(f"   Added with record_id: {record_id2}")
    
    # Check pending review again
    pending = staging_manager.get_pending_review()
    print(f"   Pending review count: {len(pending)}")
    
    if pending:
        print("\n5. Testing manual approval workflow...")
        test_record_id, test_staging_triple = pending[0]
        
        # Edit the triple
        print(f"   Editing triple {test_record_id}...")
        edited_triple = staging_manager.edit_triple(
            record_id=test_record_id,
            editor="test_editor",
            confidence=0.8,  # Increase confidence
        )
        
        # Approve with edit
        print(f"   Approving edited triple...")
        success = staging_manager.approve_triple(
            record_id=test_record_id,
            reviewer="test_reviewer",
            edited_triple=edited_triple,
        )
        
        print(f"   Approval success: {success}")
    
    # Get final statistics
    print("\n6. Final statistics...")
    stats = staging_manager.get_stats()
    print(f"   Total triples: {stats['total_triples']}")
    print(f"   Status counts: {stats['status_counts']}")
    
    # Export approved KG
    print("\n7. Exporting approved knowledge graph...")
    export_path = staging_manager.export_approved_kg()
    print(f"   Exported to: {export_path}")
    
    # Test live reload (simulated)
    print("\n8. Testing live reload trigger...")
    try:
        staging_manager._trigger_live_reload()
        print("   Live reload triggered successfully")
    except Exception as e:
        print(f"   Live reload test warning: {e}")
    
    print("\n" + "=" * 60)
    print("✅ StagingManager test completed successfully!")


if __name__ == "__main__":
    main()

