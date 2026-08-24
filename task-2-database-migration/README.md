# Task 2: Database Migration Script

## Overview

Idempotent Python migration script to upgrade NimbusTech's PostgreSQL database from schema v1 to v2. Includes rollback capability, validation checks, and progress reporting.

## Schema Changes (v1 → v2)

| Change | Description | Impact |
|--------|-------------|--------|
| Add `users.user_tier` | VARCHAR(20), default 'free' | Enables tiered user management |
| Add `orders.processed_at` | TIMESTAMP, nullable | Tracks order processing time |
| Add index `idx_orders_created_at` | Index on `orders(created_at)` | Improves query performance for date-range queries |
| Backfill `processed_at` | Set to `created_at + 2 hours` for completed orders | Historical data consistency |

## Features

✅ **Idempotent** - Safe to run multiple times, skips already-applied changes  
✅ **Parameterized queries** - No SQL injection vulnerabilities  
✅ **Batch processing** - Handles large tables (millions of rows)  
✅ **Dry-run mode** - Preview changes before applying  
✅ **Pre/post validation** - Verifies database state before and after  
✅ **Progress reporting** - Real-time updates during backfill  
✅ **Rollback script** - Clean reversion to v1 schema  
✅ **Environment-based config** - No hardcoded credentials  

## Prerequisites

- Python 3.8+
- PostgreSQL 12+
- Network access to RDS instance (run from EC2 in same VPC)

## Installation

```bash
cd task-2-database-migration

# Install dependencies
pip install -r requirements.txt

# Or use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Set required environment variables:

```bash
# Required: PostgreSQL connection string
export DATABASE_URL="postgresql://username:password@host:5432/dbname"

# Optional: Dry-run mode (default: false)
export DRY_RUN="true"

# Optional: Batch size for backfill (default: 10000)
export BATCH_SIZE="50000"
```

### Finding DATABASE_URL

If using CloudFormation outputs from Task 1:

```bash
# Get RDS endpoint
RDS_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-rds \
  --query 'Stacks[0].Outputs[?OutputKey==`DBEndpoint`].OutputValue' \
  --output text)

# Construct DATABASE_URL (replace PASSWORD)
export DATABASE_URL="postgresql://nimbusadmin:PASSWORD@${RDS_ENDPOINT}/nimbustechdb"
```

## Usage

### Running Migration

```bash
# 1. Dry-run first (see what would change)
export DRY_RUN="true"
python migrate.py

# 2. Review output, then apply for real
export DRY_RUN="false"
python migrate.py

# Or in one line:
DATABASE_URL="postgresql://..." python migrate.py
```

### Expected Output

```
NimbusTech Database Migration: add_user_tier_and_processed_at
Version: v2
Dry Run: False
Batch Size: 10,000
------------------------------------------------------------

=== Pre-Migration Validation ===
✓ Table 'users' exists (125,000 rows)
✓ Table 'orders' exists (1,500,000 rows)
✓ Column 'orders.created_at' exists
✓ Column 'orders.status' exists

✓ All pre-migration checks passed

=== Executing Migration ===
→ Adding column 'users.user_tier'...
✓ Column 'users.user_tier' added successfully
→ Adding column 'orders.processed_at'...
✓ Column 'orders.processed_at' added successfully
→ Creating index 'idx_orders_created_at'...
✓ Index 'idx_orders_created_at' created successfully

→ Backfilling 'processed_at' for completed orders...
  Found 820,000 orders to backfill
  Progress: 10,000/820,000 (1%) - 2,500 rows/sec - ETA: 324s
  Progress: 820,000/820,000 (100%) - 2,450 rows/sec - ETA: 0s
✓ Backfilled 820,000 orders in 334.7s

=== Post-Migration Validation ===
✓ Column 'users.user_tier' exists
✓ Column 'orders.processed_at' exists
✓ Index 'idx_orders_created_at' exists
✓ All completed orders have processed_at set
✓ Sample user_tier value: 'free'

✓ All post-migration checks passed

✓ Migration v2 applied successfully
```

### Running Rollback

```bash
# Rollback requires confirmation (type 'ROLLBACK' when prompted)
python rollback.py

