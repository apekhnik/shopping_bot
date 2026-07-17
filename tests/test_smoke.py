from shopping_bot import __version__
from shopping_bot.config import settings


def test_version_exposed() -> None:
    assert __version__ == "0.1.0"


def test_settings_load_with_defaults() -> None:
    assert settings.scan_interval_seconds > 0
    assert settings.varus_default_shop_id == 57
