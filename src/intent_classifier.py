import spacy
from typing import Dict, Any


class IntentClassifier:
    def __init__(self):
        # Fallback to small English model if not fully customized
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise ImportError("Please run: python -m spacy download en_core_web_sm")

        # Hardcoded structural keyword rules for absolute fallback
        self.regulatory_keywords = {
            "basel",
            "compliance",
            "regulation",
            "sec",
            "shacl",
            "requirement",
            "legal",
        }
        self.entity_keywords = {
            "subsidiary",
            "parent",
            "own",
            "owner",
            "ticker",
            "equity",
            "traded",
            "company",
        }

    def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Determines the Query Type and calculates the exact alpha (α) graph weight.
        """
        doc = self.nlp(query.lower())
        query_text = doc.text

        # 1. Check Regulatory Intent (Alpha = 0.7)
        if any(kw in query_text for kw in self.regulatory_keywords):
            return {
                "type": "Regulatory",
                "alpha": 0.7,
                "reason": "Regulatory keyword matched.",
            }

        # 2. Check Entity-Relationship Intent (Alpha = 0.8)
        # Check spaCy named entities for Organizations or Products
        has_org_entity = any(ent.label_ in {"ORG", "PRODUCT"} for ent in doc.ents)
        has_entity_kw = any(kw in query_text for kw in self.entity_keywords)

        if has_org_entity or has_entity_kw:
            return {
                "type": "Entity-Relationship",
                "alpha": 0.8,
                "reason": "Named entity or relational predicate detected.",
            }

        # 3. Check Hybrid Intent (Alpha = 0.5)
        # Mixed conversational text containing a blend of entities/concepts
        if len(doc) > 6 and (has_org_entity or has_entity_kw or "stock" in query_text):
            return {
                "type": "Hybrid",
                "alpha": 0.5,
                "reason": "Complex mixed entity/conceptual query structure.",
            }

        # 4. Default to Semantic Context (Alpha = 0.3)
        return {
            "type": "Semantic",
            "alpha": 0.3,
            "reason": "Abstract concept matching; default to vector preference.",
        }
