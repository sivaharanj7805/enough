"""Tests for fast intent classification — zero-API pattern matching."""

import pytest

from app.services.fast_intent import classify_intent


class TestClassifyIntent:
    """Test keyword + URL slug pattern matching."""

    # ── Transactional ──

    def test_pricing_page(self):
        assert classify_intent("Pricing Plans", "/pricing", 200) == "transactional"

    def test_free_trial_title(self):
        assert classify_intent("Start Your Free Trial Today", "/start", 500) == "transactional"

    def test_signup_slug(self):
        assert classify_intent("Create Account", "/signup", 100) == "transactional"

    def test_demo_slug(self):
        assert classify_intent("Book a Demo", "/demo", 300) == "transactional"

    def test_get_started_slug(self):
        assert classify_intent("Get Started Now", "/get-started", 100) == "transactional"

    # ── Commercial ──

    def test_best_tools(self):
        assert classify_intent("Best CRM Tools for Startups", "/best-crm-tools", 2000) == "commercial"

    def test_comparison_slug(self):
        assert classify_intent("HubSpot vs Salesforce", "/hubspot-vs-salesforce-comparison", 3000) == "commercial"

    def test_alternative_title(self):
        assert classify_intent("Top 10 Alternatives to Slack", "/slack-alternatives", 1500) == "commercial"

    def test_review_title(self):
        assert classify_intent("Notion Review 2024", "/notion-review", 2500) == "commercial"

    # ── Navigational ──

    def test_login_slug(self):
        assert classify_intent("Sign In", "/login", 100) == "navigational"

    def test_documentation_title(self):
        assert classify_intent("API Documentation", "/docs", 5000) == "navigational"

    def test_support_slug(self):
        assert classify_intent("Help Center", "/support", 200) == "navigational"

    def test_contact_title(self):
        assert classify_intent("Contact Us", "/contact", 150) == "navigational"

    # ── Informational (default) ──

    def test_how_to_guide(self):
        assert classify_intent("How to Build a REST API in Python", "/rest-api-python", 3000) == "informational"

    def test_tutorial(self):
        assert classify_intent("Understanding Docker Containers", "/docker-containers", 4000) == "informational"

    def test_generic_blog(self):
        assert classify_intent("The Future of Remote Work", "/future-remote-work", 2000) == "informational"

    def test_empty_inputs(self):
        assert classify_intent("", "", 0) == "informational"

    def test_short_post_informational(self):
        """Short posts without signal words default to informational."""
        assert classify_intent("Company Update March", "/update-march", 300) == "informational"

    # ── Edge cases ──

    def test_slug_takes_priority(self):
        """URL slug patterns should match even with a generic title."""
        assert classify_intent("Welcome", "/pricing", 100) == "transactional"

    def test_case_insensitive(self):
        assert classify_intent("BEST CRM Software", "/best-crm", 1000) == "commercial"
