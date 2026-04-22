"""Bundled Supabase schema assets — config, migrations, and seed helpers."""

from importlib.resources import files
from pathlib import Path


def migrations_dir() -> Path:
    """Absolute path to the bundled SQL migration files."""
    return Path(str(files("exegia.supabase").joinpath("migrations")))


def migration_files() -> list[Path]:
    """Sorted list of migration .sql paths, ready to pass to supabase db push."""
    return sorted(migrations_dir().glob("*.sql"))


def config_path() -> Path:
    """Absolute path to the bundled supabase config.toml."""
    return Path(str(files("exegia.supabase").joinpath("config.toml")))
