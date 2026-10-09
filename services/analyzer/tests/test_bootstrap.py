from app import __version__
from app.main import create_app


def test_analyzer_version() -> None:
    assert __version__ == "0.1.0"


def test_app_factory_is_available() -> None:
    assert callable(create_app)
