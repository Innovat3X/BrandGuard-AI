
# BrandGuard AI — Database Setup

This guide covers local PostgreSQL configuration, migrations, backend tests
and synthetic demo data.

## 1. Prerequisites

- Python 3.12
- PostgreSQL
- The project's Python virtual environment
- Access to the BrandGuard AI repository

## 2. Configure environment variables

From the repository root, create `.env` if needed:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `DATABASE_URL` to your local development database.

Example format:

```text
DATABASE_URL=postgresql+psycopg://YOUR_LOCAL_USER:YOUR_LOCAL_PASSWORD@localhost:5432/brandguard_dev
```

Replace the placeholders with your local database credentials. URL-encode
special characters in credentials where necessary.

Never commit `.env` or expose database passwords.

## 3. Install dependencies

Activate the virtual environment, then run:

```powershell
python -m pip install -r backend/requirements.txt
```

## 4. Create the development database

Ensure PostgreSQL is running and create `brandguard_dev` using an authorised
database account if it does not already exist.

Do not drop or recreate an existing database containing data you need.

## 5. Apply development database migrations

First verify that `DATABASE_URL` points to the intended development database.

Run these commands from the repository root:

```powershell
python -m alembic -c backend/alembic.ini history
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

The current migration head is `faf4dacc2b9e`. It includes the initial schema
and the normalized-user-email migration.

Review any reported schema differences before generating or applying another
migration. Schema changes must be represented by reviewed Alembic migrations.

## 6. Configure and migrate a dedicated test database

Integration tests require `TEST_DATABASE_URL` to point to a dedicated
PostgreSQL database whose name ends in `_test`.

Create the test database first using an authorised PostgreSQL account.
For example, use `brandguard_test` as the database name.

In PowerShell, configure the test connection:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://YOUR_LOCAL_USER:YOUR_LOCAL_PASSWORD@localhost:5432/brandguard_test"
```

Before running migrations, the following commands temporarily set
`DATABASE_URL` to the test database URL. This is necessary because Alembic
reads `DATABASE_URL`, not `TEST_DATABASE_URL`.

```powershell
$previousDatabaseUrl = $env:DATABASE_URL

try {
    $env:DATABASE_URL = $env:TEST_DATABASE_URL

    python -m alembic -c backend/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Test database migration failed."
    }

    python -m alembic -c backend/alembic.ini current
    if ($LASTEXITCODE -ne 0) {
        throw "Could not verify the test database revision."
    }

    python -m alembic -c backend/alembic.ini check
    if ($LASTEXITCODE -ne 0) {
        throw "Test database schema check failed."
    }
}
finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
```

After this completes successfully, run the integration tests:

```powershell
python -m pytest backend/tests -q
```

The test fixtures require `TEST_DATABASE_URL` and verify that its database
name ends in `_test`. They use transaction rollback for test isolation.

Never point `TEST_DATABASE_URL` at the development or production database.
Do not run destructive reset commands against data you need to preserve.

## 7. Load synthetic demo data

Verify that `DATABASE_URL` points to the intended local development database.

Run from the repository root:

```powershell
Push-Location backend
python -m app.infrastructure.db.seed_demo_data
Pop-Location
```

The script prompts for a demo-only password and its confirmation. Password
hashes are stored instead of plaintext passwords.

The seed creates:

- One demo organisation
- Three synthetic users and their organisation memberships
- One approved terminology rule
- One approved fact
- One sample text submission and its first version

Stable identifiers make the seed repeatable. Existing seed rows are not
overwritten.

Demo data is for local development and demonstrations only. Do not run the
seed against production or use real customer data as demo content.

## 8. Verify migration and model alignment

Run:

```powershell
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

The current migration should match the repository's migration head. When the
live schema matches registered SQLAlchemy metadata, `alembic check` should
report no new upgrade operations.

## 9. Safety rules

- Never commit `.env`, credentials, tokens or production data.
- Never edit database schemas manually; use Alembic migrations.
- Use a dedicated test database for integration tests.
- Preserve original submission versions and the approved rule/fact versions
  referenced by historical findings.
- Use synthetic records for demonstrations and automated tests.
