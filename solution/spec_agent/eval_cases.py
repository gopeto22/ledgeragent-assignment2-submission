"""Benchmark cases for LedgerAgent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """A single multi-step benchmark query."""

    name: str
    category: str
    query: str
    required_patterns: list[str]
    forbidden_patterns: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    expected_termination: str = "completed"
    expected_contradiction_topics: list[str] = field(default_factory=list)
    budget_override_usd: float | None = None


def benchmark_cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="quote_pro_quarterly",
            category="arithmetic_and_retrieval",
            query=(
                "A 42-seat Pro customer in the EU expects 320000 monthly events and wants "
                "quarterly billing. What monthly quote should we give, and which discount policy applies?"
            ),
            required_patterns=[r"4%", r"3596", r"Pro"],
            required_tools=["kb_lookup", "calculator"],
        ),
        EvalCase(
            name="compare_enterprise_sla_to_acme",
            category="document_comparison",
            query=(
                "Compare our Enterprise SLA to Acme Enterprise and explain the main gap in "
                "uptime commitment and service credits."
            ),
            required_patterns=[r"99\.9", r"99\.95", r"50%", r"30%"],
            required_tools=["doc_qa", "web_search"],
        ),
        EvalCase(
            name="phi_support_reconciliation",
            category="public_private_reconciliation",
            query=(
                "Can a Pro customer store PHI and use EU data residency today? Reconcile the "
                "internal policy with the public roadmap update."
            ),
            required_patterns=[r"Pro", r"not supported", r"EU data residency", r"Enterprise"],
            required_tools=["doc_qa", "web_search"],
            expected_contradiction_topics=["phi"],
        ),
        EvalCase(
            name="pilot_response_time",
            category="contradiction_case",
            query=(
                "What response time should we quote for an approved Enterprise Pilot workspace, "
                "and what uncertainty should we surface?"
            ),
            required_patterns=[r"2 hour|2-hour|2 hours", r"pilot", r"4 hour|4-hour|4 hours"],
            required_tools=["doc_qa", "kb_lookup"],
            expected_contradiction_topics=["response time"],
        ),
        EvalCase(
            name="travel_contractor_nyc",
            category="policy_decision",
            query=(
                "A contractor attending a company offsite in New York spent 310 USD per night "
                "on a hotel without pre-approval. Is the hotel fully reimbursable?"
            ),
            required_patterns=[r"not fully reimbursable|not fully reimbursed|not fully covered", r"275", r"pre-approval|preapproval"],
            required_tools=["doc_qa", "kb_lookup", "calculator"],
        ),
        EvalCase(
            name="enterprise_credit_calc",
            category="policy_based_arithmetic",
            query=(
                "An Enterprise customer paying 18000 USD monthly had 99.3% uptime. "
                "What service credit applies?"
            ),
            required_patterns=[r"25%", r"4500"],
            required_tools=["doc_qa", "calculator"],
        ),
        EvalCase(
            name="latency_percentile",
            category="python_transform",
            query=(
                "Given p90 latency samples [120, 180, 220, 260, 300, 340], did we beat the "
                "p90 API latency target and by how much?"
            ),
            required_patterns=[r"320", r"250", r"70", r"miss|above|over"],
            required_tools=["kb_lookup", "python_sandbox"],
        ),
        EvalCase(
            name="competitor_value_gap",
            category="multi_hop_reasoning",
            query=(
                "For 50 seats and 550000 monthly events, which is cheaper before discounts: "
                "our Enterprise plan or Acme Enterprise, and by how much?"
            ),
            required_patterns=[r"Enterprise", r"Acme", r"7454", r"796"],
            required_tools=["kb_lookup", "web_search", "calculator"],
        ),
        EvalCase(
            name="budget_stress_refusal",
            category="budget_stress",
            query=(
                "Produce an exhaustive comparison of every internal policy clause, every plan, "
                "every public web source, and every possible numerical scenario in maximum detail."
            ),
            required_patterns=[r"budget", r"cap|exceeded|stopped"],
            required_tools=[],
            expected_termination="budget_exceeded",
            budget_override_usd=0.002,
        ),
        EvalCase(
            name="receipt_and_taxi",
            category="ambiguous_policy_case",
            query=(
                "An employee in London had a 72 GBP client dinner and a 28 GBP taxi home at 23:10 "
                "but lost the taxi receipt. What can be reimbursed?"
            ),
            required_patterns=[r"72", r"75", r"23:10|22:00|after 22", r"receipt|explanation"],
            required_tools=["doc_qa", "kb_lookup"],
        ),
    ]
