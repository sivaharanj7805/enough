"""Tests for the migration runner."""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Import the migration module functions
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from migrate import discover_migrations, MIGRATIONS_DIR


class TestMigrateDiscovery:
    """Test migration file discovery."""

    def test_discover_finds_sql_files(self):
        """Should find SQL migration files."""
        migrations = discover_migrations()
        assert len(migrations) >= 3  # 001, 002, 003

    def test_discover_sorted_order(self):
        """Migrations should be sorted by version (filename)."""
        migrations = discover_migrations()
        versions = [v for v, _ in migrations]
        assert versions == sorted(versions)

    def test_migration_files_exist(self):
        """All discovered migration paths should exist."""
        migrations = discover_migrations()
        for version, path in migrations:
            assert path.exists(), f"Migration file {path} does not exist"

    def test_migrations_dir_exists(self):
        """Migrations directory should exist."""
        assert MIGRATIONS_DIR.is_dir()

    def test_version_naming(self):
        """Versions should follow NNN_ prefix pattern."""
        migrations = discover_migrations()
        for version, _ in migrations:
            assert version[:3].isdigit(), f"Migration {version} doesn't start with digits"
