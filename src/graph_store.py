"""
Graph Store Engine for Alchemist's Chimera Hybrid RAG Engine

Provides RDF/SPARQL-based knowledge graph retrieval capabilities.
Integrates with the finance ontology from the existing finance-ontology-rag repository.
"""

import logging
import re
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
        self.graph.bind("finance", self.EX)
        self.graph.bind("ex", self.EX)
        self.graph.bind("owl", OWL)
        self.graph.bind("rdf", RDF)
        self.graph.bind("rdfs", RDFS)
        
        # The seeded approved graph is part of the local demo dataset. Load it
        # alongside the ontology so the default router has queryable facts.
        self.approved_kg_path = (
            Path(__file__).resolve().parents[1] / "data" / "graphs" / "approved_kg.ttl"
        )
        self.ingested_kg_path = (
            Path(__file__).resolve().parents[1] / "data" / "knowledge_graph.ttl"
        )

        # Track if graph has been loaded
        self._loaded = False
        
        self.logger.info("GraphStore initialized")
    
    def load_ontology(self) -> bool:
        """Load the ontology and both local knowledge-graph sources.

        Loading is deliberately idempotent and replaces the in-memory graph so
        an approval reload cannot leave removed or superseded triples behind.
        A few checked-in demo graphs predate their namespace declarations; the
        parser adds those declarations without changing the stored files.
        """
        self.graph = Graph()
        self._bind_namespaces()
        self._loaded = False

        ontology_file = Path(self.ontology_path)
        sources = [
            (ontology_file, "ontology"),
            (self.approved_kg_path, "approved knowledge graph"),
            (self.ingested_kg_path, "ingested knowledge graph"),
        ]
        loaded_paths = set()
        loaded_any_source = False

        for source_path, description in sources:
            resolved_path = source_path.resolve()
            if resolved_path in loaded_paths or not source_path.exists():
                continue
            try:
                self._parse_turtle_source(source_path)
                loaded_paths.add(resolved_path)
                loaded_any_source = True
                self.logger.info("Loaded %s from %s", description, source_path)
            except Exception as error:
                self.logger.warning(
                    "Could not load %s from %s: %s", description, source_path, error
                )

        if not loaded_any_source:
            self.logger.info("Creating default ontology structure")
            self._create_default_ontology()

        self._loaded = True
        self.logger.info("Graph contains %s triples", len(self.graph))
        return True

    def reload(self) -> bool:
        """Clear and immediately reload all configured RDF sources."""
        return self.load_ontology()

    def _bind_namespaces(self) -> None:
        """Bind namespaces after creating or replacing the RDFLib graph."""
        self.graph.bind("finance", self.EX)
        self.graph.bind("ex", self.EX)
        self.graph.bind("owl", OWL)
        self.graph.bind("rdf", RDF)
        self.graph.bind("rdfs", RDFS)

    def _parse_turtle_source(self, source_path: Path) -> None:
        """Parse Turtle while tolerating legacy demo prefix omissions."""
        content = source_path.read_text(encoding="utf-8")
        declarations = []
        if re.search(r"(?<![A-Za-z0-9_]):[A-Za-z_][A-Za-z0-9_]*", content) and not re.search(
            r"@prefix\s*:\s*<", content, flags=re.IGNORECASE
        ):
            declarations.append("@prefix : <http://example.org/finance#> .")
        if re.search(r"\bapproval:", content) and not re.search(
            r"@prefix\s+approval:\s*<", content, flags=re.IGNORECASE
        ):
            declarations.append(
                "@prefix approval: <http://alchemists-chimera.org/approval#> ."
            )
        if declarations:
            content = "\n".join(declarations) + "\n" + content
        self.graph.parse(data=content, format="turtle", publicID=str(source_path))
    
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
            result_index = 0
            for row in result_bindings:
                # OWL ontology declarations describe the schema, not a domain
                # fact. Keep them out of retrieval cards even when a caller's
                # SPARQL query does not add its own filter.
                if self._is_ontology_metadata_row(row, result_bindings.vars):
                    continue

                content = self._format_result(row)
                if not content:
                    continue
                row_metadata = {
                    str(variable): str(row[variable])
                    for variable in result_bindings.vars
                    if row[variable] is not None
                }
                metadata = {
                    "type": "graph_query",
                    "result_index": result_index,
                    "query_type": "sparql",
                }
                result_index += 1
                if row_metadata.get("sourceDocument"):
                    metadata["source_document"] = row_metadata["sourceDocument"]
                if row_metadata.get("sourceChunk"):
                    metadata["chunk_id"] = row_metadata["sourceChunk"]
                if row_metadata.get("pageNumber"):
                    metadata["page_number"] = row_metadata["pageNumber"]
                if row_metadata.get("sourceJobId"):
                    metadata["source_job_id"] = row_metadata["sourceJobId"]

                entity_links = []
                for variable in ("entity", "subject", "provenance"):
                    if row_metadata.get(variable):
                        entity_links.append(row_metadata[variable])

                # Calculate score (simplified)
                score = max(0.5, 1.0 - ((result_index - 1) * 0.05))

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
            query_limit = max(max_results * 10, max_results)
            query = f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX chimera: <http://example.org/chimera#>

                SELECT DISTINCT ?entity ?label ?type ?description ?sourceDocument
                    ?sourceChunk ?pageNumber ?sourceJobId
                WHERE {{
                    ?entity rdfs:label ?label .
                    OPTIONAL {{ ?entity a ?type }}
                    OPTIONAL {{ ?entity rdfs:comment ?description }}
                    OPTIONAL {{ ?entity chimera:sourceDocument ?sourceDocument }}
                    OPTIONAL {{ ?entity chimera:sourceChunk ?sourceChunk }}
                    OPTIONAL {{ ?entity chimera:pageNumber ?pageNumber }}
                    OPTIONAL {{ ?entity chimera:sourceJobId ?sourceJobId }}
                    FILTER NOT EXISTS {{ ?entity a owl:Ontology }}
                    FILTER ({filters})
                }}
                LIMIT {query_limit}
            """

            candidates = self.retrieve(query, query_limit)
            lowered_terms = tuple(terms)

            def relevance(result: RetrievalResult) -> tuple[int, int, float]:
                content = result.content.casefold()
                matched_terms = sum(content.count(term) for term in lowered_terms)
                schema_penalty = int(
                    "owl#class" in content or "owl#objectproperty" in content
                )
                return (matched_terms, -schema_penalty, result.score)

            candidates.sort(key=relevance, reverse=True)
            return candidates[:max_results]
            
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
    
    def _is_ontology_metadata_row(self, row: Any, variables: Any) -> bool:
        """Return whether a SPARQL row represents an OWL ontology header."""
        values = list(row)
        if OWL.Ontology in values:
            return True
        variable_names = {str(variable) for variable in variables}
        for variable_name in ("entity", "subject"):
            if variable_name not in variable_names:
                continue
            resource = row[variable_name]
            if resource is not None and (resource, RDF.type, OWL.Ontology) in self.graph:
                return True
        return False

    def _format_result(self, row) -> str:
        """Format a SPARQL row, omitting unbound trailing values."""
        try:
            parts = []
            for item in row:
                if item is None:
                    continue
                value = str(item.value if hasattr(item, "value") else item).strip()
                if value and value.casefold() != "none":
                    parts.append(value)
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
