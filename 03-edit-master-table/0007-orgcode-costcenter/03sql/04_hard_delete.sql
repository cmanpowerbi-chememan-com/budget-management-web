-- ═══════════════════════════════════════════════════════════
-- Hard DELETE template (parameterized)
-- Locked decision #22: hard delete + simple confirm modal
--
-- ⚠️  WHERE clause MUST include both PK columns.
-- Using only cost_center would delete ALL mappings of that
-- Cost Center to every Orgcode — data loss bug.
-- ═══════════════════════════════════════════════════════════

DELETE FROM cfg_master.orgcode_costcenter
WHERE cost_center = :cost_center
  AND orgcode     = :orgcode;
