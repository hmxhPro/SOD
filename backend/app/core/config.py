"""
app/core/config.py
------------------
Central application configuration via Pydantic Settings.
Reads from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
from typing import Literal


def _gdino_config_default() -> Path:
    """Use the config bundled with the installed groundingdino package."""
    try:
        import groundingdino
        pkg_config = Path(groundingdino.__file__).parent / "config" / "GroundingDINO_SwinT_OGC.py"
        if pkg_config.exists():
            return pkg_config
    except ImportError:
        pass
    return Path("./models/groundingdino/config/GroundingDINO_SwinT_OGC.py")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ──────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # ── Storage ─────────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = Path("./uploads")
    RESULTS_DIR: Path = Path("./results")

    # ── Detection Model ──────────────────────────────────────────────────────
    DETECTION_MODEL: Literal["florence2", "grounding_dino"] = "grounding_dino"
    DEVICE: str = "cuda:0"

    # Florence-2
    FLORENCE2_MODEL_ID: str = "microsoft/Florence-2-large"

    # Grounding DINO
    GDINO_CONFIG_PATH: Path = Field(default_factory=_gdino_config_default)
    GDINO_CHECKPOINT_PATH: Path = Path(
        "./models/groundingdino/weights/groundingdino_swint_ogc.pth"
    )

    # ── Detection Thresholds ─────────────────────────────────────────────────
    BOX_THRESHOLD: float = Field(default=0.35, ge=0.0, le=1.0)
    TEXT_THRESHOLD: float = Field(default=0.25, ge=0.0, le=1.0)

    # ── ByteTrack ────────────────────────────────────────────────────────────
    TRACK_THRESH: float = Field(default=0.5, ge=0.0, le=1.0)
    TRACK_BUFFER: int = 30
    MATCH_THRESH: float = Field(default=0.8, ge=0.0, le=1.0)

    # ── Processing ───────────────────────────────────────────────────────────
    # Run full detection every N frames; track in between for speed
    DETECTION_INTERVAL: int = Field(default=5, ge=1)
    MAX_CONCURRENT_TASKS: int = 2

    # ── Optional Redis ───────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    def ensure_dirs(self) -> None:
        """Create storage directories if they don't exist."""
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# Singleton instance
settings = Settings()
settings.ensure_dirs()
