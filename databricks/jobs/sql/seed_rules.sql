-- Optional seed data for rallyday_partners_llc.garden.rules (adjust catalog/schema as needed).
-- Run after create_rules_table.sql when the table is empty.

INSERT INTO rallyday_partners_llc.garden.rules
  (name, description, comparison, minimum, maximum, uom, status, created_at, updated_at, last_updated_by)
VALUES
  (
    'Revenue threshold',
    'Minimum annual revenue for portfolio consideration.',
    '>=', 10000000, NULL, 'USD', 'active', current_timestamp(), current_timestamp(), 'seed'
  ),
  (
    'Geography',
    'Primary operating region for eligible companies.',
    '=', NULL, NULL, NULL, 'active', current_timestamp(), current_timestamp(), 'seed'
  ),
  (
    'Growth mindset score',
    'Minimum qualitative score from partner review.',
    '>=', 7, 10, 'score', 'inactive', current_timestamp(), current_timestamp(), 'seed'
  );
