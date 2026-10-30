"""Workspace-scoped preferences. Provider secrets never enter browser responses."""
import json
import os
import socket
import ipaddress
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field, ConfigDict

from app.config import get_settings
from app.tenancy import data_dir, workspace_write_lock
_key_lock = Lock()


class Features(BaseModel):
    model_config = ConfigDict(extra="forbid")
    foundations: bool = True
    glossary: bool = True
    quizzes: bool = True
    coding: bool = True
    visuals: bool = True
    paper_guidance: bool = True
    roadmap: bool = True
    graph: bool = True


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(default="", max_length=50)
    bio: str = Field(default="", max_length=500)
    institution: str = Field(default="", max_length=120)
    interests: str = Field(default="", max_length=300)
    level: str = Field(default="beginner", pattern="^(beginner|reader|researcher)$")
    weekly_hours: int = Field(default=5, ge=1, le=80)


class Provider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=120)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_key: bool = False


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Profile = Field(default_factory=Profile)
    features: Features = Field(default_factory=Features)
    provider: Provider = Field(default_factory=Provider)
    version: int = Field(default=0, ge=0)


def read():
    path = data_dir() / "preferences.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else {**Preferences().model_dump(exclude={"provider"}), "provider": {"enabled": False}}


def public():
    value = read()
    provider = value.get("provider", {})
    value["provider"] = {key: provider.get(key, default) for key, default in
                         (("enabled", False), ("base_url", ""), ("model", ""))}
    value["provider"]["has_key"] = bool(provider.get("encrypted_key"))
    value["default_model"] = get_settings().llm_model
    value["avatar_url"] = "/api/preferences/avatar" if (data_dir() / "avatar.png").is_file() else None
    return value


def _cipher():
    # One deployment key, independent from individual user data and API responses.
    path = Path(get_settings().data_dir) / ".model-key"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _key_lock:
        try:
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(Fernet.generate_key())
        except FileExistsError:
            pass
        return Fernet(path.read_bytes())


def validate_endpoint(value, *, resolve=True):
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
        raise ValueError("API 地址须为公开 HTTPS 地址，不能包含账号、参数或自定义端口")
    if resolve:
        try:
            addresses = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
        except OSError:
            raise ValueError("无法解析 API 域名，请检查地址") from None
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("API 地址不能指向本机、内网或保留地址")
    return value.rstrip("/")


def save(request: Preferences):
    with workspace_write_lock():
        old = read()
        if request.version != old.get("version", 0):
            raise ValueError("设置已在其他页面更新，请刷新后重试")
        provider = request.provider.model_dump(exclude={"api_key", "clear_key"})
        key = old.get("provider", {}).get("encrypted_key")
        if request.provider.clear_key:
            key = None
        if request.provider.api_key is not None and request.provider.api_key.strip():
            key = _cipher().encrypt(request.provider.api_key.strip().encode()).decode()
        if provider["enabled"]:
            provider["base_url"] = validate_endpoint(provider["base_url"])
            old_base = old.get("provider", {}).get("base_url")
            if old_base and urlsplit(old_base).netloc != urlsplit(provider["base_url"]).netloc and key and not request.provider.api_key:
                raise ValueError("更换 API 域名后，请重新输入对应的密钥")
            if not provider["model"].strip() or not key:
                raise ValueError("启用自定义模型需要填写模型名称和 API Key")
        provider["encrypted_key"] = key
        value = {"profile": request.profile.model_dump(), "features": request.features.model_dump(),
                 "provider": provider, "version": request.version + 1}
        directory = data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "preferences.json.tmp"
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(directory / "preferences.json")
    return public()


def provider():
    value = read().get("provider", {})
    if not value.get("enabled"):
        return None
    if not value.get("encrypted_key"):
        raise ValueError("自定义模型缺少密钥，请重新保存")
    base = validate_endpoint(value["base_url"], resolve=False)
    host = urlsplit(base).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("无法解析 API 域名，请检查地址") from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("API 地址不能指向本机、内网或保留地址")
    try:
        if not (Path(get_settings().data_dir) / ".model-key").is_file():
            raise InvalidToken()
        key = _cipher().decrypt(value["encrypted_key"].encode()).decode()
    except (InvalidToken, ValueError):
        raise ValueError("模型密钥无法解密，请重新填写并保存 API Key") from None
    return {"base_url": base, "host": host, "address": addresses[0][4][0], "model": value["model"], "api_key": key}


def enabled(name):
    return read().get("features", {}).get(name, True)
