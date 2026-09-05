import json
import unittest
from pathlib import Path

from scripts.build_company_config import USER_EXCLUDED_COMPANIES, apply_user_exclusions
from h1b_job_monitor.ranking import Ranker
from test_monitor import make_job, make_company


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
        self.assertGreaterEqual(sum(bool(company["enabled"]) for company in companies), 62)

        regenerated = [{"name": "Amazon", "enabled": True, "monitor_status": "enabled",
                        "connector": {"access_policy": "strict"}, "notes": "researched"}]
        apply_user_exclusions(regenerated)
        self.assertFalse(regenerated[0]["enabled"])
        self.assertEqual(regenerated[0]["monitor_status"], "disabled-by-user")
        self.assertEqual(regenerated[0]["connector"]["access_policy"], "disabled")

    def test_updated_resume_experience_ceiling_is_four_years(self):
        profile = json.loads((ROOT / "config/profile.json").read_text())
        self.assertEqual(profile["candidate"]["profile_source_sha256"], "719c81d73d30fe4a12f4492a4e62d494b3ddfcadd93fc357d69294012525e98a")
        self.assertEqual(profile["candidate"]["years_of_relevant_us_experience"], 3.75)
        self.assertEqual(profile["filters"]["max_required_years"], 4)
        self.assertEqual(profile["filters"]["senior_max_required_years"], 4)

    def test_hardware_in_loop_platform_is_not_backend_platform_match(self):
        profile = json.loads((ROOT / "config/profile.json").read_text())
        job = make_job(None)
        job.title = "Software Engineer, AV HIL Platform"
        self.assertFalse(Ranker(profile).evaluate(job, make_company()).accepted)


if __name__ == "__main__":
    unittest.main()
