-- ═══════════════════════════════════════════════════════════
-- MERGE upsert templates (T-SQL, parameterized)
-- Target: Fabric SQL Database
-- ═══════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────
-- MERGE 1: gl_group_dim (used when create_on_save=true)
-- Idempotent: if a group_name already exists, returns its
-- existing group_id without inserting a duplicate.
--
-- The backend should:
--   1. Look up group_id by group_name (SELECT)
--   2. If found, skip this MERGE and use the existing group_id
--   3. If not found, generate a new UUID and run this MERGE
-- ───────────────────────────────────────────────────────────
MERGE cfg_master.gl_group_dim AS t
USING (SELECT @group_id AS group_id, @group_name AS group_name) AS s
ON t.group_id = s.group_id
WHEN MATCHED THEN
    UPDATE SET group_name = s.group_name
WHEN NOT MATCHED THEN
    INSERT (group_id, group_name)
    VALUES (s.group_id, s.group_name);


-- ───────────────────────────────────────────────────────────
-- MERGE 2: gl_group_mapping (main upsert)
-- Single PK on gl_code.
-- ───────────────────────────────────────────────────────────
MERGE cfg_master.gl_group_mapping AS t
USING (SELECT @gl_code AS gl_code, @group_id AS group_id) AS s
ON t.gl_code = s.gl_code
WHEN MATCHED THEN
    UPDATE SET group_id = s.group_id
WHEN NOT MATCHED THEN
    INSERT (gl_code, group_id)
    VALUES (s.gl_code, s.group_id);
