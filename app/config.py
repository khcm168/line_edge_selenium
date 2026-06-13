from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except (ImportError, ModuleNotFoundError):

    def load_dotenv() -> bool:
        env_path = Path(".env")
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
        return True


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPREADSHEET_ID = "1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo"
DEFAULT_SPREADSHEET_TITLE = "地區會議資料V8.0 beta"
DEFAULT_DY2_TAB = "DY2"
DEFAULT_ACTS_TAB = "Acts"
DEFAULT_LIST_TAB = "List"
DEFAULT_DRAFT_SHEET = "LINE_Drafts"
DEFAULT_LOG_SHEET = "log"
DEFAULT_MATERIAL_SHEET = "LINE_Material"
DEFAULT_LOG_DIR = ROOT / "data" / "logs"
DEFAULT_SNAPSHOT_DIR = ROOT / "data" / "snapshots"
DEFAULT_TASK_DIR = ROOT / "data" / "tasks"
DEFAULT_MATERIAL_CATALOG = ROOT / "data" / "line_material_catalog.json"
DEFAULT_RULES_PATH = ROOT / "data" / "reminder_rules.json"
DEFAULT_ALLOWED_LIVE_TARGETS = ("洪啓明", "P103003", "001N1備份區", "Ya.ping")
DEFAULT_ALLOWED_GROUP_TARGETS = ("001N1備份區",)
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_AI_PROVIDER = "ollama"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma4:latest"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 180


def load_environment() -> None:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    project_name: str
    source_spreadsheet_id: str
    source_workbook_title: str
    dy2_tab_name: str
    acts_tab_name: str
    list_tab_name: str
    draft_sheet_name: str
    sheet_log_name: str
    material_sheet_name: str
    material_root: Path
    material_catalog_path: Path
    google_credentials_path: Path
    log_dir: Path
    snapshot_dir: Path
    task_dir: Path
    reminder_rules_path: Path
    allowed_live_targets: tuple[str, ...]
    allowed_group_targets: tuple[str, ...]
    openai_model: str
    ai_provider: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: int
    ai_enabled: bool
    response_watcher_enabled: bool
    response_watch_groups: tuple[str, ...]

    @classmethod
    def from_env(cls, *, require_google: bool = False) -> "Settings":
        load_environment()
        credentials = (
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or os.getenv("SERVICE_ACCOUNT_FILE")
            or ""
        )
        if require_google and not credentials:
            raise RuntimeError(
                "Missing GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_FILE."
            )
        return cls(
            project_name=os.getenv("PROJECT_NAME", "line_edge_selenium"),
            source_spreadsheet_id=os.getenv(
                "LINE_SOURCE_SPREADSHEET_ID",
                os.getenv(
                    "N1_SOURCE_SPREADSHEET_ID",
                    os.getenv("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
                ),
            ),
            source_workbook_title=os.getenv(
                "LINE_SOURCE_WORKBOOK_TITLE",
                DEFAULT_SPREADSHEET_TITLE,
            ),
            dy2_tab_name=os.getenv("LINE_DY2_TAB", DEFAULT_DY2_TAB),
            acts_tab_name=os.getenv("LINE_ACTS_TAB", DEFAULT_ACTS_TAB),
            list_tab_name=os.getenv("LINE_LIST_TAB", DEFAULT_LIST_TAB),
            draft_sheet_name=os.getenv("LINE_DRAFT_SHEET", DEFAULT_DRAFT_SHEET),
            sheet_log_name=os.getenv("LINE_LOG_SHEET", DEFAULT_LOG_SHEET),
            material_sheet_name=os.getenv(
                "LINE_MATERIAL_SHEET",
                DEFAULT_MATERIAL_SHEET,
            ),
            material_root=Path(os.getenv("LINE_MATERIAL_ROOT", "")),
            material_catalog_path=Path(
                os.getenv("LINE_MATERIAL_CATALOG", DEFAULT_MATERIAL_CATALOG)
            ),
            google_credentials_path=Path(credentials) if credentials else Path(),
            log_dir=Path(os.getenv("LINE_LOG_DIR", DEFAULT_LOG_DIR)),
            snapshot_dir=Path(os.getenv("LINE_SNAPSHOT_DIR", DEFAULT_SNAPSHOT_DIR)),
            task_dir=Path(os.getenv("LINE_TASK_DIR", DEFAULT_TASK_DIR)),
            reminder_rules_path=Path(
                os.getenv("LINE_REMINDER_RULES", DEFAULT_RULES_PATH)
            ),
            allowed_live_targets=_split_env(
                os.getenv("LINE_ALLOWED_LIVE_TARGETS"),
                DEFAULT_ALLOWED_LIVE_TARGETS,
            ),
            allowed_group_targets=_split_env(
                os.getenv("LINE_ALLOWED_GROUP_TARGETS"),
                DEFAULT_ALLOWED_GROUP_TARGETS,
            ),
            openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            ai_provider=os.getenv("LINE_AI_PROVIDER", DEFAULT_AI_PROVIDER).strip().casefold(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            ollama_timeout_seconds=_int_env(
                os.getenv("OLLAMA_TIMEOUT_SECONDS"),
                DEFAULT_OLLAMA_TIMEOUT_SECONDS,
            ),
            ai_enabled=_bool_env(os.getenv("LINE_AI_ENABLED"), True),
            response_watcher_enabled=_bool_env(
                os.getenv("LINE_RESPONSE_WATCHER_ENABLED"),
                False,
            ),
            response_watch_groups=_split_env(
                os.getenv("LINE_RESPONSE_WATCH_GROUPS"),
                DEFAULT_ALLOWED_GROUP_TARGETS,
            ),
        )


def _split_env(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _bool_env(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _int_env(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default
