import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class Config:
    database_url: str
    session_cookie_name: str = "twe_session"
    session_days: int = 7
    cookie_secure: bool = False
    asa_expected_process: str | None = None
    asa_health_host: str | None = None
    asa_health_port: int | None = None

    @property
    def session_lifetime(self) -> timedelta:
        return timedelta(days=self.session_days)


def load_config() -> Config:
    load_env_file()
    port = os.environ.get("TWE_ASA_HEALTH_PORT")
    return Config(
        database_url=os.environ.get("TWE_DATABASE_URL", "postgresql://twe_app@localhost:5432/twe"),
        session_cookie_name=os.environ.get("TWE_SESSION_COOKIE_NAME", "twe_session"),
        session_days=int(os.environ.get("TWE_SESSION_DAYS", "7")),
        cookie_secure=os.environ.get("TWE_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        asa_expected_process=os.environ.get("TWE_ASA_EXPECTED_PROCESS"),
        asa_health_host=os.environ.get("TWE_ASA_HEALTH_HOST"),
        asa_health_port=int(port) if port else None,
    )


def load_env_file():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), _clean_env_value(value.strip()))


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
