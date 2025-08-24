"""
prduction-grade config loader + DB bootstrap
- Dev: reads from .env (os.environ)
- prd: reads from AWS Secrets Manager + SSM Parameter Store with caching & retries

Files in this single module:
- Config models (dataclasses)
- Providers: EnvProvider, AWSProvider
- Loader: load_config()
- DB: Pooled connection helper for psycopg2
- Flask glue: hooks for app factory / teardown

Dependencies (add to requirements.txt):
    boto3>=1.34
    botocore>=1.34
    aws-secretsmanager-caching>=1.1.1  # optional; we fall back if missing
    psycopg2-binary>=2.9
    python-dotenv>=1.0  # only if you want local .env autoloading

Environment contract:
    APP_ENV=development|staging|prduction  # selects default backend
    CONFIG_BACKEND=env|aws                  # explicit override (optional)
    AWS_REGION=ap-northeast-1               # or your region
    # Secrets Manager IDs (prd)
    DB_SECRET_ID=papyrus/prd/db
    AUTH0_SECRET_ID=papyrus/prd/auth0
    FLASK_SECRET_ID=papyrus/prd/flask
    # SSM parameters (prd)
    SSM_AUTH0_CALLBACK=/papyrus/prd/auth0/callback_url

    # Optional tuning
    SECRET_CACHE_TTL=300     # seconds
    SSM_CACHE_TTL=120        # seconds
    DB_POOL_MIN=1
    DB_POOL_MAX=10
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.pool import SimpleConnectionPool

try:
    from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
except Exception:  # pragma: no cover - lib optional
    SecretCache = None  # type: ignore
    SecretCacheConfig = None  # type: ignore

import boto3
from botocore.config import Config as BotoConfig

# -----------------------------
# Models
# -----------------------------
@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    username: str
    password: str
    database: str

@dataclass(frozen=True)
class Auth0Config:
    domain: str
    client_id: str
    client_secret: str
    callback_url: str

@dataclass(frozen=True)
class AppConfig:
    db: DBConfig
    auth0: Auth0Config
    flask_secret_key: str

# -----------------------------
# Providers
# -----------------------------
class EnvProvider:
    """Development provider: pull straight from environment.
    Intentionally strict: raises KeyError if required vars are missing.
    """
    def __init__(self):
        # If using python-dotenv, load here to be nice in dev
        if os.getenv("APP_ENV", "development") != "prduction":
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except Exception:
                pass

    def _get(self, key: str) -> str:
        v = os.getenv(key)
        if v is None or v == "":
            raise KeyError(f"Missing required env var: {key}")
        return v

    def load(self) -> AppConfig:
        db = DBConfig(
            host=self._get("DB_HOST"),
            port=int(os.getenv("DB_PORT", 5432)),
            username=self._get("DB_USER"),
            password=self._get("DB_PASSWORD"),
            database=self._get("DB_NAME"),
        )
        auth0 = Auth0Config(
            domain=self._get("AUTH0_DOMAIN"),
            client_id=self._get("AUTH0_CLIENT_ID"),
            client_secret=self._get("AUTH0_CLIENT_SECRET"),
            callback_url=self._get("AUTH0_CALLBACK_URL"),
        )
        flask_secret = self._get("FLASK_SECRET_KEY")
        return AppConfig(db=db, auth0=auth0, flask_secret_key=flask_secret)


class _TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._data: Dict[str, Any] = {}
        self._ts: Dict[str, float] = {}

    def get(self, key: str):
        now = time.time()
        if key in self._data and now - self._ts.get(key, 0) < self.ttl:
            return self._data[key]
        return None

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._ts[key] = time.time()


class AWSProvider:
    """prduction provider: Secrets Manager + SSM with caching and retries."""
    def __init__(self, region: Optional[str] = None):
        region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise RuntimeError("AWS region not configured")
        self.region = region
        self._boto_cfg = BotoConfig(connect_timeout=3, read_timeout=5, retries={"max_attempts": 5, "mode": "standard"})
        self.sm = boto3.client("secretsmanager", region_name=self.region, config=self._boto_cfg)
        self.ssm = boto3.client("ssm", region_name=self.region, config=self._boto_cfg)

        # Secrets caching (prefer official cache if available)
        ttl = int(os.getenv("SECRET_CACHE_TTL", 300))
        if SecretCache:
            self.cache = SecretCache(  # type: ignore
                config=SecretCacheConfig(max_cache_size=1024),
                client=self.sm,
            )
            self._secret = self._secret_with_lib
        else:
            self.cache = _TTLCache(ttl)
            self._secret = self._secret_fallback

        self._ssm_cache = _TTLCache(int(os.getenv("SSM_CACHE_TTL", 120)))

    # --- Secrets helpers ---
    def _secret_with_lib(self, secret_id: str) -> Dict[str, Any]:
        raw = self.cache.get_secret_string(secret_id)  # type: ignore[attr-defined]
        return json.loads(raw)

    def _secret_fallback(self, secret_id: str) -> Dict[str, Any]:
        cached = self.cache.get(secret_id)
        if cached:
            return cached
        resp = self.sm.get_secret_value(SecretId=secret_id)
        data = json.loads(resp["SecretString"])  # type: ignore[index]
        self.cache.set(secret_id, data)
        return data

    # --- SSM helpers ---
    def _get_ssm_param(self, name: str, with_decryption: bool = True) -> str:
        print(f"[cfg] fetching SSM param: {name}", flush=True)
        cached = self._ssm_cache.get(name)
        if cached is not None:
            return cached
        resp = self.ssm.get_parameter(Name=name, WithDecryption=with_decryption)
        val = resp["Parameter"]["Value"]
        self._ssm_cache.set(name, val)
        return val

    def load(self) -> AppConfig:
        db_secret_id = os.getenv("DB_SECRET_ID", "papyrus/prd/db")
        auth0_secret_id = os.getenv("AUTH0_SECRET_ID", "papyrus/prd/auth0")
        flask_secret_id = os.getenv("FLASK_SECRET_ID", "papyrus/prd/flask")

        dbj = self._secret(db_secret_id)
        auth0j = self._secret(auth0_secret_id)
        flaskj = self._secret(flask_secret_id)

        # SSM for non-secret config (e.g., callback URL)
        cb_param = os.getenv("SSM_AUTH0_CALLBACK", "/papyrus/prd/auth0/callback_url")
        callback_url = self._get_ssm_param(cb_param, with_decryption=True)

        db = DBConfig(
            host=str(dbj.get("host")),
            port=int(dbj.get("port", 5432)),
            username=str(dbj.get("username")),
            password=str(dbj.get("password")),
            database=str(dbj.get("database") or dbj.get("name")),
        )
        auth0 = Auth0Config(
            domain=str(auth0j.get("domain")),
            client_id=str(auth0j.get("client_id")),
            client_secret=str(auth0j.get("client_secret")),
            callback_url=str(callback_url),
        )
        flask_secret = str(flaskj.get("secret_key"))
        return AppConfig(db=db, auth0=auth0, flask_secret_key=flask_secret)

# -----------------------------
# Loader (select backend)
# -----------------------------

def load_config() -> AppConfig:
    backend = os.getenv("CONFIG_BACKEND")
    if not backend:
        env = os.getenv("APP_ENV", "development").lower()
        backend = "aws" if env == "prduction" else "env"
    if backend == "aws":
        return AWSProvider().load()
    if backend == "env":
        return EnvProvider().load()
    raise RuntimeError(f"Unknown CONFIG_BACKEND: {backend}")

# -----------------------------
# DB Pool & Flask glue
# -----------------------------
class DBPool:
    def __init__(self, cfg: DBConfig):
        minconn = int(os.getenv("DB_POOL_MIN", 1))
        maxconn = int(os.getenv("DB_POOL_MAX", 10))
        self._pool = SimpleConnectionPool(
            minconn,
            maxconn,
            host=cfg.host,
            port=cfg.port,
            user=cfg.username,
            password=cfg.password,
            dbname=cfg.database,
            connect_timeout=5,
            application_name=os.getenv("APP_NAME", "papyrus-web"),
            sslmode=os.getenv("DB_SSLMODE", "prefer"),
        )

    def getconn(self):
        return self._pool.getconn()

    def putconn(self, conn):
        return self._pool.putconn(conn)

    def closeall(self):
        self._pool.closeall()


def init_db_pool(app_config: AppConfig) -> DBPool:
    return DBPool(app_config.db)
