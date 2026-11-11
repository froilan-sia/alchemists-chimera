"""
FastAPI application for Alchemist's Chimera hybrid RAG engine.

Provides REST API endpoints for query processing, health checks,
and system monitoring.
"""

import logging
import time
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__, __description__
from ..config import settings
from ..models import QueryRequest, HybridResponse, HealthStatus, ErrorResponse

# Set up logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Alchemist's Chimera API",
    description=__description__,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global retriever instance (will be initialized in startup)
retriever = None
ingestion_pipeline = None


@app.on_event("startup")
async def startup_event():
    """Initialize application components on startup."""
    global retriever
    
    logger.info(f"Starting Alchemist's Chimera v{__version__}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Log level: {settings.log_level}")
    
    # Import here to avoid circular imports
    from ..router import HybridRouter
    
    try:
        # Initialize retriever (simplified for now)
        retriever = HybridRouter()
        logger.info("Hybrid retriever initialized successfully")
        
        # Initialize components
        logger.info("Application components initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise


@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "name": "Alchemist's Chimera",
        "version": __version__,
        "description": __description__,
        "environment": settings.environment,
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "query": "/query",
            "query_simple": "/query/simple",
        },
        "features": {
            "hybrid_retrieval": True,
            "graph_store": True,
            "vector_store": True,
            "llm_generation": True,
            "local_execution": True,
        },
    }


@app.get("/health", response_model=HealthStatus, tags=["Monitoring"])
async def health_check() -> HealthStatus:
    """Report the health of API, retrieval, and ingestion components."""
    components: Dict[str, str] = {}

    def component_status(name: str, component: Any) -> None:
        try:
            if component is None:
                components[name] = "not_initialized"
            elif hasattr(component, "health_check"):
                result = component.health_check()
                components[name] = result.get("status", "healthy") if isinstance(result, dict) else str(result)
            else:
                components[name] = "initialized"
        except Exception as error:
            logger.error("Health check failed for %s: %s", name, error, exc_info=True)
            components[name] = f"unhealthy: {error}"

    component_status("retriever", retriever)
    component_status("ingestion_pipeline", ingestion_pipeline)
    for name in ("pdf_parser", "entity_extractor", "triple_extractor", "shacl_validator", "staging_manager"):
        component_status(name, getattr(ingestion_pipeline, name, None) if ingestion_pipeline else None)

    try:
        from ..graph_store import get_graph_store
        component_status("graph_store", get_graph_store())
    except Exception as error:
        components["graph_store"] = f"unhealthy: {error}"
    try:
        from ..vector_store import get_vector_store
        component_status("vector_store", get_vector_store())
    except Exception as error:
        components["vector_store"] = f"unhealthy: {error}"
    component_status("llm", getattr(retriever, "response_generator", None))

    healthy_values = {"healthy", "initialized"}
    overall_status = "healthy" if all(value in healthy_values for value in components.values()) else "degraded"
    return HealthStatus(status=overall_status, version=__version__, components=components)


@app.get("/health/{component_name}", tags=["Monitoring"])
async def component_health_check(component_name: str) -> Dict[str, Any]:
    """Return detailed health for a named component."""
    response = await health_check()
    if component_name not in response.components:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown component")
    return {"component": component_name, "status": response.components[component_name]}


@app.post("/query", response_model=HybridResponse, tags=["Query"])
async def process_query(request: QueryRequest) -> HybridResponse:
    """
    Process a query using hybrid graph-vector retrieval.
    
    This endpoint:
    1. Classifies the query type
    2. Retrieves from both graph and vector stores
    3. Fuses results using weighted scoring
    4. Generates answer using local LLM
    
    Returns the answer with source citations and confidence score.
    """
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retriever not initialized"
        )
    
    try:
        logger.info(f"Processing query: {request.query[:100]}...")
        start_time = time.time()
        
        # Process query (simplified for now)
        response = await retriever.retrieve(request)
        response.processing_time = time.time() - start_time
        
        logger.info(f"Query processed in {response.processing_time:.2f}s")
        logger.info(f"Confidence: {response.confidence:.2f}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )


@app.get("/query/simple", response_model=HybridResponse, tags=["Query"])
async def process_simple_query(
    q: str = Query(..., description="Query text"),
    query_type: str = Query(None, description="Query type (optional)"),
    alpha: float = Query(None, ge=0.0, le=1.0, description="Graph weight (0-1, optional)"),
    max_results: int = Query(10, ge=1, le=100, description="Maximum results")
) -> HybridResponse:
    """
    Simple query endpoint using query parameters.
    
    Convenience endpoint for testing and simple integrations.
    """
    request = QueryRequest(
        query=q,
        query_type=query_type,
        alpha=alpha,
        max_results=max_results,
    )
    
    return await process_query(request)


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics() -> Dict[str, Any]:
    """Get application metrics (Prometheus format)."""
    # This would integrate with Prometheus client
    # For now, return basic metrics
    return {
        "status": "Metrics endpoint - Prometheus integration needed",
        "note": "Implement with prometheus_client for production",
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=str(exc) if settings.environment == "development" else None
        ).dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc) if settings.environment == "development" else None
        ).dict(),
    )


# Export app for uvicorn
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
        workers=settings.api_workers,
    )