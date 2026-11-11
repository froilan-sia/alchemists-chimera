# Namespace Definitions for The Alchemist's Chimera

## Core Namespaces

### `:` (Default Namespace)
- **URI**: `http://example.org/finance#`
- **Purpose**: Finance and regulatory ontology
- **Contents**: Financial institutions, regulations, capital requirements, risk concepts
- **Example**: `:Bank`, `:CapitalRequirement`, `:regulatedBy`

### `chimera:`
- **URI**: `http://example.org/chimera#`
- **Purpose**: Provenance tracking and extraction metadata
- **Contents**: Source tracking, validation status, approval information
- **Example**: `chimera:sourceChunk`, `chimera:validationStatus`, `chimera:approvedBy`

### `rdf:`
- **URI**: `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
- **Purpose**: RDF vocabulary
- **Contents**: Type, property, class definitions
- **Example**: `rdf:type`, `rdf:Property`

### `rdfs:`
- **URI**: `http://www.w3.org/2000/01/rdf-schema#`
- **Purpose**: RDF Schema vocabulary
- **Contents**: Label, comment, subClassOf, domain, range
- **Example**: `rdfs:label`, `rdfs:comment`, `rdfs:subClassOf`

### `owl:`
- **URI**: `http://www.w3.org/2002/07/owl#`
- **Purpose**: Web Ontology Language
- **Contents**: Ontology, Class, ObjectProperty, DatatypeProperty
- **Example**: `owl:Ontology`, `owl:Class`, `owl:ObjectProperty`

### `xsd:`
- **URI**: `http://www.w3.org/2001/XMLSchema#`
- **Purpose**: XML Schema datatypes
- **Contents**: String, decimal, integer, date, dateTime
- **Example**: `xsd:string`, `xsd:decimal`, `xsd:date`

### `sh:`
- **URI**: `http://www.w3.org/ns/shacl#`
- **Purpose**: SHACL Shapes Constraint Language
- **Contents**: NodeShape, property, targetClass, message
- **Example**: `sh:NodeShape`, `sh:property`, `sh:targetClass`

### `dc:`
- **URI**: `http://purl.org/dc/terms/`
- **Purpose**: Dublin Core metadata terms
- **Contents**: Description, creator, created
- **Example**: `dc:description`, `dc:creator`, `dc:created`

### `skos:`
- **URI**: `http://www.w3.org/2004/02/skos/core#`
- **Purpose**: Simple Knowledge Organization System
- **Contents**: Definition, broader, narrower
- **Example**: `skos:definition`

### `prov:`
- **URI**: `http://www.w3.org/ns/prov#`
- **Purpose**: PROV Ontology for provenance
- **Contents**: Entity, wasGeneratedBy, wasAttributedTo
- **Example**: `prov:Entity`, `prov:wasGeneratedBy`

## Usage in Files

### finance-ontology.ttl
```turtle
@prefix : <http://example.org/finance#> .
@prefix chimera: <http://example.org/chimera#> .
```

### shapes.ttl
```turtle
@prefix : <http://example.org/finance#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
```

### approved_kg.ttl
```turtle
@prefix : <http://example.org/finance#> .
@prefix chimera: <http://example.org/chimera#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
```

## Chimera Namespace Details

### Provenance Properties
- `chimera:sourceChunk` - Reference to source document chunk
- `chimera:pageNumber` - Page number in source document
- `chimera:extractionTimestamp` - When extraction occurred
- `chimera:sourceDocument` - Source document filename

### Validation Properties
- `chimera:validationStatus` - VALID, QUARANTINED, REJECTED, PENDING
- `chimera:evidenceVerified` - Boolean indicating evidence verification
- `chimera:verificationMethod` - exact_match, substring, semantic

### Approval Properties
- `chimera:approvedBy` - User who approved the triple
- `chimera:approvalTimestamp` - When approval occurred
- `chimera:approvalNotes` - Notes from approving user

### Extraction Properties
- `chimera:extractorVersion` - Version of extraction pipeline
- `chimera:confidence` - Confidence score (0.0-1.0)
- `chimera:extractionMethod` - Method used for extraction

## Best Practices

1. **Use appropriate namespaces** for each type of data
2. **Be consistent** with namespace usage across files
3. **Document new namespaces** when extending the ontology
4. **Validate namespace consistency** during testing
5. **Update this document** when adding new namespaces

## Namespace Extensions

To add new namespaces:
1. Define the URI in relevant Turtle files
2. Add documentation to this file
3. Ensure consistent usage across the project
4. Update validation rules if needed

Last Updated: November 2024
