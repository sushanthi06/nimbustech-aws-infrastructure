#!/usr/bin/env python3
"""
NimbusTech Database Migration Rollback: v2 → v1

Reverses all changes made by migrate.py:
1. Drop 'user_tier' column from 'users' table
2. Drop 'processed_at' column from 'orders' table
3. Drop index on orders(created_at)
4. Remove migration record

This script is idempotent and safe to run multiple times.
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
from psycopg2 import sql

# Configuration from environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Migration metadata
MIGRATION_VERSION = 'v2'
MIGRATION_NAME = 'add_user_tier_and_processed_at'


def parse_database_url(url):
    """Parse DATABASE_URL into connection parameters."""
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Validate URL scheme (CWE-918 prevention)
    parsed = urlparse(url)
    if parsed.scheme not in ('postgres', 'postgresql'):
        raise ValueError(f"Invalid DATABASE_URL scheme: {parsed.scheme}")

    return {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path.lstrip('/'),
        'user': parsed.username,
        'password': parsed.password,
    }


def get_connection():
    """Establish database connection with secure parameters."""
    try:
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(
            **conn_params,
            connect_timeout=10,
            sslmode='prefer',
        )
        return conn
    except psycopg2.Error as e:
        # Don't expose connection details (CWE-209)
        print(f"ERROR: Failed to connect to database", file=sys.stderr)
        sys.exit(1)


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
            )
        """, (table_name, column_name))
        return cur.fetchone()[0]


