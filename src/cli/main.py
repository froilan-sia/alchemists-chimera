#!/usr/bin/env python3
"""
Command-Line Interface for Alchemist's Chimera Hybrid RAG Engine

Usage: python -m src.cli.main --query "your query here"
"""

import argparse
import asyncio
import sys
import time
from typing import Optional

import sys
sys.path.insert(0, '/Users/froilansia/git/alchemists-chimera')

from src.models import QueryRequest, QueryType, HybridResponse
from src.router import HybridRouter
from src.config import settings
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import box


async def process_query(query: str, query_type: Optional[QueryType] = None, alpha: Optional[float] = None) -> HybridResponse:
    """Process a query through the hybrid RAG pipeline."""
    router = HybridRouter()
    request = QueryRequest(
        query=query,
        query_type=query_type,
        alpha=alpha,
        max_results=10,
    )
    
    start_time = time.time()
    response = await router.retrieve(request)
    response.processing_time = time.time() - start_time
    
    return response


def display_response(response: HybridResponse, console: Console) -> None:
    """Display the response in a formatted way."""
    # Display the answer
    console.print("\n" + "="*70, style="bold cyan")
    console.print("ANSWER", style="bold cyan")
    console.print("="*70, style="bold cyan")
    console.print(Panel(
        response.answer,
        title="Response",
        border_style="green",
        padding=(1, 2),
    ))
    
    # Display metadata
    metadata_table = Table(title="Metadata", box=box.ROUNDED)
    metadata_table.add_column("Metric", style="cyan")
    metadata_table.add_column("Value", style="green")
    metadata_table.add_row("Query Type", response.query_type.value)
    metadata_table.add_row("Confidence", f"{response.confidence:.2%}")
    metadata_table.add_row("Processing Time", f"{response.processing_time:.2f}s")
    metadata_table.add_row("Sources", str(len(response.sources)))
    
    console.print("\n")
    console.print(metadata_table)
    
    # Display sources
    if response.sources:
        console.print("\n" + "="*70, style="bold cyan")
        console.print("SOURCES", style="bold cyan")
        console.print("="*70, style="bold cyan")
        
        for i, source in enumerate(response.sources, 1):
            source_table = Table(show_header=False, box=box.SIMPLE)
            source_table.add_column("Source", style="bold magenta")
            source_table.add_column("Content", style="white")
            source_table.add_column("Score", style="yellow")
            
            # Truncate content if too long
            content = source.content[:200] + "..." if len(source.content) > 200 else source.content
            
            source_table.add_row(
                f"[{i}] {source.source.value}",
                content,
                f"{source.score:.2f}"
            )
            
            console.print(source_table)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Alchemist's Chimera - Hybrid Graph-Vector RAG Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli.main --query "What are the capital requirements for banks?"
  python -m src.cli.main --query "What subsidiaries does Bank of America own?" --type entity_relationship
  python -m src.cli.main --query "Explain quantitative easing" --type semantic --alpha 0.3
        """
    )
    
    parser.add_argument(
        "--query", "-q",
        type=str,
        required=True,
        help="The query to process"
    )
    
    parser.add_argument(
        "--type", "-t",
        type=str,
        choices=["entity_relationship", "regulatory", "semantic", "hybrid"],
        default=None,
        help="Query type (optional, auto-detected if not specified)"
    )
    
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Graph weight (0-1, optional, default based on query type)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )
    
    args = parser.parse_args()
    
    # Convert query type
    query_type = None
    if args.type:
        try:
            query_type = QueryType(args.type)
        except ValueError:
            query_type = QueryType.HYBRID
    
    # Process the query
    console = Console()
    
    try:
        if args.verbose:
            console.print(f"Processing query: [bold]{args.query}[/bold]")
            console.print(f"Query type: {query_type.value if query_type else 'auto-detect'}")
            console.print(f"Graph weight (alpha): {args.alpha if args.alpha else 'default'}")
            console.print("\n[bold cyan]Processing...[/bold cyan]\n")
        
        response = await process_query(
            query=args.query,
            query_type=query_type,
            alpha=args.alpha
        )
        
        if args.json:
            # Output as JSON
            import json
            output = {
                "answer": response.answer,
                "query_type": response.query_type.value,
                "confidence": response.confidence,
                "processing_time": response.processing_time,
                "sources": [
                    {
                        "content": s.content,
                        "source": s.source.value,
                        "score": s.score,
                        "metadata": s.metadata,
                    }
                    for s in response.sources
                ]
            }
            console.print(json.dumps(output, indent=2))
        else:
            # Display formatted response
            display_response(response, console)
        
        if args.verbose:
            console.print("\n[bold green]✅ Query completed successfully![/bold green]")
        
        return 0
        
    except Exception as e:
        if args.verbose:
            console.print(f"\n[bold red]❌ Error: {str(e)}[/bold red]")
            import traceback
            traceback.print_exc()
        else:
            console.print(f"\n[bold red]❌ Error: {str(e)}[/bold red]")
        
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
