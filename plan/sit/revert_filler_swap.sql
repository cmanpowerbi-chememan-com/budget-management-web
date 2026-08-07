-- Revert the temporary SIT filler swap on 10IT012000 (taken 2026-08-07T13:39:39)
-- Run this the moment SIT testing is done. The daily SharePoint sync (~06:30)
-- would also restore it, but do not rely on that.

UPDATE dbo.cc_filler_map SET filler_email = N'suchanyay@chememan.com'
 WHERE cost_center = N'10IT012000' AND filler_email = N'phanuwate@chememan.com';

-- verify: expect exactly 1 row, filler_email = suchanyay@chememan.com
SELECT cost_center, filler_email, department FROM dbo.cc_filler_map WHERE cost_center = N'10IT012000';