def index_exists(conn, index_name):
    """Check if an index exists."""
    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE indexname = %s
            )
        """, (index_name,))
        return cur.fetchone()[0]


def migration_table_exists(conn):
    """Check if schema_migrations table exists."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'schema_migrations'
            )
        """)
        return cur.fetchone()[0]


def is_migration_applied(conn):
    """Check if this migration is recorded as applied."""
    if not migration_table_exists(conn):
        return False

    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute(
            "SELECT version FROM schema_migrations WHERE version = %s",
            (MIGRATION_VERSION,)
        )
        return cur.fetchone() is not None


def pre_rollback_checks(conn):
    """Validate database state before rollback."""
    print("\n=== Pre-Rollback Validation ===")

    # Check that tables exist
    with conn.cursor() as cur:
        for table in ['users', 'orders']:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))

            if not cur.fetchone()[0]:
                print(f"✗ Table '{table}' does not exist")
                sys.exit(1)
            else:
                print(f"✓ Table '{table}' exists")

    # Warn if data will be lost
    if column_exists(conn, 'users', 'user_tier'):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT user_tier) FROM users")
            distinct_tiers = cur.fetchone()[0]

            if distinct_tiers > 1:
                print(f"⚠ WARNING: {distinct_tiers} distinct user_tier values will be lost")

    if column_exists(conn, 'orders', 'processed_at'):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders WHERE processed_at IS NOT NULL")
            filled_count = cur.fetchone()[0]

            if filled_count > 0:
                print(f"⚠ WARNING: {filled_count:,} processed_at timestamps will be lost")

    print("\n✓ Pre-rollback checks passed")


def drop_user_tier_column(conn):
    """Drop user_tier column from users table."""
    if not column_exists(conn, 'users', 'user_tier'):
        print("✓ Column 'users.user_tier' does not exist (skipping)")
        return

    print("→ Dropping column 'users.user_tier'...")

    if DRY_RUN:
        print("  [DRY RUN] Would execute: ALTER TABLE users DROP COLUMN user_tier")
        return

    with conn.cursor() as cur:
        cur.execute("ALTER TABLE users DROP COLUMN user_tier")
        conn.commit()

    print("✓ Column 'users.user_tier' dropped successfully")


def drop_processed_at_column(conn):
    """Drop processed_at column from orders table."""
    if not column_exists(conn, 'orders', 'processed_at'):
        print("✓ Column 'orders.processed_at' does not exist (skipping)")
        return

    print("→ Dropping column 'orders.processed_at'...")

    if DRY_RUN:
        print("  [DRY RUN] Would execute: ALTER TABLE orders DROP COLUMN processed_at")
        return

    with conn.cursor() as cur:
        cur.execute("ALTER TABLE orders DROP COLUMN processed_at")
        conn.commit()

    print("✓ Column 'orders.processed_at' dropped successfully")


def drop_created_at_index(conn):
    """Drop index on orders(created_at)."""
    index_name = 'idx_orders_created_at'

    if not index_exists(conn, index_name):
        print(f"✓ Index '{index_name}' does not exist (skipping)")
        return

    print(f"→ Dropping index '{index_name}'...")

    if DRY_RUN:
        print(f"  [DRY RUN] Would execute: DROP INDEX {index_name}")
        return

    with conn.cursor() as cur:
        # Use identifier to safely construct index name (no SQL injection)
        cur.execute(
            sql.SQL("DROP INDEX CONCURRENTLY IF EXISTS {}").format(
                sql.Identifier(index_name)
            )
        )
        conn.commit()

    print(f"✓ Index '{index_name}' dropped successfully")


def remove_migration_record(conn):
    """Remove migration record from schema_migrations."""
    if not migration_table_exists(conn):
        print("✓ Migration table does not exist (skipping)")
        return

    if not is_migration_applied(conn):
        print("✓ Migration not recorded (skipping)")
        return

    print("→ Removing migration record...")

    if DRY_RUN:
        print(f"  [DRY RUN] Would delete migration record for {MIGRATION_VERSION}")
        return

    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute(
            "DELETE FROM schema_migrations WHERE version = %s",
            (MIGRATION_VERSION,)
        )
        conn.commit()

    print("✓ Migration record removed")


def post_rollback_checks(conn):
    """Validate database state after rollback."""
    print("\n=== Post-Rollback Validation ===")

    checks_passed = True

    # Check columns are dropped
    if column_exists(conn, 'users', 'user_tier'):
        print("✗ Column 'users.user_tier' still exists")
        checks_passed = False
    else:
        print("✓ Column 'users.user_tier' removed")

    if column_exists(conn, 'orders', 'processed_at'):
        print("✗ Column 'orders.processed_at' still exists")
        checks_passed = False
    else:
        print("✓ Column 'orders.processed_at' removed")

    # Check index is dropped
    if index_exists(conn, 'idx_orders_created_at'):
        print("✗ Index 'idx_orders_created_at' still exists")
        checks_passed = False
    else:
        print("✓ Index 'idx_orders_created_at' removed")

    # Check migration record is removed
    if is_migration_applied(conn):
        print("✗ Migration record still exists")
        checks_passed = False
    else:
        print("✓ Migration record removed")

    if not checks_passed:
        print("\n⚠ Post-rollback checks failed - investigate before proceeding")
        return False

    print("\n✓ All post-rollback checks passed")
    return True


def main():
    """Main rollback execution."""
    print(f"NimbusTech Database Rollback: {MIGRATION_NAME}")
    print(f"Version: {MIGRATION_VERSION}")
    print(f"Dry Run: {DRY_RUN}")
    print("-" * 60)

    # Confirm rollback (unless dry run)
    if not DRY_RUN:
        print("\n⚠ WARNING: This will permanently delete data in user_tier and processed_at columns")
        response = input("Type 'ROLLBACK' to confirm: ")
        if response != 'ROLLBACK':
            print("Rollback cancelled")
            return 1

    # Connect to database
    conn = get_connection()

    try:
        # Pre-rollback validation
        pre_rollback_checks(conn)

        # Execute rollback steps
        print("\n=== Executing Rollback ===")
        drop_created_at_index(conn)
        drop_processed_at_column(conn)
        drop_user_tier_column(conn)
        remove_migration_record(conn)

        # Post-rollback validation
        if not post_rollback_checks(conn):
            print("\nRollback completed but validation failed")
            return 1

        if not DRY_RUN:
            print(f"\n✓ Rollback {MIGRATION_VERSION} completed successfully")
        else:
            print("\n[DRY RUN] Rollback not executed (use DRY_RUN=false to apply)")

        return 0

    except psycopg2.Error as e:
        # Log error internally, don't expose details (CWE-209)
        print(f"\nERROR: Rollback failed - {type(e).__name__}", file=sys.stderr)
        conn.rollback()
        return 1

    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
