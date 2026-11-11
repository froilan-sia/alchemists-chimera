# Sample Data for The Alchemist's Chimera - HKMA/Basel III Regulatory Framework

## Overview
This directory contains realistic sample regulatory documents and knowledge graphs for testing the PDF ingestion pipeline with HKMA (Hong Kong Monetary Authority) and Basel III regulatory content.

## File Structure

### PDF Documents
1. **hkma_capital_requirements.pdf**
   - Content: HKMA Supervisory Policy Manual SA-2 on capital adequacy requirements
   - Key concepts: CET1 ratio, Tier 1 capital, total capital ratio, leverage ratio, liquidity coverage ratio
   - Entities: HKMA, banks, authorized institutions
   - Purpose: Test extraction of regulatory requirements from HKMA documents

2. **basel_iii_framework.pdf**
   - Content: Basel III international regulatory framework
   - Key concepts: Capital buffers, leverage ratio, liquidity standards, risk coverage
   - Entities: Basel Committee, G-SIBs, D-SIBs
   - Purpose: Test extraction of international regulatory standards

3. **risk_weighted_assets.pdf**
   - Content: Risk-weighted assets calculation methodology
   - Key concepts: Credit risk RWA, market risk RWA, operational risk RWA
   - Entities: Financial Stability Board, banks with internal models
   - Purpose: Test extraction of technical regulatory calculations

### Ontology Files
1. **ontology/finance-ontology.ttl**
   - Comprehensive finance ontology with regulatory concepts
   - Classes: FinancialInstitution, Bank, RegulatoryBody, Regulation, CapitalRequirement
   - Properties: regulatedBy, subjectTo, hasCapitalRatio, minimumRequirement
   - Sample instances: HKMA, HSBC, Standard Chartered, Bank of China

2. **ontology/shapes.ttl**
   - SHACL shapes for validation of extracted knowledge
   - Shapes for: Bank validation, Capital ratio constraints, Provenance tracking
   - Constraints: Capital ratios must be between 0-100%, banks must have regulators

### Knowledge Graph
1. **data/graphs/approved_kg.ttl**
   - Pre-populated approved knowledge graph with validated triples
   - Contains: HKMA regulatory requirements, Basel III standards, bank-specific compliance data
   - Includes: Provenance metadata, evidence quotes, approval information
   - Purpose: Provide baseline knowledge for hybrid retrieval testing

## Key Regulatory Concepts in Sample Data

### Capital Requirements
- **CET1 Ratio**: 4.5% minimum (Common Equity Tier 1)
- **Tier 1 Ratio**: 6.0% minimum
- **Total Capital Ratio**: 8.0% minimum
- **Capital Conservation Buffer**: 2.5% additional
- **Countercyclical Buffer**: 0-2.5% variable

### Liquidity Requirements
- **Liquidity Coverage Ratio (LCR)**: 100% minimum
- **Net Stable Funding Ratio (NSFR)**: 100% minimum

### Leverage Requirements
- **Leverage Ratio**: 3.0% minimum of total exposures

### Risk Categories
- Credit Risk
- Market Risk
- Operational Risk
- Liquidity Risk

## Entities for Testing

### Regulatory Bodies
- HKMA (Hong Kong Monetary Authority)
- Basel Committee on Banking Supervision
- Financial Stability Board

### Banks
- HSBC Hong Kong
- Standard Chartered Hong Kong
- Bank of China (Hong Kong)

### Regulations
- HKMA Capital Adequacy Requirements
- Basel III Framework
- HKMA Liquidity Coverage Ratio
- Basel III Leverage Ratio

## Sample Queries for Testing

### Entity Relationship Queries
```
"What are the capital requirements for HSBC Hong Kong?"
"Which regulations apply to Bank of China Hong Kong?"
"Who regulates Standard Chartered in Hong Kong?"
```

### Regulatory Compliance Queries
```
"What is the minimum CET1 ratio under Basel III?"
"What liquidity ratios does HKMA require?"
"How is the leverage ratio calculated?"
```

### Technical Calculation Queries
```
"How are risk-weighted assets calculated for credit risk?"
"What are the risk weights for sovereign exposures?"
"What methods can banks use for operational risk RWA?"
```

## Usage for Testing PDF Ingestion Pipeline

### 1. Document Processing
- Upload PDFs to Surgeon's Table tab
- Verify extraction of entities and relationships
- Check evidence grounding with source text

### 2. Knowledge Graph Building
- Extract triples with proper provenance
- Validate against SHACL shapes
- Stage for human-in-the-loop approval

### 3. Hybrid Retrieval Testing
- Query approved knowledge graph
- Compare graph vs vector retrieval results
- Test fusion of multiple result types

### 4. Compliance Verification
- Verify air-gapped operation
- Check audit trail completeness
- Validate human approval workflow

## Data Characteristics for Testing

### Realistic Complexity
- Multiple regulatory frameworks (HKMA + Basel III)
- Technical calculation methodologies
- Real-world banking entities
- Provenance and audit requirements

### Extraction Challenges
- Numerical values with percentages
- Regulatory hierarchies and relationships
- Evidence grounding in source text
- SHACL validation requirements

### Compliance Requirements
- 100% air-gapped operation
- Human-in-the-loop approval
- Audit trail maintenance
- Transparency in AI-assisted extraction

## Maintenance and Updates

### Adding New Documents
1. Place new PDFs in `data/input/`
2. Update ontology if new concepts are introduced
3. Extend SHACL shapes for new validation rules
4. Add sample queries to this documentation

### Updating Ontology
1. Add new classes to `finance-ontology.ttl`
2. Define properties and relationships
3. Create corresponding SHACL shapes
4. Add sample instances for testing

### Knowledge Graph Updates
1. Add approved triples to `approved_kg.ttl`
2. Include provenance metadata
3. Maintain evidence quotes
4. Track approval history

## Notes for Developers

### Testing Coverage
- Unit tests should cover all regulatory concepts
- Integration tests should process sample PDFs end-to-end
- Performance tests should handle realistic document sizes
- Compliance tests should verify audit requirements

### Quality Assurance
- Verify extracted triples match source evidence
- Check SHACL validation passes/fails appropriately
- Confirm provenance metadata is complete
- Ensure human approval workflow functions correctly

### Performance Considerations
- Sample PDFs are sized for reasonable processing times
- Ontology should load quickly for validation
- Knowledge graph queries should be efficient
- Memory usage should be monitored during extraction

## Contact and Support

For questions about the sample data or suggestions for improvement:
- Project Repository: https://github.com/froilan-sia/alchemists-chimera
- Documentation: See project README.md
- Issues: Use GitHub issue tracker

## License
Sample data provided for testing purposes only. Based on publicly available regulatory information. Not for production use.

Last Updated: November 2024
