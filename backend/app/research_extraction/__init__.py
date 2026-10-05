"""Source-grounded extraction for the Research Atlas project workflow.

This package is intentionally persistence-free.  T1 owns storage and calls the
public ``extract_candidates`` function after it has frozen a document version.
"""

from app.research_extraction.candidates import (
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
