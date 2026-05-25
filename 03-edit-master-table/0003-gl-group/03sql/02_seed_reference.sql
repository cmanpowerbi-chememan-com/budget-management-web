-- ═══════════════════════════════════════════════════════════
-- 02_seed_reference.sql — gl_group_dim seed data
-- Source: docs/04gl code & gl group & gl thai name (master).xlsx
-- Seeded: 2026-05-25 — 18 groups
-- Safe to re-run (INSERT only, no duplicate if table is empty)
-- ═══════════════════════════════════════════════════════════

INSERT INTO cfg_master.gl_group_dim (group_id, group_name) VALUES
    ('6bb0620e-21f8-4b7b-a2e1-55130db8c702', 'Bank Charge'),
    ('c9937804-141f-483b-b0a5-7a134c7941d8', 'Communication Expense'),
    ('0f879748-1b5d-416d-b9ca-960a9528418d', 'Electricity & Water'),
    ('2b99c080-34dd-41b6-9061-dcfff4687270', 'Employee benefits'),
    ('0d935c42-2722-4ce9-8c0a-f2aa8e353a05', 'Entertainment'),
    ('4a2d19a5-90f1-4114-92f1-4ae2e325781d', 'Insurance Premium'),
    ('176d5f59-bf00-4f89-8d0c-80f4777a8f93', 'Lease & Rental'),
    ('dd44508c-c6d1-45b3-9861-38c6a40c9b84', 'Maintenance - License for software'),
    ('afc09935-39df-4b02-a679-b02dc2127996', 'Office expenses'),
    ('0cbdd0e4-51fb-4bde-9ca0-031891f8f685', 'Other admin. Expenses'),
    ('9c62d57c-f7bf-40b1-b032-6e49f0e0ff18', 'Other manpower exp (Per diem,Health check,Uniform…etc)'),
    ('bc4109ac-5062-47a5-a664-c5ca2606029e', 'Personal expenses'),
    ('18ed8d80-a050-4ff5-9c25-ce2da319f4b4', 'Professional & Legal Fee'),
    ('76c73dd0-aaab-493b-b0fd-13cdc8df37b0', 'Public Relation & Donation'),
    ('393b2bf7-6d68-4310-baff-dde5c480e90e', 'Remuneration of director'),
    ('704d9090-4e41-4a80-931c-db76644af1ec', 'Repair & Maintenance'),
    ('8eb7e169-4454-41eb-a47f-61217f6e81ae', 'Training & Seminar'),
    ('4df65d86-feaf-4f34-aaa6-40fe3652c1d5', 'Travelling Expense');
