from app.prompts.rules_engine import RULES_ENGINE_GENIE_INSTRUCTIONS, RULES_ENGINE_IMPLEMENTATION_PROMPT


def test_prompts_include_opportunity_silver_fields():
    assert "salesforce_silver.opportunity_silver" in RULES_ENGINE_GENIE_INSTRUCTIONS
    assert "annual_revenue" in RULES_ENGINE_GENIE_INSTRUCTIONS
    assert "salesforce_silver.opportunity_silver" in RULES_ENGINE_IMPLEMENTATION_PROMPT
    assert "snake_case" in RULES_ENGINE_IMPLEMENTATION_PROMPT
