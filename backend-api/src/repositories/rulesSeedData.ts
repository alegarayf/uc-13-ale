/** Shared AI rule seed used by in-memory repository and SQL seed script. */
export const SEED_AI_EMPLOYEE_HEADCOUNT = {
  name: "employee_headcount_investment_range",
  description:
    "Evaluates whether an opportunity's employee_head_count is within the target range of 50 to 350, inclusive, for investment consideration. Ignores annual_revenue as a size proxy.",
  status: "active" as const,
  rule_source: "ai" as const,
  nl_prompt:
    "Rallyday uses employee headcount as the primary proxy for company size, given that revenue data from third-party sources is considered unreliable. A company's total employee count should fall within the target range of 50 to 350 employees to be considered appropriately sized for investment consideration.",
  nl_summary:
    "The rule interprets company size based on employee_head_count, disregarding annual_revenue due to its unreliability. An opportunity is considered appropriately sized for investment if employee_head_count is between 50 and 350, inclusive.",
  rule_definition: JSON.stringify({
    name: "employee_headcount_investment_range",
    description:
      "Evaluates whether an opportunity's employee_head_count is within the target range of 50 to 350, inclusive, for investment consideration. Ignores annual_revenue as a size proxy.",
    intent: "evaluate_opportunity",
    conditions: [
      { field: "employee_head_count", operator: ">=", value: 50 },
      { field: "employee_head_count", operator: "<=", value: 350 },
    ],
    actions: [{ type: "flag", target: "opportunity", params: {} }],
    metadata: {},
    python_function: {
      language: "python",
      version: "3.11",
      entrypoint: "evaluate_employee_headcount_investment_range",
      source:
        "def evaluate_employee_headcount_investment_range(opportunity):\n    headcount = opportunity.get('employee_head_count')\n    if headcount is None:\n        return {'passed': False, 'reason': 'employee_head_count is missing', 'rule': 'employee_headcount_investment_range'}\n    if 50 <= headcount <= 350:\n        return {'passed': True, 'reason': 'employee_head_count is within the target range', 'rule': 'employee_headcount_investment_range'}\n    return {'passed': False, 'reason': f'employee_head_count ({headcount}) is outside the target range (50-350)', 'rule': 'employee_headcount_investment_range'}",
    },
  }),
  python_source:
    "def evaluate_employee_headcount_investment_range(opportunity):\n    headcount = opportunity.get('employee_head_count')\n    if headcount is None:\n        return {'passed': False, 'reason': 'employee_head_count is missing', 'rule': 'employee_headcount_investment_range'}\n    if 50 <= headcount <= 350:\n        return {'passed': True, 'reason': 'employee_head_count is within the target range', 'rule': 'employee_headcount_investment_range'}\n    return {'passed': False, 'reason': f'employee_head_count ({headcount}) is outside the target range (50-350)', 'rule': 'employee_headcount_investment_range'}",
  python_entrypoint: "evaluate_employee_headcount_investment_range",
  last_updated_by: "seed",
};
