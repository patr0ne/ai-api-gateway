"""Static checks for the Alembic migration graph and model metadata."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from ai_api_gateway.models import Base


def test_alembic_has_one_head() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(project_root / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0001"]


def test_api_clients_metadata_matches_authentication_fields() -> None:
    table = Base.metadata.tables["api_clients"]

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "key_fingerprint",
        "is_active",
        "created_at",
    }
    assert table.c.key_fingerprint.unique is True
    assert table.c.key_fingerprint.index is True
