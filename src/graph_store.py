"""
Graph Store Engine for Alchemist's Chimera Hybrid RAG Engine

Provides RDF/SPARQL-based knowledge graph retrieval capabilities.
Integrates with the finance ontology from the existing finance-ontology-rag repository.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.plugins.sparql import prepareQuery
from rdflib.namespace import RDF, RDFS, OWL

from .config import settings
from .models import RetrievalResult, RetrievalSource

logger = logging.getLogger(__name__)


class GraphStore:
    """Graph store using RDFLib for knowledge graph operations."""
    
    def __init__(self, ontology_path: str = None):
        """Initialize graph store with ontology."""
        self.logger = logging.getLogger(__name__)
        
        # Use provided path or default from settings
        self.ontology_path = ontology_path or settings.graph_store_path
        
        # Initialize RDF graph
        self.graph = Graph()
        
        # Define namespaces
        self.EX = Namespace("http://example.org/finance#")
        self.graph.bind("ex", self.EX)
        self.graph.bind("owl", OWL)
        self.graph.bind("rdf", RDF)
        self.graph.bind("rdfs", RDFS)
        
        # The seeded approved graph is part of the local demo dataset. Load it
        # alongside the ontology so the default router has queryable facts.
        self.approved_kg_path = (
            Path(__file__).resolve().parents[1] / "data" / "graphs" / "approved_kg.ttl"
        )

        # Track if graph has been loaded
        self._loaded = False
        
        self.logger.info("GraphStore initialized")
    
    def load_ontology(self) -> bool:
        """Load the ontology and the local approved knowledge graph."""
        try:
            # Check if file exists
            ontology_file = Path(self.ontology_path)
            
            if ontology_file.exists():
                # Load existing ontology
                self.graph.parse(self.ontology_path, format="turtle")
                self.logger.info(f"Loaded ontology from {self.ontology_path}")
            else:
                # Create default ontology structure
                self.logger.info("Creating default ontology structure")
                self._create_default_ontology()

            # The ontology provides schemas while the approved graph provides
            # reviewed sample facts used by the chat and explorer. Avoid
            # parsing twice when a caller explicitly supplies that same file.
            approved_path = self.approved_kg_path.resolve()
            if ontology_file.resolve() != approved_path and approved_path.exists():
                self.graph.parse(approved_path, format="turtle")
                self.logger.info("Loaded approved knowledge graph from %s", approved_path)

            self.logger.info(f"Graph contains {len(self.graph)} triples")
            self._loaded = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load ontology: {e}")
            # Create default ontology as fallback
            self._create_default_ontology()
            return True
    
    def _create_default_ontology(self):
        """Create default ontology structure."""
        # Define classes
        financial_instrument = self.EX.FinancialInstrument
        traded_equity = self.EX.TradedEquity
        regulatory_document = self.EX.RegulatoryDocument
        financial_entity = self.EX.FinancialEntity
        subsidiary = self.EX.Subsidiary
        
        # Add class definitions
        self.graph.add((financial_instrument, RDF.type, OWL.Class))
        self.graph.add((financial_instrument, RDFS.label, Literal("Financial Instrument")))
        self.graph.add((financial_instrument, RDFS.comment, Literal("Any tradable financial asset")))
        
        self.graph.add((traded_equity, RDF.type, OWL.Class))
        self.graph.add((traded_equity, RDFS.subClassOf, financial_instrument))
        self.graph.add((traded_equity, RDFS.label, Literal("Traded Equity")))
        self.graph.add((traded_equity, RDFS.comment, Literal("Publicly traded company stock")))
        
        self.graph.add((regulatory_document, RDF.type, OWL.Class))
        self.graph.add((regulatory_document, RDFS.label, Literal("Regulatory Document")))
        self.graph.add((regulatory_document, RDFS.comment, Literal("Official regulatory publication")))
        
        self.graph.add((financial_entity, RDF.type, OWL.Class))
        self.graph.add((financial_entity, RDFS.label, Literal("Financial Entity")))
        self.graph.add((financial_entity, RDFS.comment, Literal("Financial organization or institution")))
        
        self.graph.add((subsidiary, RDF.type, OWL.Class))
        self.graph.add((subsidiary, RDFS.label, Literal("Subsidiary")))
        self.graph.add((subsidiary, RDFS.comment, Literal("Company owned by another entity")))
        
        # Define properties
        has_ticker = self.EX.hasTicker
        has_market_cap = self.EX.hasMarketCap
        has_parent = self.EX.hasParent
        has_subsidary = self.EX.hasSubsidiary
        regulates = self.EX.regulates
        
        # Add property definitions
        self.graph.add((has_ticker, RDF.type, OWL.ObjectProperty))
        self.graph.add((has_ticker, RDFS.domain, traded_equity))
        self.graph.add((has_ticker, RDFS.range, Literal("string")))
        
        self.graph.add((has_market_cap, RDF.type, OWL.DatatypeProperty))
        self.graph.add((has_market_cap, RDFS.domain, traded_equity))
        self.graph.add((has_market_cap, RDFS.range, Literal("string")))
        
        self.graph.add((has_parent, RDF.type, OWL.ObjectProperty))
        self.graph.add((has_parent, RDFS.domain, subsidiary))
        self.graph.add((has_parent, RDFS.range, financial_entity))
        
        self.graph.add((has_subsidary, RDF.type, OWL.ObjectProperty))
        self.graph.add((has_subsidary, RDFS.domain, financial_entity))
        self.graph.add((has_subsidary, RDFS.range, subsidiary))
        
        self.graph.add((regulates, RDF.type, OWL.ObjectProperty))
        self.graph.add((regulates, RDFS.domain, regulatory_document))
        self.graph.add((regulates, RDFS.range, OWL.Class))
        
        self.logger.info("Default ontology structure created")
    
    def retrieve(self, query: str, max_results: int = 10) -> List[RetrievalResult]:
        """Execute SPARQL query and return results."""
        try:
            if not self._loaded:
                self.load_ontology()
            
            # Prepare results list
            results = []
            
            # Execute the query
            result_bindings = self.graph.query(query)
            
            # Process results
            for i, row in enumerate(result_bindings):
                # Format result content
                content = self._format_result(row)
                row_metadata = {
                    str(variable): str(row[variable])
                    for variable in result_bindings.vars
                    if row[variable] is not None
                }
                metadata = {
                    "type": "graph_query",
                    "result_index": i,
                    "query_type": "sparql",
                }
                if row_metadata.get("sourceDocument"):
                    metadata["source_document"] = row_metadata["sourceDocument"]
                if row_metadata.get("sourceChunk"):
                    metadata["chunk_id"] = row_metadata["sourceChunk"]
                if row_metadata.get("pageNumber"):
                    metadata["page_number"] = row_metadata["pageNumber"]

                entity_links = []
                for variable in ("entity", "subject", "provenance"):
                    if row_metadata.get(variable):
                        entity_links.append(row_metadata[variable])

                # Calculate score (simplified)
                score = max(0.5, 1.0 - (i * 0.05))

                # Create retrieval result
                result = RetrievalResult(
                    content=content,
                    source=RetrievalSource.GRAPH,
                    score=score,
                    metadata=metadata,
                    entity_links=entity_links or None,
                )
                
                results.append(result)
                
                if len(results) >= max_results:
                    break
            
            self.logger.info(f"Retrieved {len(results)} results from graph store")
            return results
            
        except Exception as e:
            self.logger.error(f"Error executing graph query: {e}")
            return []
    
    def retrieve_by_entity(self, entity_name: str, max_results: int = 10) -> List[RetrievalResult]:
        """Retrieve facts matching meaningful terms in an entity or query."""
        try:
            if not self._loaded:
                self.load_ontology()

            # Natural-language queries rarely equal an RDF label. Search
            # meaningful terms across labels and comments while ignoring
            # question stop words, so seeded facts remain discoverable.
            stop_words = {
                "what", "when", "where", "which", "who", "does", "are",
                "the", "and", "for", "under", "with", "from", "about",
                "into", "that", "this", "have", "has", "must", "their",
            }
            terms = []
            for raw_term in entity_name.lower().replace("?", " ").split():
                term = "".join(character for character in raw_term if character.isalnum())
                if len(term) >= 3 and term not in stop_words and term not in terms:
                    terms.append(term)

            if not terms:
                return []

            filters = " || ".join(
                f'(contains(lcase(str(?label)), "{term}") '
                f'|| contains(lcase(str(?description)), "{term}"))'
                for term in terms
            )
            query = f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX chimera: <http://example.org/chimera#>

                SELECT DISTINCT ?entity ?label ?type ?description ?sourceDocument
                    ?sourceChunk ?pageNumber
                WHERE {{
                    ?entity rdfs:label ?label .
                    OPTIONAL {{ ?entity a ?type }}
                    OPTIONAL {{ ?entity rdfs:comment ?description }}
                    OPTIONAL {{ ?entity chimera:sourceDocument ?sourceDocument }}
                    OPTIONAL {{ ?entity chimera:sourceChunk ?sourceChunk }}
                    OPTIONAL {{ ?entity chimera:pageNumber ?pageNumber }}
                    FILTER ({filters})
                }}
                LIMIT {max_results}
            """

            return self.retrieve(query, max_results)
            
        except Exception as e:
            self.logger.error(f"Error retrieving by entity: {e}")
            return []
    
    def retrieve_relationships(self, subject: str, predicate: str = None, max_results: int = 10) -> List[RetrievalResult]:
        """Retrieve relationships involving a subject entity."""
        try:
            if not self._loaded:
                self.load_ontology()
            
            # Build SPARQL query
            query = f"""
                PREFIX ex: <http://example.org/finance#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                SELECT ?subject ?predicate ?object
                WHERE {{
                    ?subject ?predicate ?object .
                    FILTER (contains(lcase(str(?subject)), "{subject.lower()}"))
                }}
            """
            
            if predicate:
                query += f'FILTER (str(?predicate) = "{predicate}") .'
            
            query += f" LIMIT {max_results}"
            
            return self.retrieve(query, max_results)
            
        except Exception as e:
            self.logger.error(f"Error retrieving relationships: {e}")
            return []
    
    def execute_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL query and return raw results."""
        try:
            if not self._loaded:
                self.load_ontology()
            
            # Execute query
            results = self.graph.query(query)
            
            # Convert to list of dictionaries
            result_list = []
            for row in results:
                row_dict = {}
                for var in results.vars:
                    value = row[var]
                    if hasattr(value, 'value'):
                        row_dict[str(var)] = str(value)
                    else:
                        row_dict[str(var)] = str(value)
                result_list.append(row_dict)
            
            return result_list
            
        except Exception as e:
            self.logger.error(f"Error executing SPARQL: {e}")
            return []
    
    def get_subgraph(self, entities: List[str], max_depth: int = 2) -> List[RetrievalResult]:
        """Retrieve subgraph around specified entities."""
        try:
            if not self._loaded:
                self.load_ontology()
            
            results = []
            
            for entity in entities:
                # Query for entity and its relationships
                query = f"""
                    PREFIX ex: <http://example.org/finance#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    
                    SELECT ?subject ?predicate ?object
                    WHERE {{
                        {{ ?subject ?predicate "{entity}" }}
                        UNION
                        {{ "{entity}" ?predicate ?object }}
                        UNION
                        {{ ?subject rdfs:label "{entity}" }}
                    }}
                    LIMIT 100
                """
                
                # Execute query
                result_bindings = self.graph.query(query)
                
                for i, row in enumerate(result_bindings):
                    # Format content
                    content = f"{row[0]} - {row[1]} - {row[2]}"
                    
                    result = RetrievalResult(
                        content=content,
                        source=RetrievalSource.GRAPH,
                        score=0.8,
                        metadata={
                            "type": "subgraph",
                            "entity": entity,
                            "depth": max_depth
                        }
                    )
                    
                    results.append(result)
            
            return results[:10]
            
        except Exception as e:
            self.logger.error(f"Error retrieving subgraph: {e}")
            return []
    
    def _format_result(self, row) -> str:
        """Format SPARQL result row into readable content."""
        try:
            # Convert row to readable string
            parts = []
            for item in row:
                if hasattr(item, 'value'):
                    parts.append(str(item.value))
                else:
                    parts.append(str(item))
            
            return " | ".join(parts)
        except Exception:
            return str(row)
    
    def health_check(self) -> Dict[str, str]:
        """Check health of graph store."""
        try:
            if not self._loaded:
                self.load_ontology()
            
            return {
                "status": "healthy",
                "triples": str(len(self.graph)),
                "loaded": "true"
            }
            
        except Exception as e:
            return {
                "status": f"error: {str(e)}",
                "triples": "0",
                "loaded": "false"
            }


# Singleton instance
graph_store_instance = None


def get_graph_store() -> GraphStore:
    """Get singleton graph store instance."""
    global graph_store_instance
    
    if graph_store_instance is None:
        graph_store_instance = GraphStore()
        graph_store_instance.load_ontology()
    
    return graph_store_instance
