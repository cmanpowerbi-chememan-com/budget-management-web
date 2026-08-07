-- Restore script for the FY2027 test data on 10IT012000
-- Snapshot taken before the SIT wave-0 delete. Run top to bottom to undo.

-- budget.pending_budget_detail: 2 row(s)
SET IDENTITY_INSERT budget.pending_budget_detail ON;
INSERT INTO budget.pending_budget_detail ([detail_id], [cost_center], [gl_account], [fiscal_year], [trip_id], [gl_group], [line_label], [m01], [m02], [m03], [m04], [m05], [m06], [m07], [m08], [m09], [m10], [m11], [m12], [total_year], [meta_json], [is_auto_calc], [_user], [_updated_at]) VALUES (166, N'10IT012000', N'6210400010', 2027, 30, N'Travelling Expense', N'เบี้ยเลี้ยง · Per Diem', 2640.00, 2640.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 5280.00, NULL, True, N'jakkaritw@chememan.com', '2026-08-05 09:12:50.347061');
INSERT INTO budget.pending_budget_detail ([detail_id], [cost_center], [gl_account], [fiscal_year], [trip_id], [gl_group], [line_label], [m01], [m02], [m03], [m04], [m05], [m06], [m07], [m08], [m09], [m10], [m11], [m12], [total_year], [meta_json], [is_auto_calc], [_user], [_updated_at]) VALUES (167, N'10IT012000', N'6210400010', 2027, 31, N'Travelling Expense', N'เบี้ยเลี้ยง · Per Diem', 0.00, 0.00, 0.00, 4620.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 4620.00, NULL, True, N'jakkaritw@chememan.com', '2026-08-05 09:20:06.272180');
SET IDENTITY_INSERT budget.pending_budget_detail OFF;

-- budget.budget_trip: 2 row(s)
SET IDENTITY_INSERT budget.budget_trip ON;
INSERT INTO budget.budget_trip ([trip_id], [cost_center], [fiscal_year], [traveler_empcode], [traveler_name], [position], [destination], [country_group], [days], [travel_months], [purpose], [side], [_user], [_updated_at], [client_token], [project]) VALUES (30, N'10IT012000', 2027, N'101159', N'สุชัญญา ยุปา', N'Assistant Department Head (MGR)', N'South Africa', 2, 2, N'01,02', NULL, N'SGA', N'jakkaritw@chememan.com', '2026-08-05 09:12:50.347061', N'd50f53d9-c938-461c-891c-05d2c0622f05', NULL);
INSERT INTO budget.budget_trip ([trip_id], [cost_center], [fiscal_year], [traveler_empcode], [traveler_name], [position], [destination], [country_group], [days], [travel_months], [purpose], [side], [_user], [_updated_at], [client_token], [project]) VALUES (31, N'10IT012000', 2027, N'100925', N'เจณภพ สุริยะวงศ์', N'Senior Supervisor 2', N'China', 2, 2, N'04', NULL, N'SGA', N'jakkaritw@chememan.com', '2026-08-05 09:20:06.272180', N'52e5ba98-2f82-4cb3-9d07-4cb9da7c16f9', N'');
SET IDENTITY_INSERT budget.budget_trip OFF;

-- budget.pending_budget: 1 row(s)
SET IDENTITY_INSERT budget.pending_budget ON;
INSERT INTO budget.pending_budget ([cost_center], [gl_account], [fiscal_year], [m01], [m02], [m03], [m04], [m05], [m06], [m07], [m08], [m09], [m10], [m11], [m12], [total_year], [template], [remark], [gl_name], [gl_group], [c_level], [division], [department], [_user], [_updated_at]) VALUES (N'10IT012000', N'6210400010', 2027, 2640.00, 2640.00, 0.00, 4620.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 9900.00, N'USER', NULL, N'เบี้ยเลี้ยง', N'Travelling Expense', N'Chief Technology Officer', N'Digital Technology', N'Solution Delivery', N'jakkaritw@chememan.com', '2026-08-05 09:20:06.272180');
SET IDENTITY_INSERT budget.pending_budget OFF;
