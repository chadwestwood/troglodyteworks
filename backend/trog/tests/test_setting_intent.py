import unittest

from twe.services.setting_intent import (
    describe_setting,
    identify_setting_query_intent,
    semantic_setting_tokens,
    setting_is_eligible,
)


class SettingIntentTests(unittest.TestCase):
    def test_splits_acronyms_and_camel_case_without_substrings(self):
        self.assertEqual(
            semantic_setting_tokens("CraftXPMultiplier"),
            frozenset({"craft", "xp", "multiplier"}),
        )
        self.assertEqual(
            semantic_setting_tokens("bCustomCosmeticLocalTabExpanded"),
            frozenset({"custom", "cosmetic", "local", "tab", "expanded"}),
        )

    def test_assigns_explicit_topics_from_exact_semantic_tokens(self):
        harvest_xp = describe_setting("HarvestXPMultiplier")
        cosmetic_tab = describe_setting("bCustomCosmeticLocalTabExpanded")

        self.assertEqual(harvest_xp.topic_tags, {"harvest", "experience"})
        self.assertEqual(cosmetic_tab.topic_tags, {"interface", "cosmetic"})
        self.assertNotIn("experience", cosmetic_tab.topic_tags)

    def test_identifies_structured_experience_intent(self):
        intent = identify_setting_query_intent(
            "<@999> What are the current XP multipliers?"
        )

        self.assertEqual(intent.topic_tags, {"experience"})
        self.assertEqual(intent.qualifier_tokens, set())
        self.assertTrue(intent.is_actionable)

    def test_topic_gate_rejects_expanded_and_accepts_real_xp_settings(self):
        intent = identify_setting_query_intent("What are the XP multipliers?")

        self.assertTrue(setting_is_eligible(intent, describe_setting("CraftXPMultiplier")))
        self.assertTrue(setting_is_eligible(intent, describe_setting("HarvestXPMultiplier")))
        self.assertFalse(
            setting_is_eligible(
                intent,
                describe_setting("bCustomCosmeticLocalTabExpanded"),
            )
        )

    def test_multiple_topics_and_qualifiers_are_required(self):
        harvest_xp = identify_setting_query_intent("harvest XP multipliers")
        craft_xp = identify_setting_query_intent("craft XP multiplier")

        self.assertTrue(
            setting_is_eligible(harvest_xp, describe_setting("HarvestXPMultiplier"))
        )
        self.assertFalse(
            setting_is_eligible(harvest_xp, describe_setting("HarvestAmountMultiplier"))
        )
        self.assertTrue(
            setting_is_eligible(craft_xp, describe_setting("CraftXPMultiplier"))
        )
        self.assertFalse(
            setting_is_eligible(craft_xp, describe_setting("BossKillXPMultiplier"))
        )

    def test_breeding_aliases_share_one_topic(self):
        intent = identify_setting_query_intent("current breeding settings")

        self.assertTrue(
            setting_is_eligible(intent, describe_setting("MatingSpeedMultiplier"))
        )
        self.assertTrue(
            setting_is_eligible(intent, describe_setting("BabyCuddleIntervalMultiplier"))
        )
        self.assertFalse(
            setting_is_eligible(intent, describe_setting("TamingSpeedMultiplier"))
        )


if __name__ == "__main__":
    unittest.main()
