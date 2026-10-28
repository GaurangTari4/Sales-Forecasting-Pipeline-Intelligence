-- CUSTOM stores explicitly supplied, auditable scenario assumptions.
-- Existing historical forecast runs are preserved unchanged.
ALTER TYPE scenario_code ADD VALUE IF NOT EXISTS 'CUSTOM';