# Or dry-run first:
DRY_RUN="true" python rollback.py
```

## Estimated Runtime

Based on table size and typical hardware (db.t3.medium):

| Orders Table Size | Estimated Time | Notes |
|-------------------|----------------|-------|
| 100K rows | ~40 seconds | Mostly schema changes |
| 1M rows | ~7 minutes | ~2,500 rows/sec backfill |
| 10M rows | ~70 minutes | Consider running during maintenance window |

**Schema changes (ALTER TABLE, CREATE INDEX)** take < 1 second on empty tables, longer on large tables with data.

**Backfill performance** depends on:
- Database instance size (CPU, I/O)
- Concurrent load on database
- Network latency (run from EC2 in same VPC)

## Validation Checks

### Pre-Migration
- ✓ Tables `users` and `orders` exist
- ✓ Required columns exist (`orders.created_at`, `orders.status`)
- ✓ Row counts reported for awareness

### Post-Migration
- ✓ New columns exist (`users.user_tier`, `orders.processed_at`)
- ✓ Index exists (`idx_orders_created_at`)
- ✓ All completed orders have `processed_at` populated
- ✓ Default value ('free') applies to new `user_tier` values

## Idempotency

The script is safe to run multiple times:

- Checks if migration already recorded in `schema_migrations` table
- Skips adding columns/indexes that already exist
- Skips backfilling rows that already have `processed_at` set

**Use case:** If migration fails mid-backfill (network timeout, instance restart), re-run to continue from where it left off.

## Security Features

Following `secure-python` guidelines:

✅ **Parameterized queries** - All SQL uses `%s` placeholders, never f-strings  
✅ **URL validation** - Checks `DATABASE_URL` scheme is `postgres://` or `postgresql://`  
✅ **Environment variables** - No hardcoded credentials  
✅ **Error sanitization** - Doesn't expose connection details in error messages  
✅ **SSL preference** - Uses `sslmode='prefer'` for encrypted connections  

## Troubleshooting

### Connection timeout
```
ERROR: Failed to connect to database
```

**Solutions:**
- Check security group allows connection from your IP/EC2
- Verify RDS endpoint is correct
- Check DATABASE_URL format

### Migration already applied
```
✓ Migration v2 already applied (idempotent)
```

**This is normal** - script detected migration was already run. To force re-run:

```sql
-- Connect to database and remove migration record
DELETE FROM schema_migrations WHERE version = 'v2';
```

### Slow backfill
```
Progress: 50,000/1,000,000 (5%) - 200 rows/sec - ETA: 4750s
```

**Solutions:**
- Increase batch size: `export BATCH_SIZE="50000"`
- Run during off-peak hours
- Upgrade RDS instance temporarily (scale vertically)
- Consider splitting backfill into multiple sessions

### Rollback confirmation required
```
⚠ WARNING: This will permanently delete data in user_tier and processed_at columns
Type 'ROLLBACK' to confirm:
```

**This is intentional** - rollback deletes data. Type `ROLLBACK` (case-sensitive) to proceed.

## Testing Recommendations

### On Staging Database

```bash
# 1. Clone production data to staging
aws rds create-db-snapshot --db-instance-identifier prod-db \
  --db-snapshot-identifier pre-migration-test

aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier staging-db \
  --db-snapshot-identifier pre-migration-test

# 2. Run migration on staging
export DATABASE_URL="postgresql://user:pass@staging-db:5432/dbname"
python migrate.py

# 3. Verify application works with new schema

# 4. Test rollback
python rollback.py

# 5. Verify application works with old schema
```

### On Production

```bash
# 1. Create backup snapshot
aws rds create-db-snapshot \
  --db-instance-identifier nimbustech-db \
  --db-snapshot-identifier pre-v2-migration-$(date +%Y%m%d-%H%M)

# 2. Enable maintenance mode (optional)
# Stop ALB or set /health endpoint to return 503

# 3. Run migration
python migrate.py

# 4. Disable maintenance mode

# 5. Monitor application and database metrics
```

## Production Deployment Checklist

- [ ] **Backup created** - RDS snapshot taken before migration
- [ ] **Tested on staging** - Migration and rollback verified
- [ ] **Maintenance window** - Scheduled during low-traffic period
- [ ] **Monitoring ready** - CloudWatch alarms active
- [ ] **Rollback plan** - Team knows how to execute rollback.py
- [ ] **Communication** - Stakeholders notified of maintenance window
- [ ] **Post-migration tests** - Application smoke tests prepared
- [ ] **Connection from VPC** - Script runs from EC2, not public internet

## Files

- `migrate.py` - Forward migration script (v1 → v2)
- `rollback.py` - Reverse migration script (v2 → v1)
- `requirements.txt` - Python dependencies
- `README.md` - This file

## What's NOT Included

For a complete production migration system, you would also add:

- **Blue/green deployment** - Migrate copy of DB, switch over atomically
- **Application compatibility** - Code changes to use new columns
- **Monitoring integration** - DataDog/PagerDuty alerts
- **Automated testing** - Integration tests against schema v2
- **Version control** - Migrations in git with semantic versioning

## Future Enhancements

1. **Alembic integration** - Use migration framework instead of custom scripts
2. **Read replica migration** - Migrate replica first, then failover
3. **Application-driven backfill** - Lazy backfill as records are accessed
4. **Metrics export** - Send migration progress to CloudWatch
5. **Concurrent index creation** - Already implemented for production safety
