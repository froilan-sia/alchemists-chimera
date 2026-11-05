# Command-Line Interface

This directory contains the command-line interface for The Alchemist's Chimera hybrid RAG engine.

## Usage

```bash
# Basic query
python src/cli/main.py --query "What are the capital requirements for banks?"

# Specify query type
python src/cli/main.py --query "What subsidiaries does Bank of America own?" --type entity_relationship

# Custom alpha weight
python src/cli/main.py --query "Explain quantitative easing" --type semantic --alpha 0.3

# Verbose output
python src/cli/main.py --query "your query" --verbose

# JSON output
python src/cli/main.py --query "your query" --json
```

## Arguments

- `--query, -q` (required): The query to process
- `--type, -t`: Query type (entity_relationship, regulatory, semantic, hybrid)
- `--alpha`: Graph weight (0-1)
- `--verbose, -v`: Enable verbose output
- `--json`: Output in JSON format

## Query Types

- **entity_relationship**: Focus on specific entities, hierarchies, regulations (α=0.8)
- **regulatory**: Compliance, rules, legal frameworks (α=0.7)
- **semantic**: Conceptual, abstract, narrative context (α=0.3)
- **hybrid**: Mixed entity and conceptual queries (α=0.5)
