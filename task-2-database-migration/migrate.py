#!/usr/bin/env python3
"""
NimbusTech Database Migration: v1 → v2

Schema Changes:
1. Add 'user_tier' column (VARCHAR, default 'free') to 'users' table
2. Add 'processed_at' timestamp column (nullable) to 'orders' table
3. Add index on orders(created_at)
4. Backfill 'processed_at' = created_at + 2 hours for completed orders

This script is idempotent and safe to run multiple times.
"""

import os
import sys
import time
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configuration from environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '10000'))

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
            sslmode='prefer',  # Use SSL if available
        )
        return conn
    except psycopg2.Error as e:
        # Don't expose connection details in error message (CWE-209)
        print(f"ERROR: Failed to connect to database", file=sys.stderr)
        sys.exit(1)


def ensure_migration_table(conn):
    """Create migration tracking table if it doesn't exist."""
    with conn.cursor() as cur:
        # Use parameterized queries - no SQL injection risk here as no user input
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()


def is_migration_applied(conn):
    """Check if this migration has already been applied."""
    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute(
            "SELECT version FROM schema_migrations WHERE version = %s",
            (MIGRATION_VERSION,)
        )
        return cur.fetchone() is not None


def record_migration(conn):
    """Record that this migration has been applied."""
    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
            (MIGRATION_VERSION, MIGRATION_NAME)
        )
        conn.commit()


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


def get_table_row_count(conn, table_name):
    """Get approximate row count for a table."""
    with conn.cursor() as cur:
        # Use identifier to safely construct table name (no SQL injection)
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
        )
        return cur.fetchone()[0]


def pre_migration_checks(conn):
    """Validate database state before migration."""
    print("\n=== Pre-Migration Validation ===")

    checks_passed = True

    # Check that required tables exist
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
                checks_passed = False
            else:
                count = get_table_row_count(conn, table)
                print(f"✓ Table '{table}' exists ({count:,} rows)")

    # Check that required columns exist
    required_columns = {
        'orders': ['created_at', 'status']
    }

    for table, columns in required_columns.items():
        for column in columns:
            if not column_exists(conn, table, column):
                print(f"✗ Column '{table}.{column}' does not exist")
                checks_passed = False
            else:
                print(f"✓ Column '{table}.{column}' exists")

    if not checks_passed:
        print("\nPre-migration checks failed. Aborting.")
        sys.exit(1)

    print("\n✓ All pre-migration checks passed")


def add_user_tier_column(conn):
    """Add user_tier column to users table."""
    if column_exists(conn, 'users', 'user_tier'):
        print("✓ Column 'users.user_tier' already exists (skipping)")
        return

    print("→ Adding column 'users.user_tier'...")

    if DRY_RUN:
        print("  [DRY RUN] Would execute: ALTER TABLE users ADD COLUMN user_tier VARCHAR(20) DEFAULT 'free'")
        return

    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN user_tier VARCHAR(20) DEFAULT 'free' NOT NULL
        """)
        conn.commit()

    print("✓ Column 'users.user_tier' added successfully")


def add_processed_at_column(conn):
    """Add processed_at column to orders table."""
    if column_exists(conn, 'orders', 'processed_at'):
        print("✓ Column 'orders.processed_at' already exists (skipping)")
        return

    print("→ Adding column 'orders.processed_at'...")

    if DRY_RUN:
        print("  [DRY RUN] Would execute: ALTER TABLE orders ADD COLUMN processed_at TIMESTAMP")
        return

    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE orders
            ADD COLUMN processed_at TIMESTAMP
        """)
        conn.commit()

    print("✓ Column 'orders.processed_at' added successfully")


def add_created_at_index(conn):
    """Add index on orders(created_at)."""
    index_name = 'idx_orders_created_at'

    if index_exists(conn, index_name):
        print(f"✓ Index '{index_name}' already exists (skipping)")
        return

    print(f"→ Creating index '{index_name}'...")

    if DRY_RUN:
        print(f"  [DRY RUN] Would execute: CREATE INDEX {index_name} ON orders(created_at)")
        return

    with conn.cursor() as cur:
        # Create index concurrently to avoid locking table
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur.execute(
            sql.SQL("CREATE INDEX CONCURRENTLY {} ON orders(created_at)").format(
                sql.Identifier(index_name)
            )
        )
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)

    print(f"✓ Index '{index_name}' created successfully")


