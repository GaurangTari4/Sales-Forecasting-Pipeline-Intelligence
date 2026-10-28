-- Remove only the legacy uniqueness rule across this exact configuration tuple.
-- A run ID remains the primary key, preserving immutable historical run records.
DO $$
DECLARE constraint_name text;
BEGIN
  SELECT constraint_row.conname INTO constraint_name
  FROM pg_constraint AS constraint_row
  WHERE constraint_row.conrelid = 'forecast_runs'::regclass
    AND constraint_row.contype = 'u'
    AND constraint_row.conkey = ARRAY[
      (SELECT attnum FROM pg_attribute WHERE attrelid = 'forecast_runs'::regclass AND attname = 'forecast_snapshot_id'),
      (SELECT attnum FROM pg_attribute WHERE attrelid = 'forecast_runs'::regclass AND attname = 'model_version'),
      (SELECT attnum FROM pg_attribute WHERE attrelid = 'forecast_runs'::regclass AND attname = 'feature_version'),
      (SELECT attnum FROM pg_attribute WHERE attrelid = 'forecast_runs'::regclass AND attname = 'scenario'),
      (SELECT attnum FROM pg_attribute WHERE attrelid = 'forecast_runs'::regclass AND attname = 'stage_probability_version_name')
    ]::smallint[];
  IF constraint_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE forecast_runs DROP CONSTRAINT %I', constraint_name);
  END IF;
END $$;
