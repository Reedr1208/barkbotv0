-- Persona V4 Migration: Add fingerprint and enrichment metadata columns
-- Safe, additive-only migration. No column deletions or type changes.
-- Rollback: These columns can be ignored; empty fingerprint = v3 behavior.

-- 1. Add persona fingerprint storage
ALTER TABLE animal_persona_profiles
  ADD COLUMN IF NOT EXISTS persona_fingerprint_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb;

-- 2. Add schema version tracking
ALTER TABLE animal_persona_profiles
  ADD COLUMN IF NOT EXISTS schema_version text NOT NULL DEFAULT 'persona_v3';

-- 3. Add enrichment model tracking (separate from archetype selection model)
ALTER TABLE animal_persona_profiles
  ADD COLUMN IF NOT EXISTS enrichment_model text;

ALTER TABLE animal_persona_profiles
  ADD COLUMN IF NOT EXISTS enrichment_params_jsonb jsonb;