def backfill_processed_at(conn):
    """Backfill processed_at = created_at + 2 hours for completed orders."""
    print("\n→ Backfilling 'processed_at' for completed orders...")

    # Count orders that need backfilling
    with conn.cursor() as cur:
        # Parameterized query (CWE-89 prevention)
        cur.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE status = %s AND processed_at IS NULL
        """, ('completed',))

        total_to_backfill = cur.fetchone()[0]

    if total_to_backfill == 0:
        print("✓ No orders need backfilling (all completed orders already have processed_at)")
        return

    print(f"  Found {total_to_backfill:,} orders to backfill")

    if DRY_RUN:
        print(f"  [DRY RUN] Would backfill {total_to_backfill:,} orders in batches of {BATCH_SIZE:,}")
        return

    # Backfill in batches to avoid long-running transactions
    total_updated = 0
    start_time = time.time()

    while total_updated < total_to_backfill:
        with conn.cursor() as cur:
            # Parameterized query (CWE-89 prevention)
            cur.execute("""
                UPDATE orders
                SET processed_at = created_at + INTERVAL '2 hours'
                WHERE id IN (
                    SELECT id
                    FROM orders
                    WHERE status = %s AND processed_at IS NULL
                    LIMIT %s
                )
            """, ('completed', BATCH_SIZE))

            updated = cur.rowcount
            total_updated += updated
            conn.commit()

            elapsed = time.time() - start_time
            rate = total_updated / elapsed if elapsed > 0 else 0
            remaining = (total_to_backfill - total_updated) / rate if rate > 0 else 0

            print(f"  Progress: {total_updated:,}/{total_to_backfill:,} ({total_updated*100//total_to_backfill}%) "
                  f"- {rate:.0f} rows/sec - ETA: {remaining:.0f}s")

            if updated == 0:
                break

    print(f"✓ Backfilled {total_updated:,} orders in {time.time() - start_time:.1f}s")


def post_migration_checks(conn):
    """Validate database state after migration."""
    print("\n=== Post-Migration Validation ===")

    checks_passed = True

    # Check columns exist
    if not column_exists(conn, 'users', 'user_tier'):
        print("✗ Column 'users.user_tier' does not exist")
        checks_passed = False
    else:
        print("✓ Column 'users.user_tier' exists")

    if not column_exists(conn, 'orders', 'processed_at'):
        print("✗ Column 'orders.processed_at' does not exist")
        checks_passed = False
    else:
        print("✓ Column 'orders.processed_at' exists")

    # Check index exists
    if not index_exists(conn, 'idx_orders_created_at'):
        print("✗ Index 'idx_orders_created_at' does not exist")
        checks_passed = False
    else:
        print("✓ Index 'idx_orders_created_at' exists")

    # Verify backfill completed
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE status = %s AND processed_at IS NULL
        """, ('completed',))

        null_count = cur.fetchone()[0]

        if null_count > 0:
            print(f"⚠ Warning: {null_count:,} completed orders still have NULL processed_at")
        else:
            print("✓ All completed orders have processed_at set")

    # Verify default value works
    with conn.cursor() as cur:
        cur.execute("SELECT user_tier FROM users LIMIT 1")
        result = cur.fetchone()
        if result:
            print(f"✓ Sample user_tier value: '{result[0]}'")

    if not checks_passed:
        print("\n⚠ Post-migration checks failed - investigate before proceeding")
        return False

    print("\n✓ All post-migration checks passed")
    return True


def main():
    """Main migration execution."""
    print(f"NimbusTech Database Migration: {MIGRATION_NAME}")
    print(f"Version: {MIGRATION_VERSION}")
    print(f"Dry Run: {DRY_RUN}")
    print(f"Batch Size: {BATCH_SIZE:,}")
    print("-" * 60)

    # Connect to database
    conn = get_connection()

    try:
        # Ensure migration tracking table exists
        ensure_migration_table(conn)

        # Check if already applied
        if is_migration_applied(conn):
            print(f"\n✓ Migration {MIGRATION_VERSION} already applied (idempotent)")
            post_migration_checks(conn)
            return 0

        # Pre-migration validation
        pre_migration_checks(conn)

        # Execute migration steps
        print("\n=== Executing Migration ===")
        add_user_tier_column(conn)
        add_processed_at_column(conn)
        add_created_at_index(conn)
        backfill_processed_at(conn)

        # Post-migration validation
        if not post_migration_checks(conn):
            print("\nMigration completed but validation failed")
            return 1

        # Record migration as applied
        if not DRY_RUN:
            record_migration(conn)
            print(f"\n✓ Migration {MIGRATION_VERSION} applied successfully")
        else:
            print("\n[DRY RUN] Migration not recorded (use DRY_RUN=false to apply)")

        return 0

    except psycopg2.Error as e:
        # Log error internally, don't expose details to user (CWE-209)
        print(f"\nERROR: Migration failed - {type(e).__name__}", file=sys.stderr)
        conn.rollback()
        return 1

    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
