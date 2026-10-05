from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "atlasdev"

    grobid_base_url: str = "http://localhost:8070"

    data_dir: str = "./data"
    arxiv_categories: str = "cs.RO,cs.LG,cs.AI"
    s2_api_base: str = "https://api.semanticscholar.org/graph/v1"

    llm_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_api_key: str = ""
    llm_model: str = "qwen3.7-flash"
    llm_embed_model: str = "text-embedding-v4"
    llm_timeout_seconds: float = 120.0

    # Explicit opt-in after approval of outbound data and model-call budget.
    research_model_enabled: bool = False
    research_model_response_format: Literal["json_object", "json_schema"] = "json_object"
    research_model_timeout_seconds: float = Field(default=60, gt=0, le=180)
    research_model_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    research_model_max_input_chars: int = Field(default=60000, ge=1000, le=200000)
    research_model_max_requests: int = Field(default=16, ge=1, le=64)


@lru_cache
def get_settings() -> Settings:
    return Settings()
