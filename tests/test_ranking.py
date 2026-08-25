import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from h1b_job_monitor.models import Company, Job, SponsorshipEvidence
from h1b_job_monitor.ranking import Ranker, extract_years, sponsorship_signal


ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "config/profile.json").read_text())


def company(score=0.82):
    return Company(
        id="example",
        name="Example",
        domain="example.com",
        careers_url="https://example.com/jobs",
        enabled=True,
        connector={"type": "greenhouse", "default_country": "US"},
        sponsorship=SponsorshipEvidence(
            confidence="high", score=score, summary="FY2026 certified LCAs", sources=["https://dol.gov"]
        ),
        fit_tags=["backend", "distributed-systems", "security", "platform"],
    )


def job(title="Senior Software Engineer, Backend Platform", location="Seattle, WA", description=None):
    return Job(
        company_id="example",
        company="Example",
        source="greenhouse",
        source_job_id="1",
        title=title,
        location=location,
        description=description or (
            "Build Java Spring Boot distributed systems on AWS using Kafka, DynamoDB, Kubernetes, "
            "Prometheus and security controls. Requires 4+ years of software engineering experience."
        ),
        source_url="https://example.com/jobs/1",
        posted_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        posting_date_confidence="high",
    )


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.ranker = Ranker(PROFILE)
        self.now = datetime(2026, 8, 25, tzinfo=timezone.utc)

    def test_selective_senior_is_accepted(self):
        decision = self.ranker.evaluate(job(), company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertIn(decision.priority, {"P0", "P1"})

    def test_senior_without_years_rejected(self):
        value = job(description="Build Java distributed services on AWS.")
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertFalse(decision.accepted)
        self.assertTrue(any("Senior title" in x for x in decision.rejection_reasons))

    def test_staff_and_intern_rejected(self):
        self.assertFalse(self.ranker.evaluate(job(title="Staff Software Engineer"), company(), self.now).accepted)
        self.assertFalse(self.ranker.evaluate(job(title="Lead Software Engineer"), company(), self.now).accepted)
        self.assertFalse(self.ranker.evaluate(job(title="Software Engineer Intern"), company(), self.now).accepted)
        self.assertFalse(self.ranker.evaluate(job(title="Cloud DevOps Team Leader"), company(), self.now).accepted)

    def test_explicitly_junior_titles_are_rejected(self):
        for title in (
            "Junior Software Engineer",
            "Associate Software Engineer",
            "Software Engineer, Level I",
            "Software Engineer, Level IV",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_explicit_zero_to_two_year_range_is_rejected(self):
        value = job(
            title="Software Engineer",
            description=(
                "Build Java Spring AWS Kafka distributed backend systems with security and Kubernetes. "
                "Requires 0-2 years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

    def test_one_year_generic_role_is_rejected(self):
        value = job(
            title="Software Engineer",
            description=(
                "Build Java Spring AWS Kafka distributed backend systems with security and Kubernetes. "
                "Requires 1+ years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

    def test_irrelevant_ml_testing_and_federal_rejected(self):
        for title in (
            "Senior Machine Learning Engineer",
            "Software Development Engineer, Vehicle Testing",
            "Software Engineer, Federal Platform",
            "Technical Escalations Engineer 2",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_real_world_irrelevant_and_clearance_titles_rejected(self):
        for title in (
            "Data Engineer, Monetization Data Platform",
            "Software Integration Support Engineer",
            "Senior Software Engineer, Core UI",
            "Electrical Engineer, Actuator Test Infrastructure",
            "Quantum Systems Software Development Engineer II",
            "Sr. Software Consultant-CTJ-Top Secret/SCI",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_explicit_no_sponsorship_wins(self):
        value = job(description=job().description + " Candidates must work without current or future sponsorship.")
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.sponsorship_signal, "explicit_no_sponsorship")

    def test_employment_authorization_no_sponsorship_wins(self):
        text = "Capital One will not sponsor a new applicant for employment authorization for this position."
        self.assertEqual(sponsorship_signal(text), "explicit_no_sponsorship")

    def test_common_negative_sponsorship_phrasings(self):
        for text in (
            "This position is not eligible for employment-based sponsorship.",
            "Candidates requiring visa sponsorship will not be considered.",
            "Visa sponsorship is not provided.",
            "We cannot sponsor employment authorization.",
            "Sponsorship is unavailable.",
            "No sponsorship is available for this role.",
            "This role is ineligible for visa sponsorship.",
            "The company may not be able to employ some visa categories or support future H-1B sponsorship at this time.",
        ):
            with self.subTest(text=text):
                self.assertEqual(sponsorship_signal(text), "explicit_no_sponsorship")

    def test_non_us_rejected(self):
        decision = self.ranker.evaluate(job(location="Toronto, Canada"), company(), self.now)
        self.assertFalse(decision.accepted)
        self.assertIn("non-US location", decision.rejection_reasons)

    def test_ambiguous_country_abbreviations_are_not_us_states(self):
        for location in (
            "Toronto, CA",
            "Panamá, Provincia de Panamá, PA",
            "Karnataka, Karnātaka, IN",
        ):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertIn("non-US location", decision.rejection_reasons)

    def test_structured_country_overrides_ambiguous_state_code(self):
        value = job(location="Karnataka, IN")
        value.raw = {
            "jobLocation": {
                "address": {"addressRegion": "Karnataka", "addressCountry": "IN"}
            }
        }
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertIn("non-US location", decision.rejection_reasons)

    def test_mixed_location_with_a_real_us_option_is_allowed(self):
        decision = self.ranker.evaluate(
            job(location="Toronto, Canada | New York, US"), company(), self.now
        )
        self.assertNotIn("non-US location", decision.rejection_reasons)

    def test_lowercase_or_is_not_oregon(self):
        decision = self.ranker.evaluate(job(location="Location TBD or negotiable"), company(), self.now)
        self.assertIn("US eligibility could not be verified from location", decision.rejection_reasons)

    def test_location_requirement_is_configurable(self):
        profile = copy.deepcopy(PROFILE)
        profile["filters"]["require_us_location"] = False
        decision = Ranker(profile).evaluate(job(location="Toronto, Canada"), company(), self.now)
        self.assertNotIn("non-US location", decision.rejection_reasons)

    def test_target_title_pattern_is_configurable(self):
        profile = copy.deepcopy(PROFILE)
        profile["matching"]["target_title_regex"] = r"\bwidget engineer\b"
        decision = Ranker(profile).evaluate(job(), company(), self.now)
        self.assertIn("title lacks a target engineering discipline", decision.rejection_reasons)

    def test_year_extraction_ignores_preferred_when_required_exists(self):
        text = "Requires 3+ years of experience. Preferred: 8+ years of Java."
        self.assertEqual(extract_years(text)[0], 3.0)

    def test_year_range_is_not_double_counted(self):
        self.assertEqual(extract_years("Requires 3-5 years of experience."), (3.0, 5.0))

    def test_company_age_and_benefit_years_are_not_experience(self):
        for text in (
            "For over 10 years, we have built cloud software. Requires 3+ years of experience.",
            "Founded 8 years ago, we build systems. Requires 3+ years backend experience.",
            "Benefits vest after 7 years of service. Requires 3+ years of engineering experience.",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_years(text)[0], 3.0)

    def test_export_control_and_clearance_phrases_rejected(self):
        for restriction in (
            "U.S. Person required.",
            "Applicants must be U.S. persons due to export controls.",
            "Must possess a Secret clearance.",
            "US Citizen or Green Card holder only.",
            "This role requires ITAR eligibility.",
            "To comply with U.S. export control laws, candidates may need to meet certain legal status requirements.",
        ):
            value = job(description=job().description + " " + restriction)
            with self.subTest(restriction=restriction):
                self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

    def test_suffix_preferred_is_not_required(self):
        text = "Requires 3+ years of experience. 8+ years preferred."
        self.assertEqual(extract_years(text)[0], 3.0)

    def test_positive_sponsorship(self):
        self.assertEqual(sponsorship_signal("H-1B transfer sponsorship is available."), "explicit_sponsorship_available")
        self.assertEqual(sponsorship_signal("We do sponsor visas!"), "explicit_sponsorship_available")


if __name__ == "__main__":
    unittest.main()
