-- Database initialization script for AI Marketing Platform
-- This runs automatically when PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create application user with limited privileges (for production)
-- In development, we use the main user

-- Set timezone
SET timezone = 'UTC';

-- Enum tipleri ve tablolar burada KURULMAZ: şemayı Alembic migrasyonları
-- (backend/migrations) yönetir. Burada tip oluşturmak `alembic upgrade head`
-- ile "type already exists" çakışması yaratır.

-- Log that initialization completed
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully with extensions';
END $$;
