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

    def test_generic_titles_do_not_hide_unverified_required_specialties(self):
        for text in (
            'Own full-stack features end-to-end.',
            '3+ years of full stack software engineering experience.',
            'Shipped an LLM-powered feature to real users.',
            'Experience with MCP, agent frameworks, or tool-calling architectures in production.',
            '2 years of experience employing advanced AI toolsets to accelerate development.',
            'Strong hands‑on experience with containers and Kubernetes in production environments.',
            'Design, implement, test feature and OS improvements in the latest Windows OS.',
            '2+ years shipping A/B tests end-to-end in production.',
        ):
            with self.subTest(text=text):
                d = self.ranker.evaluate(job(title='Software Engineer', description='Build Java backend services on AWS. Requires 3+ years of experience. '+text), company(), self.now)
                self.assertFalse(d.accepted, text)
        for optional in ('Preferred Qualifications', 'Preferred Qualifications:'):
            text = 'Build Java backend services on AWS. Minimum qualifications: 3+ years of experience. '+optional+' Experience with MCP in production.'
            self.assertTrue(self.ranker.evaluate(job(description=text), company(), self.now).accepted)

    def test_escaped_required_years_and_language_or_do_not_lower_degree_floor(self):
        d = self.ranker.evaluate(job(description='Build Java distributed services on AWS. &lt;p&gt;Requires &lt;b&gt;5+ years&lt;/b&gt; of software engineering experience.&lt;/p&gt;'), company(), self.now)
        self.assertFalse(d.accepted)
        self.assertEqual(d.min_years, 5)
        text = "Master's Degree in Computer Science AND 6+ years technical engineering experience with coding in Java, JavaScript, or Python OR equivalent experience."
        self.assertEqual(extract_years(text)[0], 6)

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
        for title in (
            "Software Engineering Mgr, Backend Platform",
            "Software Engineering Supervisor, Backend Platform",
            "Software Engineering Leader, Backend Platform",
            "Software Engineering Group Leader",
            "Technical Leader, Software Engineering",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

        metadata_intern = job(title="Software Engineer, Backend Platform")
        metadata_intern.employment_type = "Internship"
        self.assertFalse(self.ranker.evaluate(metadata_intern, company(), self.now).accepted)
        for department in ("University Recruiting", "Campus Programs", "Early Careers"):
            with self.subTest(department=department):
                metadata_new_grad = job(title="Software Engineer, Backend Platform")
                metadata_new_grad.department = department
                self.assertFalse(
                    self.ranker.evaluate(metadata_new_grad, company(), self.now).accepted
                )
        metadata_entry_level = job(title="Software Engineer, Backend Platform")
        metadata_entry_level.employment_type = "Entry Level"
        self.assertFalse(self.ranker.evaluate(metadata_entry_level, company(), self.now).accepted)

        for department in ("Associate Experience", "Associate Technology"):
            with self.subTest(department=department):
                legitimate_associate = job(title="Software Engineer, Backend Platform")
                legitimate_associate.department = department
                self.assertTrue(
                    self.ranker.evaluate(legitimate_associate, company(), self.now).accepted
                )

    def test_full_stack_sdet_and_nonsoftware_security_titles_are_rejected(self):
        for title in (
            "Full Stack Software Engineer",
            "Software Development Engineer in Test",
            "Software Quality Engineer",
            "Security Engineer, GRC Compliance",
            "Security Engineer, Red Team",
            "Client Platform Security Engineer",
            "Security Engineer, Corporate Security",
            "Security Engineer, Privacy",
            "Security Engineer, Incident Response",
            "AI Systems Engineer, Codex Agents",
            "Applied AI Software Engineer, Growth",
            "Product Engineer, Enterprise AI Platform",
            "Software Developer, Physical & Edge AI Platforms",
            "Software Development Engineer, Ads Console Frameworks",
            "Platform Security Engineer, DRTM / Secure Launch",
            "AI DevOps Engineer",
            "Customer Reliability Engineer",
            "Robotics Software Engineer",
            "Solutions Engineer, Cloud Platform",
            "Cloud Infrastructure Consultant",
            "Platform Specialist",
            "Software Recruiter",
            "Software Engineer, Test Platform",
            "Software Engineer, Test Infrastructure",
            "Software Engineer, Build & Test Systems",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_explicitly_junior_titles_are_rejected(self):
        for title in (
            "Junior Software Engineer",
            "Associate Software Engineer",
            "Software Engineer, Level I",
            "Software Engineer, Level IV",
            "Software Developer I",
            "Systems Development Engineer I",
            "Cloud Engineer I",
            "DevOps Engineer I",
            "API Developer I",
            "Observability Engineer I",
            "Telemetry Engineer I",
            "AMTS Software Engineer",
            "SRE I",
            "SRE 1",
            "MTS I",
            "Graduate Software Engineer",
            "Recent Graduate Software Engineer",
            "New College Grad - Software Engineer",
            "Software Engineer Trainee",
            "Software Engineer, Early Talent",
            "Software Engineer, Emerging Talent",
            "Software Engineer, Entry Talent",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_updated_target_title_levels_are_handled_conservatively(self):
        self.assertFalse(
            self.ranker.evaluate(job(title="Backend Engineer I"), company(), self.now).accepted
        )

        engineer_three = self.ranker.evaluate(
            job(
                title="Platform Engineer III",
                description=(
                    "Build Java distributed platform systems on AWS with DynamoDB. "
                    "Requires 4+ years of experience."
                ),
            ),
            company(),
            self.now,
        )
        self.assertTrue(engineer_three.accepted, engineer_three.rejection_reasons)

        self.assertFalse(
            self.ranker.evaluate(
                job(title="Member of Technical Staff", description="Build Java AWS services."),
                company(),
                self.now,
            ).accepted
        )
        mts = self.ranker.evaluate(
            job(
                title="Member of Technical Staff",
                description=(
                    "Build Java backend distributed systems on AWS with DynamoDB. "
                    "Requires 4+ years of experience."
                ),
            ),
            company(),
            self.now,
        )
        self.assertTrue(mts.accepted, mts.rejection_reasons)

        for title in (
            "Principal Member of Technical Staff",
            "Lead MTS",
            "Staff Member of Technical Staff",
        ):
            with self.subTest(title=title):
                self.assertFalse(
                    self.ranker.evaluate(
                        job(title=title, description=job().description),
                        company(),
                        self.now,
                    ).accepted
                )

        for title in ("Software Engineer V", "Backend Engineer 5"):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

        for title in (
            "Software Engineer VI",
            "Software Engineer 6",
            "Software Developer IV",
            "Cloud Engineer IV",
            "API Developer IV",
            "PMTS Software Engineer",
            "DMTS Software Engineer",
            "LMTS Software Engineer",
            "Engineer VI, Backend Platform",
            "Software Engineer L6",
            "Platform Engineer IC6",
            "SWE E6",
            "SRE IV",
            "SRE 4",
            "SRE VI",
            "SRE 6",
            "MTS IV",
            "Member of Technical Staff IV",
            "Master Software Engineer",
            "Advisory Software Engineer",
            "Expert Software Engineer",
            "Software Engineer, Expert",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

        for title in (
            "Java Engineer III",
            "Python Engineer III",
            "Software Developer III",
            "Systems Development Engineer III",
            "Cloud Engineer III",
            "DevOps Engineer III",
            "SRE III",
            "SRE 3",
            "SMTS Software Engineer",
        ):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(
                    job(title=title, description="Build Java distributed services on AWS."),
                    company(),
                    self.now,
                )
                self.assertFalse(decision.accepted)
                self.assertTrue(
                    any("Senior title" in reason for reason in decision.rejection_reasons)
                )

        for title in (
            "Software Engineer, I/O Systems",
            "Platform Engineer - I/O Infrastructure",
            "Systems Engineer I/O Platform",
        ):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(job(title=title), company(), self.now)
                self.assertNotIn("level-I/junior role", decision.rejection_reasons)

    def test_bank_associate_ladders_are_selective_senior_not_entry_or_principal(self):
        for title in (
            "Senior Associate, Software Engineer",
            "Senior Associate Software Engineer, Backend Platform",
            "Principal Associate, Software Engineer, Back End",
        ):
            with self.subTest(title=title):
                value = job(
                    title=title,
                    description=(
                        "Build Java Spring backend distributed systems on AWS with DynamoDB. "
                        "Requires 4+ years of software engineering experience."
                    ),
                )
                decision = self.ranker.evaluate(value, company(), self.now)
                self.assertTrue(decision.accepted, decision.rejection_reasons)

        too_deep = job(
            title="Principal Associate, Software Engineer, Back End",
            description=(
                "Build Java backend distributed systems on AWS. "
                "Requires 6+ years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(too_deep, company(), self.now).accepted)

    def test_specialist_suffix_does_not_override_a_software_engineer_anchor(self):
        for title in (
            "Backend Software Engineer, Specialist",
            "Specialist Software Engineer II",
        ):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(job(title=title), company(), self.now)
                self.assertTrue(decision.accepted, decision.rejection_reasons)

        systems_development = self.ranker.evaluate(
            job(
                title="Systems Development Engineer II",
                description=(
                    "Build Java distributed systems and automation on AWS with DynamoDB. "
                    "Requires 3+ years of experience."
                ),
            ),
            company(),
            self.now,
        )
        self.assertTrue(systems_development.accepted, systems_development.rejection_reasons)

    def test_explicit_zero_to_two_year_range_is_rejected(self):
        value = job(
            title="Software Engineer",
            description=(
                "Build Java Spring AWS Kafka distributed backend systems with security and Kubernetes. "
                "Requires 0-2 years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

        explicit_mid = job(
            title="Software Engineer II, Backend Platform",
            description=(
                "Build Java Spring AWS distributed backend systems with security. "
                "Requires 0-2 years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(explicit_mid, company(), self.now).accepted)

    def test_one_year_generic_role_is_rejected(self):
        value = job(
            title="Software Engineer",
            description=(
                "Build Java Spring AWS Kafka distributed backend systems with security and Kubernetes. "
                "Requires 1+ years of software engineering experience."
            ),
        )
        self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

    def test_early_career_band_and_five_year_floor_are_rejected(self):
        early = job(
            title="Software Engineer, Data Platform",
            description=(
                "Build Java backend distributed systems on AWS with DynamoDB. "
                "Requires 1-3 years of experience."
            ),
        )
        early_decision = self.ranker.evaluate(early, company(), self.now)
        self.assertFalse(early_decision.accepted)
        self.assertIn("experience range is an early-career band (1-3 years)", early_decision.rejection_reasons)

        stretch = job(
            title="Software Development Engineer, Kinesis Streams",
            description=(
                "Build Java distributed stream processing systems on AWS Kinesis with DynamoDB. "
                "Requires 5+ years of experience."
            ),
        )
        stretch_decision = self.ranker.evaluate(stretch, company(), self.now)
        self.assertFalse(stretch_decision.accepted)
        self.assertIn("requires about 5+ years", stretch_decision.rejection_reasons)

        two_year = job(
            title="Software Engineer II, Backend Platform",
            description=(
                "Build Java Spring Boot distributed systems on AWS with DynamoDB. "
                "Requires 2+ years of experience."
            ),
        )
        self.assertEqual(
            self.ranker.evaluate(two_year, company(), self.now).priority,
            "P2",
        )

        unknown_years = job(
            title="Software Engineer II, Backend Platform",
            description="Build Java Spring Boot distributed systems on AWS with DynamoDB.",
        )
        self.assertEqual(
            self.ranker.evaluate(unknown_years, company(), self.now).priority,
            "P2",
        )

    def test_generic_boilerplate_and_company_metadata_cannot_rescue_weak_fit(self):
        value = job(
            title="Software Engineer",
            location="Seattle, WA",
            description=(
                "Build scalable regional services with security and incident ownership. "
                "Requires 3+ years of experience."
            ),
        )
        rich_company = company(score=1.0)
        rich_company.fit_tags = [
            "backend",
            "distributed-systems",
            "platform",
            "security",
            "java",
            "aws",
        ]
        decision = self.ranker.evaluate(value, rich_company, self.now)
        self.assertFalse(decision.accepted)
        self.assertLess(decision.score, PROFILE["filters"]["min_match_score"])

    def test_irrelevant_ml_testing_and_federal_rejected(self):
        for title in (
            "Senior Machine Learning Engineer",
            "Software Development Engineer, Vehicle Testing",
            "Software Engineer, Federal Platform",
            "Technical Escalations Engineer 2",
        ):
            with self.subTest(title=title):
                self.assertFalse(self.ranker.evaluate(job(title=title), company(), self.now).accepted)

    def test_updated_resume_python_fastapi_api_role_is_accepted(self):
        value = job(
            title="API Engineer",
            description=(
                "Build Python FastAPI backend REST APIs on AWS using PostgreSQL and Docker. "
                "Requires 3+ years of software engineering experience."
            ),
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertIn(decision.priority, {"P0", "P1", "P2"})
        self.assertTrue(any("Python/FastAPI" in reason for reason in decision.why))

    def test_sde_alias_and_aligned_streaming_data_engineer_are_discovered(self):
        sde = job(
            title="SDE II, AWS Shield",
            description=(
                "Build Java distributed DDoS protection systems on AWS with DynamoDB. "
                "Requires 3+ years of software engineering experience."
            ),
        )
        self.assertTrue(self.ranker.evaluate(sde, company(), self.now).accepted)

        streaming_data = job(
            title="Data Engineer, Real-Time Streaming",
            description=(
                "Develop Java software for distributed Kinesis telemetry pipelines on AWS. "
                "Requires 3+ years of software engineering experience."
            ),
        )
        decision = self.ranker.evaluate(streaming_data, company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertNotEqual(decision.priority, "P0")

        for title in (
            "Security Development Engineer II",
            "Cloud Development Engineer II",
        ):
            with self.subTest(title=title):
                value = job(
                    title=title,
                    description=(
                        "Develop Java distributed security services on AWS with DynamoDB. "
                        "Requires 3+ years of software engineering experience."
                    ),
                )
                self.assertTrue(
                    self.ranker.evaluate(value, company(), self.now).accepted,
                    self.ranker.evaluate(value, company(), self.now).rejection_reasons,
                )

    def test_core_professional_evidence_and_software_operations_gate(self):
        project_only = job(
            title="Software Engineer, AI Platform",
            description=(
                "Build GraphQL, Kafka, pgvector, Docker, Prometheus, RAG, and MCP systems. "
                "Requires 3+ years of software engineering experience."
            ),
        )
        project_decision = self.ranker.evaluate(project_only, company(), self.now)
        self.assertFalse(project_decision.accepted)
        self.assertTrue(
            any("professionally evidenced core" in reason for reason in project_decision.rejection_reasons)
        )

        pure_operations = job(
            title="Cloud Infrastructure Engineer",
            description=(
                "Operate AWS accounts, networks, Kubernetes clusters, incidents, and access controls. "
                "Requires 3+ years of experience."
            ),
        )
        operations_decision = self.ranker.evaluate(pure_operations, company(), self.now)
        self.assertFalse(operations_decision.accepted)
        self.assertIn(
            "operations-oriented title lacks software-development evidence",
            operations_decision.rejection_reasons,
        )

        software_platform = job(
            title="Infrastructure Engineer",
            description=(
                "Develop Java services and AWS CDK infrastructure-as-code for a distributed platform. "
                "Requires 3+ years of software engineering experience."
            ),
        )
        self.assertTrue(self.ranker.evaluate(software_platform, company(), self.now).accepted)

    def test_direct_secondary_technology_experience_requirement_is_rejected(self):
        value = job(
            title="Backend Software Engineer",
            description=(
                "Build Java backend services on AWS. This position requires 4+ years of experience with Python."
            ),
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertFalse(decision.accepted)
        self.assertTrue(any("Python/FastAPI" in reason for reason in decision.rejection_reasons))

        alternative = job(
            title="Backend Software Engineer",
            description=(
                "Build backend services on AWS. Requires 3+ years of experience with Java or Python."
            ),
        )
        self.assertTrue(self.ranker.evaluate(alternative, company(), self.now).accepted)

    def test_secondary_technology_duration_handles_required_and_alternative_lists(self):
        required = job(
            title="Backend Software Engineer",
            description=(
                "Build backend services on AWS. Requires 3+ years of experience using Java and Python."
            ),
        )
        required_decision = self.ranker.evaluate(required, company(), self.now)
        self.assertFalse(required_decision.accepted)
        self.assertTrue(
            any("Python/FastAPI" in reason for reason in required_decision.rejection_reasons)
        )

        for description, technology in (
            (
                "Build Java services on AWS. Requires 3+ years developing distributed backend services in Python.",
                "Python/FastAPI",
            ),
            (
                "Build Java services on AWS. Requires 3+ years of software development experience building backend APIs using Python/FastAPI.",
                "Python/FastAPI",
            ),
            (
                "Build Java services on AWS. Requires 3+ years of hands-on development of Python microservices.",
                "Python/FastAPI",
            ),
            (
                "Build Java services on AWS. Requires 3+ years designing systems with Redis.",
                "Redis/ElastiCache",
            ),
            (
                "Build Java services on AWS. Requires 3+ years operating Docker-based applications.",
                "Docker/ECS",
            ),
            (
                "Build Java services on AWS. Requires 3+ years developing ML infrastructure.",
                "AI/ML application infrastructure",
            ),
            (
                "Build Java services on AWS. Requires 3+ years building AI platforms.",
                "AI/ML application infrastructure",
            ),
            (
                "Build Java services on AWS. Requires 3+ years operating GenAI systems.",
                "AI/ML application infrastructure",
            ),
            (
                "Build Java services on AWS. Requires 3+ years designing MLOps systems.",
                "AI/ML application infrastructure",
            ),
        ):
            with self.subTest(description=description):
                decision = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertFalse(decision.accepted)
                self.assertTrue(
                    any(technology in reason for reason in decision.rejection_reasons)
                )

        for description in (
            "Build backend services on AWS. Requires 3+ years of experience using Python, Java, or Go.",
            "Build backend services on AWS. Requires 3+ years of experience using C++, Java, Python, or Go.",
            "Build backend services on AWS. Requires 3+ years of experience using Java or Python.",
            "Build backend services on AWS. 3+ years of software development experience in one or "
            "more general-purpose programming languages; Go, Java, Python, Rust.",
        ):
            with self.subTest(description=description):
                decision = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertTrue(decision.accepted, decision.rejection_reasons)

        flattened_preferred = job(
            title="Backend Software Engineer",
            description=(
                "Build Java backend services on AWS. "
                "Requires 4+ years of software development experience, Python preferred."
            ),
        )
        preferred_decision = self.ranker.evaluate(flattened_preferred, company(), self.now)
        self.assertTrue(preferred_decision.accepted, preferred_decision.rejection_reasons)

        unsupported_language_list = self.ranker.evaluate(
            job(
                title="Backend Software Engineer",
                description=(
                    "Build distributed backend systems on AWS. 3+ years of software development "
                    "experience in one or more general-purpose programming languages; "
                    "Go, Python, Rust, Ruby."
                ),
            ),
            company(),
            self.now,
        )
        self.assertFalse(unsupported_language_list.accepted)
        self.assertTrue(
            any(
                "Python/FastAPI" in reason
                for reason in unsupported_language_list.rejection_reasons
            )
        )

    def test_required_frontend_and_dotnet_depth_beyond_resume_is_rejected(self):
        for description, technology in (
            (
                "Build Java Spring services on AWS. Requires 2+ years of experience using Angular and TypeScript.",
                "frontend/mobile application stack",
            ),
            (
                "Build Java services on AWS. Requires 3+ years of C#/.NET development experience.",
                ".NET/C#",
            ),
            (
                "Build Java Spring services on AWS. Requires 2+ years of experience "
                "(or relevant internship/academic projects) using Angular for front-end development.",
                "frontend/mobile application stack",
            ),
            (
                "Build Java Spring services on AWS. Requires 1+ years of experience "
                "(or relevant internship/academic projects) using Angular or a similar TypeScript framework.",
                "frontend/mobile application stack",
            ),
        ):
            with self.subTest(technology=technology):
                decision = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertFalse(decision.accepted)
                self.assertTrue(
                    any(technology in reason for reason in decision.rejection_reasons)
                )

        for description in (
            "Build services on AWS. Requires 3+ years of experience using Java or TypeScript.",
            "Build services on AWS. Requires 3+ years of experience using Java or .NET.",
        ):
            with self.subTest(description=description):
                decision = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertTrue(decision.accepted, decision.rejection_reasons)

    def test_unverified_specialist_domains_do_not_leak_through_backend_keywords(self):
        specialist_descriptions = (
            (
                "Build Java AWS APIs. Work across SAP enterprise systems with ABAP, S/4HANA, "
                "BTP, and CDS views. Requires 4+ years of hands-on SAP development experience."
            ),
            (
                "Build Java distributed systems on AWS. Experience in Games Industry is required. "
                "Requires 4+ years of software engineering experience."
            ),
            (
                "Build AWS inference systems. Develop performance-critical kernels and compiler "
                "support for Trainium accelerators. Requires 3+ years of engineering experience."
            ),
            (
                "Build Java AWS services and machine learning models. Own model training, inference, "
                "and the computer vision model lifecycle with Applied Scientists. Requires 3+ years."
            ),
            (
                "Build Java AWS platform automation. Advanced Python and .NET skills are required. "
                "Requires 4+ years of engineering experience."
            ),
            (
                "Build Java distributed systems on AWS. Hands-on production-level code experience. "
                "Experience in C++ is required. Requires 3+ years of engineering experience."
            ),
            (
                "Build Java AWS services. We are looking for a full-stack software engineer to own "
                "customer-facing applications. Requires 3+ years of engineering experience."
            ),
            (
                "Develop products primarily using Java for backend and React/JavaScript for frontend. "
                "Requires 3+ years of software engineering experience."
            ),
            (
                "Build Java distributed cloud systems. Qualifications include experience with data "
                "privacy, privacy-preserving analytics, and deploying AI/ML solutions. Requires 4+ years."
            ),
            (
                "Build Java security services on AWS. Required Skills and Experience include OAuth 2.0, "
                "OpenID Connect, JWT, PKCE, gRPC, and Protocol Buffers. Requires 5+ years."
            ),
            (
                "Build Java backend systems on AWS. Experience with data-driven systems, ML-powered "
                "features, or A/B experimentation platforms, backend APIs (e.g., gRPC), and Flink or "
                "Spark is required. Requires 5+ years."
            ),
            (
                "Build Java security APIs. Required skills include MFA, SSO, OAuth 2.0, and working "
                "knowledge of PHP. Requires 5+ years of engineering experience."
            ),
            (
                "Build Java distributed media services. Requires familiarity with HLS, MPEG-DASH, MP4, "
                "H.264, H.265, VP9, and AV1. Requires 5+ years of engineering experience."
            ),
            (
                "Build Java payment APIs. 3+ years of relevant industry experience (Payments/Fintech) "
                "as a backend software engineer."
            ),
            (
                "Build Java payment systems on AWS. Experience leading design, implementation, and "
                "deployment of one or more high scale, cross-functional payment systems. Requires 5+ years."
            ),
            (
                "Build distributed infrastructure on AWS. Requires deep expertise in systems-level "
                "performance analysis, profiling, and a track record of reducing infrastructure costs. "
                "Requires 5+ years of engineering experience."
            ),
        )
        for description in specialist_descriptions:
            with self.subTest(description=description):
                decision = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertFalse(decision.accepted)
                self.assertIn(
                    "posting requires a specialist domain not established by the resume",
                    decision.rejection_reasons,
                )

        aligned_trainium_backend = self.ranker.evaluate(
            job(
                title="Software Development Engineer, EC2 Trainium Infrastructure",
                description=(
                    "Build scalable Java microservices and AWS-native provisioning workflows for "
                    "Trainium infrastructure. Requires 3+ years of software engineering experience."
                ),
            ),
            company(),
            self.now,
        )
        self.assertTrue(aligned_trainium_backend.accepted, aligned_trainium_backend.rejection_reasons)

        for description in (
            "Build Java backend services on AWS and collaborate with full-stack engineers. "
            "Requires 4+ years of software engineering experience.",
            "Build Java payment services and distributed APIs on AWS. Requires 4+ years of "
            "software engineering experience.",
            "Build Java event-streaming metadata services on AWS. Requires 4+ years of software "
            "engineering experience.",
        ):
            with self.subTest(aligned_description=description):
                aligned = self.ranker.evaluate(
                    job(title="Backend Software Engineer", description=description),
                    company(),
                    self.now,
                )
                self.assertTrue(aligned.accepted, aligned.rejection_reasons)

    def test_false_positive_classes_from_weekly_audit_are_rejected(self):
        descriptions = (
            "Build Python backend services. Architect medical robots and mechatronic instrumentation "
            "using motion control and FDA requirements. Requires 3+ years.",
            "Build Python network tooling. Develop functional test plan, execute test cases, automate "
            "test cases for regression using networking test equipment. Requires 4+ years.",
            "Build AWS cloud services. Advanced programming skills in Golang are required, with "
            "Kubernetes, CSI, and PV/PVC experience. Requires 3+ years.",
            "Requires 3+ years of professional full-stack software engineering experience shipping "
            "production systems in Go and TypeScript/React with Next.js.",
            "Requires 4+ years of platform engineering. Hands-on experience with Google Cloud Platform "
            "and experience building and scaling AI agents are required.",
            "Basic programming skills in Java. You will work closely with senior developers and learn "
            "from senior engineers.",
            "Experience in software development, including internships, co-ops, apprenticeships, "
            "academic projects, or professional experience.",
            "Requires 1+ years with Generative AI and LLM-based systems, shipping product features "
            "to production.",
            "Requires 4+ years of experience designing, building, and supporting enterprise software "
            "applications. Hands-on experience with at least one of the following areas: agentic systems, "
            "retrieval-augmented generation, generative AI, or large language model applications.",
            "Bachelor's Degree and 1+ year(s) technical engineering experience, or Master's Degree in "
            "Computer Science or related technical field with proven experience coding.",
        )
        for description in descriptions:
            with self.subTest(description=description):
                decision = self.ranker.evaluate(
                    job(title="Software Engineer II", description=description), company(), self.now
                )
                self.assertFalse(decision.accepted)
                self.assertIn(
                    "posting requires a specialist domain not established by the resume",
                    decision.rejection_reasons,
                )

    def test_ai_platform_is_secondary_but_pure_ai_and_ml_roles_stay_rejected(self):
        platform = job(
            title="Software Engineer, AI Platform",
            description=(
                "Build Java Spring AI backend services and RAG infrastructure with MCP, pgvector, "
                "AWS, Redis, and distributed systems. Requires 4+ years of experience."
            ),
        )
        platform_decision = self.ranker.evaluate(platform, company(), self.now)
        self.assertTrue(platform_decision.accepted, platform_decision.rejection_reasons)
        self.assertEqual(platform_decision.priority, "P1")

        for title in ("AI Engineer", "Machine Learning Engineer", "Applied Scientist"):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(
                    job(
                        title=title,
                        description=(
                            "Build Python FastAPI services, RAG systems, and distributed AWS "
                            "infrastructure. Requires 4+ years of experience."
                        ),
                    ),
                    company(),
                    self.now,
                )
                self.assertFalse(decision.accepted)

    def test_secondary_ai_platform_spellings_are_order_independent_and_never_p0(self):
        for title in (
            "Software Engineer, Backend Platform - Artificial Intelligence",
            "Software Engineer, Backend Platform - GenAI",
            "Software Engineer, MLOps Platform",
            "Platform Engineer, Machine Learning",
            "Infrastructure Engineer - Machine Learning",
            "Machine Learning Platform Engineer",
            "Model Serving Infrastructure Engineer",
        ):
            with self.subTest(title=title):
                value = job(
                    title=title,
                    description=(
                        "Build Java backend distributed platform software on AWS with DynamoDB. "
                        "Requires 4+ years of software engineering experience."
                    ),
                )
                decision = self.ranker.evaluate(value, company(), self.now)
                self.assertTrue(decision.accepted, decision.rejection_reasons)
                self.assertNotEqual(decision.priority, "P0")

    def test_ml_infrastructure_can_match_only_as_software_platform_work(self):
        value = job(
            title="Software Engineer, Machine Learning Infrastructure",
            description=(
                "Build Java backend distributed serving systems on AWS with DynamoDB. "
                "Requires 4+ years of software engineering experience."
            ),
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertNotEqual(decision.priority, "P0")

    def test_unshown_kubernetes_and_terraform_do_not_create_a_skill_match(self):
        value = job(
            title="Software Engineer",
            description="Kubernetes and Terraform. Requires 3+ years of experience.",
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertFalse(decision.accepted)
        self.assertFalse(any("platform/infrastructure" in reason for reason in decision.why))

        unsupported = job(
            title="Software Engineer",
            description="WAF and disaster recovery. Requires 3+ years of experience.",
        )
        unsupported_decision = self.ranker.evaluate(unsupported, company(), self.now)
        self.assertFalse(unsupported_decision.accepted)
        self.assertFalse(any("security/DDoS" in reason for reason in unsupported_decision.why))
        self.assertFalse(any("multi-region" in reason for reason in unsupported_decision.why))

    def test_redmond_area_does_not_override_technical_relevance(self):
        description = (
            "Build Python FastAPI backend APIs on AWS using PostgreSQL. "
            "Requires 3+ years of software engineering experience."
        )
        seattle = self.ranker.evaluate(
            job(title="API Engineer", location="Seattle, WA", description=description),
            company(),
            self.now,
        )
        new_york = self.ranker.evaluate(
            job(title="API Engineer", location="New York, NY", description=description),
            company(),
            self.now,
        )
        self.assertTrue(seattle.accepted)
        self.assertTrue(new_york.accepted)
        self.assertEqual(seattle.score, new_york.score)

    def test_real_world_irrelevant_and_clearance_titles_rejected(self):
        for title in (
            "Data Engineer, Monetization Data Platform",
            "Software Integration Support Engineer",
            "Senior Software Engineer, Core UI",
            "Electrical Engineer, Actuator Test Infrastructure",
            "Quantum Systems Software Development Engineer II",
            "Sr. Software Consultant-CTJ-Top Secret/SCI",
            "Software Engineer, Verification Platform",
            "Software Engineer, Validation Infrastructure",
            "Software Engineer, V&V Platform",
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
            "H-1B transfers are not supported.",
            "We do not accept H-1B transfers.",
            "This role is not eligible for visa support.",
            "No immigration assistance is available.",
            "Candidates must have unrestricted work authorization.",
            "We are unable to provide work authorization assistance.",
            "This role is not open to visa sponsorship.",
            "We are not considering candidates who require visa sponsorship.",
            "Candidates requiring sponsorship are not eligible for hire.",
            "Sponsorship for employment authorization is not available.",
            "We are unable to sponsor new applicants for employment authorization.",
            "Visa sponsorship cannot be accommodated.",
            "No work visa sponsorship will be provided.",
            "Visa sponsorship not available.",
            "Visa sponsorship: not available.",
            "Sponsorship not offered.",
            "No sponsorship provided.",
            "No sponsorship offered.",
            "We cannot accommodate visa sponsorship.",
            "We do not accommodate visa sponsorship.",
            "We are not offering sponsorship for this role.",
            "Employment sponsorship not available.",
            "We don't sponsor visas.",
            "We won't sponsor visas.",
            "We won’t sponsor visas.",
            "H-1B not supported.",
            "H1B candidates cannot be considered.",
            "No H-1B transfers.",
            "Candidates must not require sponsorship.",
            "Applicants must not now or in the future require visa sponsorship.",
            "No H-1B sponsorship.",
            "H-1B sponsorship unavailable.",
            "H-1B transfers cannot be supported.",
            "We cannot transfer H-1Bs.",
            "We do not process H-1B transfers.",
            "Visa sponsorship: no.",
            "Sponsorship: None.",
            "Immigration support is not provided.",
            "No future sponsorship is available.",
            "No sponsorship.",
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
            "Batumi, Georgia",
        ):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertIn("non-US location", decision.rejection_reasons)

    def test_us_cities_named_like_foreign_locations_use_explicit_state_suffix(self):
        for location in (
            "Dublin, OH",
            "Dublin, Ohio",
            "Dublin, CA",
            "London, Kentucky",
            "New London, CT",
            "Mexico, Missouri",
            "Sweden, ME",
            "Brazil, IN",
            "Panama City, FL",
            "Vancouver, WA",
            "Vancouver, Washington",
        ):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertNotIn("non-US location", decision.rejection_reasons)

        workplace_value = job(location="Dublin, CA")
        workplace_value.workplace_type = "Hybrid"
        self.assertNotIn(
            "non-US location",
            self.ranker.evaluate(workplace_value, company(), self.now).rejection_reasons,
        )
        for location in (
            "Dublin, CA (Hybrid)",
            "Vancouver, WA Remote",
            "London, OH On-site",
            "Panama City, FL Hybrid",
        ):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertNotIn("non-US location", decision.rejection_reasons)

    def test_structured_country_overrides_ambiguous_state_code(self):
        value = job(location="Karnataka, IN")
        value.raw = {
            "jobLocation": {
                "address": {"addressRegion": "Karnataka", "addressCountry": "IN"}
            }
        }
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertIn("non-US location", decision.rejection_reasons)

    def test_location_country_scope_and_remote_inference_are_conservative(self):
        for location in (
            "Remote - Argentina",
            "Remote - Colombia",
            "Remote - Portugal",
            "Remote - Switzerland",
            "Remote - Costa Rica",
        ):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertFalse(decision.accepted)
                self.assertIn("non-US location", decision.rejection_reasons)

        missing = self.ranker.evaluate(job(location=""), company(), self.now)
        self.assertFalse(missing.accepted)
        self.assertIn("US eligibility could not be verified from location", missing.rejection_reasons)

        value = job(location="London, UK")
        value.raw = {
            "jobLocation": {"address": {"addressCountry": "GB"}},
            "hiringOrganization": {"address": {"addressCountry": "US"}},
        }
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertIn("non-US location", decision.rejection_reasons)

        generic_remote = self.ranker.evaluate(job(location="Remote"), company(), self.now)
        self.assertNotIn("US eligibility could not be verified from location", generic_remote.rejection_reasons)

        provider_country = job(location="Remote")
        provider_country.raw = {"country": "CA"}
        provider_decision = self.ranker.evaluate(provider_country, company(), self.now)
        self.assertIn("non-US location", provider_decision.rejection_reasons)

        new_mexico = self.ranker.evaluate(job(location="Albuquerque, New Mexico"), company(), self.now)
        self.assertNotIn("non-US location", new_mexico.rejection_reasons)

        tbilisi = self.ranker.evaluate(job(location="Tbilisi, Georgia"), company(), self.now)
        self.assertIn("non-US location", tbilisi.rejection_reasons)

        for location in ("Remote, CA", "Remote, IN"):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertIn(
                    "US eligibility could not be verified from location",
                    decision.rejection_reasons,
                )

    def test_mixed_location_with_a_real_us_option_is_allowed(self):
        decision = self.ranker.evaluate(
            job(location="Toronto, Canada | New York, US"), company(), self.now
        )
        self.assertNotIn("non-US location", decision.rejection_reasons)

    def test_plain_us_location_marker_is_recognized(self):
        for location in ("US", "Seattle, US"):
            with self.subTest(location=location):
                decision = self.ranker.evaluate(job(location=location), company(), self.now)
                self.assertNotIn(
                    "US eligibility could not be verified from location",
                    decision.rejection_reasons,
                )

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

    def test_domain_words_do_not_rescue_non_software_role_shapes(self):
        for title in (
            "Customer Engineer, Cloud Platform",
            "Developer Advocate, Backend Platform",
            "Technical Product Owner, Backend Platform",
            "Scrum Master, Cloud Platform",
            "Technical Writer, Backend Platform",
            "Systems Administrator, Cloud Platform",
            "Network Engineer, Cloud Platform",
            "Customer Systems Engineer",
            "Field Systems Engineer",
            "Business Systems Engineer",
            "IT Systems Engineer",
            "Controls Systems Engineer",
            "Manufacturing Systems Engineer",
            "Enterprise Systems Engineer",
            "Software Engineering Scrum Master",
            "Product Owner, Software Engineering",
            "Software Engineering Project Coordinator",
            "Technical Writer, Software Engineering",
            "Developer Advocate, Software Engineering",
            "Customer Engineer, Software Engineering",
            "Business Systems Analyst, Software Engineering",
            "Software Engineering Administrator",
            "Agile Coach, Software Engineering",
            "Head, Software Engineering",
        ):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(job(title=title), company(), self.now)
                self.assertFalse(decision.accepted)
                self.assertIn(
                    "title lacks a target engineering discipline",
                    decision.rejection_reasons,
                )

    def test_explicit_software_systems_role_shapes_remain_eligible(self):
        for title in (
            "Distributed Systems Engineer",
            "Systems Software Engineer",
            "Software Systems Engineer",
            "Systems Development Engineer II",
        ):
            with self.subTest(title=title):
                decision = self.ranker.evaluate(job(title=title), company(), self.now)
                self.assertTrue(decision.accepted, decision.rejection_reasons)

    def test_department_scope_is_used_without_excluding_ml_platform_teams(self):
        for department in (
            "iOS / Mobile",
            "Frontend UI",
            "Quality Assurance",
            "Machine Learning Research",
            "Data Science",
            "Robotics",
            "Quality Engineering",
            "Test Engineering",
            "Software Test",
            "Validation",
            "Verification",
            "V&V",
            "Customer Engineering",
            "Professional Services",
            "Sales Engineering",
            "Solutions Engineering",
            "Technical Support",
        ):
            with self.subTest(department=department):
                value = job(title="Software Engineer II")
                value.department = department
                decision = self.ranker.evaluate(value, company(), self.now)
                self.assertFalse(decision.accepted)
                self.assertIn(
                    "department is outside backend/platform/security/SRE scope",
                    decision.rejection_reasons,
                )

        platform_value = job(title="Software Engineer II")
        platform_value.department = "Machine Learning Platform Infrastructure"
        platform_decision = self.ranker.evaluate(platform_value, company(), self.now)
        self.assertTrue(platform_decision.accepted, platform_decision.rejection_reasons)
        self.assertNotEqual(platform_decision.priority, "P0")

    def test_all_configured_matching_regexes_are_validated_at_startup(self):
        profile = copy.deepcopy(PROFILE)
        profile["matching"]["skill_groups"][0]["patterns"][0] = "[unterminated"
        with self.assertRaises(Exception):
            Ranker(profile)

    def test_year_extraction_ignores_preferred_when_required_exists(self):
        text = "Requires 3+ years of experience. Preferred: 8+ years of Java."
        self.assertEqual(extract_years(text)[0], 3.0)

    def test_flattened_long_preferred_qualification_section_is_not_required(self):
        for heading in ("Preferred Qualifications", "Preferred Experience", "Preferred Skills", "Nice to have"):
            with self.subTest(heading=heading):
                text = (
                    "Minimum Qualifications: 3+ years of software engineering experience. "
                    f"{heading}: experience leading distributed-system design reviews, "
                    "mentoring engineers across several teams, operating high-throughput production "
                    "services, improving observability, and building reliable cloud platforms; "
                    "8+ years of software engineering experience."
                )
                self.assertEqual(extract_years(text), (3.0, 3.0))

    def test_preferred_qualification_prose_is_not_a_section_heading(self):
        text = (
            "Even if you do not meet all of the preferred qualifications and skills listed, "
            "we encourage candidates to apply. "
            "5+ years of required software engineering experience."
        )
        self.assertEqual(extract_years(text), (5.0, 5.0))

    def test_common_required_experience_formats_and_strict_floors(self):
        for text in (
            "6 yrs. of software engineering experience required.",
            "6 yr. of software engineering experience required.",
            "6-year software engineering experience required.",
            "six-year software engineering experience required.",
            "Experience: 6+ years.",
            "Professional experience: 6+ years.",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_years(text), (6.0, 6.0))
        self.assertEqual(
            extract_years(
                "3+ years of industry experience. 5+ years of hands-on, professional "
                "software development experience."
            ),
            (5.0, 5.0),
        )
        for text in (
            "More than 5 years of software engineering experience required.",
            "Over 5 years of software engineering experience required.",
            "Greater than 5 years of software engineering experience required.",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_years(text), (6.0, 6.0))

    def test_year_range_is_not_double_counted(self):
        self.assertEqual(extract_years("Requires 3-5 years of experience."), (3.0, 5.0))

    def test_year_abbreviations_words_and_degree_alternatives(self):
        self.assertEqual(extract_years("Requires 3 yrs of experience."), (3.0, 3.0))
        self.assertEqual(extract_years("Requires three years of experience."), (3.0, 3.0))
        self.assertEqual(extract_years("Requires 3 or more years of experience."), (3.0, 3.0))
        self.assertEqual(extract_years("Requires four-plus years of experience."), (4.0, 4.0))
        for text, expected in (
            ("4+ years required.", 4.0),
            ("4+ years is required.", 4.0),
            ("4 years minimum.", 4.0),
            ("Requires 3+ years of demonstrated experience.", 3.0),
            ("Requires 3+ years of proven experience.", 3.0),
            ("Requires 3+ years’ experience.", 3.0),
            ("Requires 3+ years' experience.", 3.0),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_years(text)[0], expected)
        self.assertEqual(
            extract_years(
                "Requires a Bachelor's degree and 7+ years of experience, or a Master's degree and 5+ years of experience."
            ),
            (5.0, 5.0),
        )
        self.assertEqual(
            extract_years(
                "Requires a Master's degree and 3+ years of experience, or a Bachelor's degree and 5+ years of experience."
            ),
            (3.0, 3.0),
        )
        self.assertEqual(
            extract_years(
                "Bachelor's degree with 5+ years of experience; or Master's degree with 3+ years of experience."
            ),
            (3.0, 3.0),
        )
        self.assertEqual(
            extract_years(
                "Requires 3+ years of experience with a Master's degree, or 5+ years of experience with a Bachelor's degree."
            ),
            (3.0, 3.0),
        )
        self.assertEqual(
            extract_years(
                "A Bachelor's or Master's degree and 3+ years of backend experience plus 6+ years of Java experience are required."
            ),
            (6.0, 6.0),
        )
        self.assertEqual(
            extract_years(
                "A Master's degree and 5+ years of experience, or 8+ years of equivalent experience without a degree."
            ),
            (5.0, 5.0),
        )
        self.assertEqual(
            extract_years(
                "A Master's degree and 5+ years, or 8+ years of experience without a degree."
            ),
            (5.0, 5.0),
        )
        self.assertEqual(
            extract_years(
                "A Bachelor's degree with 5+ years of experience or 7+ years of experience without a degree."
            ),
            (5.0, 5.0),
        )

    def test_company_age_and_benefit_years_are_not_experience(self):
        for text in (
            "For over 10 years, we have built cloud software. Requires 3+ years of experience.",
            "Founded 8 years ago, we build systems. Requires 3+ years backend experience.",
            "Benefits vest after 7 years of service. Requires 3+ years of engineering experience.",
            "Acme has operated for 10+ years building cloud software. Requires 3+ years of experience.",
            "Our team has 10+ years of experience. Requires 3+ years of engineering experience.",
            "We bring 8+ years of experience. Requires 3+ years of engineering experience.",
            "The company has 12+ years of experience. Requires 3+ years of engineering experience.",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_years(text)[0], 3.0)

        sectioned = (
            "Minimum qualifications:\n3+ years of software engineering experience.\n"
            "Preferred qualifications:\n8+ years of Java experience."
        )
        self.assertEqual(extract_years(sectioned), (3.0, 3.0))

    def test_export_control_and_clearance_phrases_rejected(self):
        for restriction in (
            "U.S. Person required.",
            "Applicants must be U.S. persons due to export controls.",
            "Must possess a Secret clearance.",
            "US Citizen or Green Card holder only.",
            "This role requires ITAR eligibility.",
            "To comply with U.S. export control laws, candidates may need to meet certain legal status requirements.",
            "Active US Security Clearance required.",
            "Eligibility and willingness to obtain a US Security Clearance is required.",
            "Candidates must have the ability and willingness to obtain a U.S. Government security clearance.",
            "Must be eligible to obtain a security clearance.",
            "Ability to obtain a security clearance is required.",
            "Must be able to obtain and maintain a Secret clearance.",
            "Must be eligible for a Secret clearance.",
            "Must have or be able to obtain Secret clearance.",
            "Clearance eligibility is required.",
            "Must be a citizen of the United States.",
            "Only U.S. citizens may apply.",
            "Open only to U.S. citizens.",
            "This position is limited to US Persons.",
            "Must be a permanent resident or US citizen.",
            "United States citizenship is required.",
            "Applicants must be US nationals.",
            "Secret clearance required.",
            "Security clearance is required.",
            "Current Secret clearance required.",
            "Must hold a Secret clearance.",
            "Must obtain DoD Secret.",
            "TS clearance required.",
            "Only U.S. Persons may apply.",
            "U.S. national status required.",
            "Permanent residents only.",
            "No foreign nationals.",
            "Must qualify as a U.S. Person under ITAR.",
        ):
            value = job(description=job().description + " " + restriction)
            with self.subTest(restriction=restriction):
                self.assertFalse(self.ranker.evaluate(value, company(), self.now).accepted)

    def test_explicitly_optional_clearance_language_does_not_reject(self):
        value = job(
            description=(
                job().description
                + " Active UK or US Security clearance, or eligibility and willingness to obtain "
                "one, is beneficial, but not necessary."
            )
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)

    def test_unrelated_preference_does_not_make_mandatory_restriction_optional(self):
        for restriction in (
            "U.S. citizenship is required and Python experience is preferred.",
            "Candidates must be U.S. citizens, while AWS experience is preferred.",
            "An active US security clearance is required, and Java is a plus.",
        ):
            with self.subTest(restriction=restriction):
                value = job(description=job().description + " " + restriction)
                decision = self.ranker.evaluate(value, company(), self.now)
                self.assertFalse(decision.accepted)
                self.assertTrue(
                    any("citizenship/clearance" in reason for reason in decision.rejection_reasons)
                )

    def test_software_dev_engineer_alias_receives_general_title_credit(self):
        value = job(
            title="Software Dev Engineer II, AWS Glacier",
            description=(
                "Build Java distributed storage systems on AWS with DynamoDB. "
                "Requires 3+ years of experience."
            ),
        )
        decision = self.ranker.evaluate(value, company(), self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertGreaterEqual(decision.score, PROFILE["filters"]["min_match_score"])

    def test_suffix_preferred_is_not_required(self):
        text = "Requires 3+ years of experience. 8+ years preferred."
        self.assertEqual(extract_years(text)[0], 3.0)

    def test_positive_sponsorship(self):
        self.assertEqual(
            sponsorship_signal("H-1B transfer sponsorship is available."),
            "explicit_h1b_sponsorship_available",
        )
        self.assertEqual(sponsorship_signal("We do sponsor visas!"), "explicit_sponsorship_available")

    def test_generic_visa_language_gets_only_a_modest_role_level_boost(self):
        low_evidence = company(score=0.30)
        value = job(
            title="Backend Software Engineer",
            description=(
                "Build Java Spring Boot distributed backend systems on AWS with DynamoDB. "
                "Requires 4+ years of experience. Visa sponsorship is available."
            ),
        )
        decision = self.ranker.evaluate(value, low_evidence, self.now)
        self.assertTrue(decision.accepted, decision.rejection_reasons)
        self.assertEqual(decision.sponsorship_score, 0.58)
        self.assertEqual(decision.priority, "P2")


if __name__ == "__main__":
    unittest.main()
