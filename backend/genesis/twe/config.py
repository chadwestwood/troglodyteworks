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
    asa_rcon_host: str | None = None
    asa_rcon_port: int | None = None
    asa_rcon_password: str | None = None
    asa_panel_config_path: str | None = "/opt/asa-control-panel/config.json"
    discord_client_id: str | None = None
    discord_client_secret: str | None = None
    discord_redirect_uri: str | None = None
    discord_install_redirect_uri: str | None = None
    discord_bot_token: str | None = None
    discord_bot_permissions: int | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    admin_emails: tuple[str, ...] = ()
    pterodactyl_panel_url: str | None = None
    pterodactyl_api_key: str | None = None
    pterodactyl_owner_user_id: int | None = None
    pterodactyl_location_id: int | None = None
    pterodactyl_nest_id: int | None = None
    pterodactyl_egg_id: int | None = None
    pterodactyl_docker_image: str | None = None
    pterodactyl_startup: str | None = None
    pterodactyl_memory_mb: int | None = None
    pterodactyl_swap_mb: int = 0
    pterodactyl_disk_mb: int | None = None
    pterodactyl_io_weight: int = 500
    pterodactyl_cpu_limit: int | None = None
    pterodactyl_dedicated_ip: bool = False
    pterodactyl_feature_databases: int = 0
    pterodactyl_feature_backups: int = 0
    pterodactyl_feature_allocations: int = 0
    pterodactyl_env_server_map: str | None = None
    pterodactyl_env_max_players: str | None = None

    @property
    def session_lifetime(self) -> timedelta:
        return timedelta(days=self.session_days)


def load_config() -> Config:
    load_env_file()
    health_port = os.environ.get("TWE_ASA_HEALTH_PORT")
    rcon_port = os.environ.get("TWE_ASA_RCON_PORT") or os.environ.get("RCON_PORT")
    discord_bot_permissions = os.environ.get("TROG_DISCORD_BOT_PERMISSIONS")
    pterodactyl_owner_user_id = os.environ.get("TWE_PTERODACTYL_OWNER_USER_ID")
    pterodactyl_location_id = os.environ.get("TWE_PTERODACTYL_LOCATION_ID")
    pterodactyl_nest_id = os.environ.get("TWE_PTERODACTYL_NEST_ID")
    pterodactyl_egg_id = os.environ.get("TWE_PTERODACTYL_EGG_ID")
    pterodactyl_memory_mb = os.environ.get("TWE_PTERODACTYL_MEMORY_MB")
    pterodactyl_swap_mb = os.environ.get("TWE_PTERODACTYL_SWAP_MB")
    pterodactyl_disk_mb = os.environ.get("TWE_PTERODACTYL_DISK_MB")
    pterodactyl_io_weight = os.environ.get("TWE_PTERODACTYL_IO_WEIGHT")
    pterodactyl_cpu_limit = os.environ.get("TWE_PTERODACTYL_CPU_LIMIT")
    pterodactyl_feature_databases = os.environ.get("TWE_PTERODACTYL_FEATURE_DATABASES")
    pterodactyl_feature_backups = os.environ.get("TWE_PTERODACTYL_FEATURE_BACKUPS")
    pterodactyl_feature_allocations = os.environ.get("TWE_PTERODACTYL_FEATURE_ALLOCATIONS")
    return Config(
        database_url=os.environ.get("TWE_DATABASE_URL", "postgresql://twe_app@localhost:5432/twe"),
        session_cookie_name=os.environ.get("TWE_SESSION_COOKIE_NAME", "twe_session"),
        session_days=int(os.environ.get("TWE_SESSION_DAYS", "7")),
        cookie_secure=os.environ.get("TWE_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        asa_expected_process=os.environ.get("TWE_ASA_EXPECTED_PROCESS"),
        asa_health_host=os.environ.get("TWE_ASA_HEALTH_HOST"),
        asa_health_port=int(health_port) if health_port else None,
        asa_rcon_host=os.environ.get("TWE_ASA_RCON_HOST") or os.environ.get("RCON_HOST"),
        asa_rcon_port=int(rcon_port) if rcon_port else None,
        asa_rcon_password=os.environ.get("TWE_ASA_RCON_PASSWORD") or os.environ.get("RCON_PASSWORD"),
        asa_panel_config_path=os.environ.get("TWE_ASA_PANEL_CONFIG_PATH", "/opt/asa-control-panel/config.json"),
        discord_client_id=os.environ.get("TROG_DISCORD_CLIENT_ID"),
        discord_client_secret=os.environ.get("TROG_DISCORD_CLIENT_SECRET"),
        discord_redirect_uri=os.environ.get("TROG_DISCORD_REDIRECT_URI"),
        discord_install_redirect_uri=os.environ.get("TROG_DISCORD_INSTALL_REDIRECT_URI"),
        discord_bot_token=os.environ.get("TROG_DISCORD_BOT_TOKEN"),
        discord_bot_permissions=int(discord_bot_permissions) if discord_bot_permissions else None,
        google_client_id=os.environ.get("TWE_GOOGLE_CLIENT_ID"),
        google_client_secret=os.environ.get("TWE_GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=os.environ.get("TWE_GOOGLE_REDIRECT_URI"),
        admin_emails=parse_csv(os.environ.get("TWE_ADMIN_EMAILS")),
        pterodactyl_panel_url=os.environ.get("TWE_PTERODACTYL_PANEL_URL"),
        pterodactyl_api_key=os.environ.get("TWE_PTERODACTYL_API_KEY"),
        pterodactyl_owner_user_id=int(pterodactyl_owner_user_id) if pterodactyl_owner_user_id else None,
        pterodactyl_location_id=int(pterodactyl_location_id) if pterodactyl_location_id else None,
        pterodactyl_nest_id=int(pterodactyl_nest_id) if pterodactyl_nest_id else None,
        pterodactyl_egg_id=int(pterodactyl_egg_id) if pterodactyl_egg_id else None,
        pterodactyl_docker_image=os.environ.get("TWE_PTERODACTYL_DOCKER_IMAGE"),
        pterodactyl_startup=os.environ.get("TWE_PTERODACTYL_STARTUP"),
        pterodactyl_memory_mb=int(pterodactyl_memory_mb) if pterodactyl_memory_mb else None,
        pterodactyl_swap_mb=int(pterodactyl_swap_mb) if pterodactyl_swap_mb else 0,
        pterodactyl_disk_mb=int(pterodactyl_disk_mb) if pterodactyl_disk_mb else None,
        pterodactyl_io_weight=int(pterodactyl_io_weight) if pterodactyl_io_weight else 500,
        pterodactyl_cpu_limit=int(pterodactyl_cpu_limit) if pterodactyl_cpu_limit else None,
        pterodactyl_dedicated_ip=os.environ.get("TWE_PTERODACTYL_DEDICATED_IP", "").lower() in {"1", "true", "yes"},
        pterodactyl_feature_databases=int(pterodactyl_feature_databases) if pterodactyl_feature_databases else 0,
        pterodactyl_feature_backups=int(pterodactyl_feature_backups) if pterodactyl_feature_backups else 0,
        pterodactyl_feature_allocations=int(pterodactyl_feature_allocations) if pterodactyl_feature_allocations else 0,
        pterodactyl_env_server_map=os.environ.get("TWE_PTERODACTYL_ENV_SERVER_MAP", "TheIsland_WP"),
        pterodactyl_env_max_players=os.environ.get("TWE_PTERODACTYL_ENV_MAX_PLAYERS", "70"),
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


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())
