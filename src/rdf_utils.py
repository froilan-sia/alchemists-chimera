"""Shared RDF label and graph-result formatting helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


RDF_NAMESPACES = {
    "http://example.org/finance#": "finance",
    "http://example.org/chimera#": "chimera",
    "http://alchemists-chimera.org/": "chimera",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
    "http://www.w3.org/ns/shacl#": "sh",
    "http://www.w3.org/ns/prov#": "prov",
}
RDF_TERM_PATTERN = re.compile(
    r"https?://[^\s|<>\"']+|\b(?:finance|chimera|rdf|rdfs|owl|xsd|sh|prov):"
    r"[A-Za-z_][A-Za-z0-9_.-]*\b"
)


def readable_local_name(local_name: str) -> str:
    """Turn an RDF local name into a readable label."""
    words = local_name.replace("_", " ").replace("-", " ")
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words)
    words = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", words)
    words = re.sub(r"\s+", " ", words).strip()
    return words or local_name


def format_rdf_term(term: Any) -> str:
    """Format known RDF identifiers as readable labels with compact CURIEs."""
    value = str(term)
    if not value:
        return value

    if value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        local_name = parsed.fragment or parsed.path.rsplit("/", 1)[-1]
        for namespace, prefix in RDF_NAMESPACES.items():
            if value.startswith(namespace):
                local_name = value[len(namespace):]
                return f"{readable_local_name(local_name)} ({prefix}:{local_name})"
        return readable_local_name(local_name)

    match = re.fullmatch(
        r"(?P<prefix>finance|chimera|rdf|rdfs|owl|xsd|sh|prov):(?P<local>.+)",
        value,
    )
    if match:
        local_name = match.group("local")
        return f"{readable_local_name(local_name)} ({value})"
    return value


def format_rdf_text(text: Any) -> str:
    """Replace raw RDF/OWL identifiers in text with readable labels."""
    return RDF_TERM_PATTERN.sub(
        lambda match: format_rdf_term(match.group(0)), str(text)
    )
