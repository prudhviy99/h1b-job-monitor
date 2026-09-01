import json
import unittest
from pathlib import Path

from scripts.build_company_config import USER_EXCLUDED_COMPANIES, apply_user_exclusions


ROOT = Path(__file__).resolve().parents[1]


class ProfileContractTests(unittest.TestCase):
    def test_amazon_is_disabled_and_exclusion_survives_regeneration(self):
        payload = json.loads((ROOT / "config/companies.json").read_text())
        companies = payload["companies"]
        amazon = next(company for company in companies if company["id"] == "amazon")
        self.assertFalse(amazon["enabled"])
        self.assertEqual(amazon["monitor_status"], "disabled-by-user")
        self.assertEqual(amazon["connector"]["access_policy"], "disabled")
        self.assertIn("Amazon", USER_EXCLUDED_COMPANIES)
        self.assertEqual(sum(bool(company["enabled"]) for company in companies), 62)

        regenerated = [{"name": "Amazon", "enabled": True, "monitor_status": "enabled",
                        "connector": {"access_policy": "strict"}, "notes": "researched"}]
        apply_user_exclusions(regenerated)
        self.assertFalse(regenerated[0]["enabled"])
        self.assertEqual(regenerated[0]["monitor_status"], "disabled-by-user")
        self.assertEqual(regenerated[0]["connector"]["access_policy"], "disabled")

    def test_updated_resume_experience_ceiling_is_four_years(self):
        profile = json.loads((ROOT / "config/profile.json").read_text())
        self.assertEqual(profile["candidate"]["profile_revision"], "2026-08-31-master-resume-v2")
        self.assertEqual(profile["candidate"]["years_of_relevant_us_experience"], 3.75)
        self.assertEqual(profile["filters"]["max_required_years"], 4)
        self.assertEqual(profile["filters"]["senior_max_required_years"], 4)


if __name__ == "__main__":
    unittest.main()
