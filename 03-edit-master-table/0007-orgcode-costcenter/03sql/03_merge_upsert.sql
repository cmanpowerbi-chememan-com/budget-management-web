-- ═══════════════════════════════════════════════════════════
-- MERGE upsert template (parameterized)
-- ═══════════════════════════════════════════════════════════
-- Junction table with composite PK on (cost_center, orgcode).
-- 
-- Both PK columns appear in ON clause to prevent
-- DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE
-- when multiple Cost Centers share the same Orgcode (or vice versa).
--
-- Source is deduplicated with SELECT DISTINCT to guard against
-- duplicate rows in the same batch.
--
-- No WHEN MATCHED clause: this is a pure relationship table,
-- there are no non-PK columns to update.  If the pair already
-- exists, the MERGE is a no-op.
-- ═══════════════════════════════════════════════════════════

MERGE INTO cfg_master.orgcode_costcenter t
USING (
    SELECT DISTINCT
        :cost_center AS cost_center,
        :orgcode     AS orgcode
) s
ON  t.cost_center = s.cost_center
AND t.orgcode     = s.orgcode
WHEN NOT MATCHED THEN INSERT (cost_center, orgcode)
VALUES (s.cost_center, s.orgcode);
