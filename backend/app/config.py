from functools import lru_cache
import os
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "atlasdev"

    grobid_base_url: str = "http://localhost:8070"

    data_dir: str = "./data"
    runtime_mode: str = "local"
    runtime_id: str = ""
    access_mode: Literal["local", "multiuser"] = "local"
    require_login: bool = True
    registration_enabled: bool = True
    offline_mode: bool = False
    session_secure_cookie: bool = True
    session_lifetime_hours: int = Field(default=12, ge=1, le=168)
    auth_public_url: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_security: Literal["starttls", "ssl", "plain"] = "starttls"
    smtp_timeout_seconds: float = Field(default=10, gt=0, le=60)
    password_reset_minutes: int = Field(default=30, ge=5, le=120)
    max_users: int = Field(default=20, ge=1, le=1000)
    user_pdf_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    user_pdf_max_pages: int = Field(default=50, ge=1, le=1000)
    user_max_papers: int = Field(default=20, ge=1, le=1000)
    user_storage_max_bytes: int = Field(default=100 * 1024 * 1024, ge=1024 * 1024)
    task_timeout_seconds: int = Field(default=900, ge=1, le=7200)
    arxiv_categories: str = "cs.RO,cs.LG,cs.AI"
    s2_api_base: str = "https://api.semanticscholar.org/graph/v1"

    llm_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_api_key: str = ""
    llm_model: str = "qwen3.8-flash"
    llm_embed_model: str = "text-embedding-v4"
    llm_timeout_seconds: float = 120.0
    llm_parallel_requests: int = Field(default=3, ge=1, le=6)
    tutor_default_api_key: str = ""

    # Explicit opt-in after approval of outbound data and model-call budget.
    research_model_enabled: bool = False
    research_model_enable_thinking: bool | None = None
    research_model_schema_require_all: bool = True
    research_model_response_format: Literal["json_object", "json_schema"] = "json_object"
    research_model_timeout_seconds: float = Field(default=60, gt=0, le=180)
    research_model_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    research_model_max_input_chars: int = Field(default=60000, ge=1000, le=200000)
    research_model_max_requests: int = Field(default=16, ge=1, le=64)
    knowledge_model_enabled: bool = True
    knowledge_parser_timeout_seconds: int = Field(default=1200, ge=30, le=7200)
    knowledge_use_docling: bool = True
    knowledge_formula_vision_enabled: bool = True

    @model_validator(mode="after")
    def isolate_multiuser_providers(self):
        # Shared graph namespaces and paid providers have no per-user quota
        # ledger yet. A configured local key must never enable them here.
        if self.access_mode == "multiuser" or self.offline_mode:
            if not self.offline_mode and not self.tutor_default_api_key:
                self.tutor_default_api_key = self.dashscope_api_key
            self.dashscope_api_key = ""
            self.research_model_enabled = False
            self.knowledge_model_enabled = False
        if self.offline_mode:
            self.tutor_default_api_key = ""
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=os.environ.get("ATLAS_ENV_FILE", ".env"))
