-- ═══════════════════════════════════════════════════════════
-- Hard DELETE template (T-SQL, parameterized)
-- Locked decision #22: hard delete + simple confirm modal
-- Recovery via Fabric SQL Database point-in-time restore.
-- ═══════════════════════════════════════════════════════════

DELETE FROM cfg_master.gl_group_mapping
WHERE gl_code = @gl_code;

-- ───────────────────────────────────────────────────────────
-- NOTE on dimension cleanup
-- ───────────────────────────────────────────────────────────
-- Deleting a mapping row does NOT delete its referenced
-- gl_group_dim row, because other mappings may still use it.
--
-- Orphan dim rows (groups with zero mappings) can be cleaned
-- by a separate maintenance job. Do NOT cascade delete here.
