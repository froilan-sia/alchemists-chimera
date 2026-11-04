#!/bin/bash

# Hook: Validate Ontology Changes
# Purpose: Automatically validate RDF ontology files using SHACL when they are saved
# Trigger: PostFileSave on .ttl files
# Kiroween Hackathon Feature Demonstration

set -e

echo "🔍 Validating ontology changes..."
echo "Timestamp: $(date)"
echo "File: $1"

# Check if pyshacl is available
if ! command -v pyshacl &> /dev/null; then
    echo "⚠️  pyshacl not found. Installing..."
    pip install pyshacl
fi

# Define paths
ONTOLOGY_PATH="ontology/finance-ontology.ttl"
SHAPES_PATH="ontology/shapes.ttl"

# Check if files exist
if [ ! -f "$ONTOLOGY_PATH" ]; then
    echo "❌ Ontology file not found: $ONTOLOGY_PATH"
    echo "💡 Creating basic ontology structure..."
    
    # Create basic ontology structure
    mkdir -p ontology
    cat > "$ONTOLOGY_PATH" << 'EOF'
@prefix : <http://example.org/finance#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

:FinanceOntology a owl:Ontology ;
    rdfs:label "Finance Ontology" ;
    rdfs:comment "A basic finance ontology for hybrid RAG system" .

# Classes
:FinancialInstrument a owl:Class ;
    rdfs:label "Financial Instrument" ;
    rdfs:comment "Any tradable financial asset" .

:TradedEquity a owl:Class ;
    rdfs:subClassOf :FinancialInstrument ;
    rdfs:label "Traded Equity" ;
    rdfs:comment "Publicly traded company stock" .

:RegulatoryDocument a owl:Class ;
    rdfs:label "Regulatory Document" ;
    rdfs:comment "Official regulatory publication" .

# Example data
:AppleStock a :TradedEquity ;
    rdfs:label "Apple Inc. Stock" ;
    :hasTicker "AAPL" ;
    :hasMarketCap "2.8T"^^xsd:string .
EOF
    
    echo "✅ Created basic ontology at $ONTOLOGY_PATH"
fi

if [ ! -f "$SHAPES_PATH" ]; then
    echo "⚠️  SHACL shapes file not found: $SHAPES_PATH"
    echo "💡 Creating basic SHACL shapes..."
    
    cat > "$SHAPES_PATH" << 'EOF'
@prefix : <http://example.org/finance#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

:FinancialInstrumentShape a sh:NodeShape ;
    sh:targetClass :FinancialInstrument ;
    sh:property [
        sh:path rdfs:label ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:message "Financial instruments must have exactly one label" ;
    ] .

:TradedEquityShape a sh:NodeShape ;
    sh:targetClass :TradedEquity ;
    sh:property [
        sh:path :hasTicker ;
        sh:datatype xsd:string ;
        sh:pattern "^[A-Z]{1,5}$" ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:message "Traded equities must have a valid ticker symbol (1-5 uppercase letters)" ;
    ] ;
    sh:property [
        sh:path :hasMarketCap ;
        sh:datatype xsd:string ;
        sh:minCount 0 ;
        sh:maxCount 1 ;
        sh:message "Market cap should be a string" ;
    ] .
EOF
    
    echo "✅ Created basic SHACL shapes at $SHAPES_PATH"
fi

# Run SHACL validation
echo "📋 Running SHACL validation..."
echo "Ontology: $ONTOLOGY_PATH"
echo "Shapes: $SHAPES_PATH"

# Run pyshacl with detailed output
if pyshacl "$ONTOLOGY_PATH" -s "$SHAPES_PATH" --verbose; then
    echo "✅ Ontology validation passed!"
    echo "📊 Validation Summary:"
    echo "  - Ontology file: $ONTOLOGY_PATH"
    echo "  - SHACL shapes: $SHAPES_PATH"
    echo "  - Status: VALID"
    echo "  - Timestamp: $(date)"
    
    # Additional quality checks
    echo "🔬 Running additional quality checks..."
    
    # Check for common issues
    if grep -q "a owl:Class" "$ONTOLOGY_PATH"; then
        CLASS_COUNT=$(grep -c "a owl:Class" "$ONTOLOGY_PATH")
        echo "  - Found $CLASS_COUNT OWL classes"
    fi
    
    if grep -q "a owl:ObjectProperty" "$ONTOLOGY_PATH"; then
        PROP_COUNT=$(grep -c "a owl:ObjectProperty" "$ONTOLOGY_PATH")
        echo "  - Found $PROP_COUNT object properties"
    fi
    
    # Check for inferred classes
    echo "💡 Tip: Run reasoner to check inferences:"
    echo "      python -c \"from rdflib import Graph; g = Graph(); g.parse('$ONTOLOGY_PATH'); print('Triples:', len(g))\""
    
    exit 0
else
    echo "❌ Ontology validation failed!"
    echo "🔧 Please fix the following issues:"
    echo "  1. Check SHACL validation output above"
    echo "  2. Review ontology structure"
    echo "  3. Ensure all required properties are defined"
    echo "  4. Check data type consistency"
    
    # Provide troubleshooting tips
    echo "💡 Troubleshooting tips:"
    echo "  - Run: pyshacl $ONTOLOGY_PATH -s $SHAPES_PATH --verbose"
    echo "  - Check for syntax errors: rapper -i turtle -o ntriples $ONTOLOGY_PATH"
    echo "  - Validate with: owl2vowl -file $ONTOLOGY_PATH"
    
    exit 1
fi