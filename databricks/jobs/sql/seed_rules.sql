-- Optional seed data for rallyday_partners_llc.garden.rules (adjust catalog/schema as needed).
-- Run after create_rules_table.sql when the table is empty.

INSERT INTO rallyday_partners_llc.garden.rules
  (name, description, status, rule_source, nl_prompt, nl_summary, rule_definition, python_source, python_entrypoint, created_at, updated_at, last_updated_by)
VALUES
  (
    'employee_headcount_investment_range',
    'Evaluates whether an opportunity''s employee_head_count is within the target range of 50 to 350, inclusive, for investment consideration. Ignores annual_revenue as a size proxy.',
    'active',
    'ai',
    'Rallyday uses employee headcount as the primary proxy for company size, given that revenue data from third-party sources is considered unreliable. A company''s total employee count should fall within the target range of 50 to 350 employees to be considered appropriately sized for investment consideration.',
    'The rule interprets company size based on employee_head_count, disregarding annual_revenue due to its unreliability. An opportunity is considered appropriately sized for investment if employee_head_count is between 50 and 350, inclusive.',
    '{"name":"employee_headcount_investment_range","description":"Evaluates whether an opportunity''s employee_head_count is within the target range of 50 to 350, inclusive, for investment consideration. Ignores annual_revenue as a size proxy.","intent":"evaluate_opportunity","conditions":[{"field":"employee_head_count","operator":">=","value":50},{"field":"employee_head_count","operator":"<=","value":350}],"actions":[{"type":"flag","target":"opportunity","params":{}}],"metadata":{},"python_function":{"language":"python","version":"3.11","entrypoint":"evaluate_employee_headcount_investment_range","source":"def evaluate_employee_headcount_investment_range(opportunity):\\n    headcount = opportunity.get(''employee_head_count'')\\n    if headcount is None:\\n        return {''passed'': False, ''reason'': ''employee_head_count is missing'', ''rule'': ''employee_headcount_investment_range''}\\n    if 50 <= headcount <= 350:\\n        return {''passed'': True, ''reason'': ''employee_head_count is within the target range'', ''rule'': ''employee_headcount_investment_range''}\\n    return {''passed'': False, ''reason'': f''employee_head_count ({headcount}) is outside the target range (50-350)'', ''rule'': ''employee_headcount_investment_range''}"}}',
    'def evaluate_employee_headcount_investment_range(opportunity):\n    headcount = opportunity.get(''employee_head_count'')\n    if headcount is None:\n        return {''passed'': False, ''reason'': ''employee_head_count is missing'', ''rule'': ''employee_headcount_investment_range''}\n    if 50 <= headcount <= 350:\n        return {''passed'': True, ''reason'': ''employee_head_count is within the target range'', ''rule'': ''employee_headcount_investment_range''}\n    return {''passed'': False, ''reason'': f''employee_head_count ({headcount}) is outside the target range (50-350)'', ''rule'': ''employee_headcount_investment_range''}',
    'evaluate_employee_headcount_investment_range',
    current_timestamp(),
    current_timestamp(),
    'seed'
  ),
  (
    'Geography',
    'Primary operating region for eligible companies.',
    'active',
    'form',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    current_timestamp(),
    current_timestamp(),
    'seed'
  ),
  (
    'Growth mindset score',
    'Minimum qualitative score from partner review.',
    'inactive',
    'form',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    current_timestamp(),
    current_timestamp(),
    'seed'
  );
