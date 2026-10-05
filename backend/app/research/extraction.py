"""Contract-path adapter for the persistence-free T2 extraction package."""

from app.research_extraction import (
    EXTRACTION_VERSION,
    PROMPT_VERSION,
    CandidateExtractionError,
    ExtractionBatchError,
    ExtractionInputError,
    ModelInvocationError,
    ModelOutputError,
    extract_candidates,
)

__all__ = [
    "EXTRACTION_VERSION",
    "PROMPT_VERSION",
    "CandidateExtractionError",
    "ExtractionBatchError",
    "ExtractionInputError",
    "ModelInvocationError",
    "ModelOutputError",
    "extract_candidates",
]
