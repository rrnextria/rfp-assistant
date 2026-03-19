"""Adaptive Card v1.5 builder for RFP Assistant Teams bot responses."""
from __future__ import annotations


def build_adaptive_card(
    answer: str,
    citations: list[dict],
    mode: str = "answer",
) -> dict:
    """Return an Adaptive Card v1.5 dict ready for Bot Framework attachment.

    Args:
        answer: The answer text from the orchestrator.
        citations: List of dicts with keys 'chunk_id', 'doc_id', 'snippet'.
        mode: The query mode (answer, draft, review, gap) — shown as a badge.

    Returns:
        Adaptive Card JSON as a Python dict.
    """
    mode_colors = {
        "answer": "Good",
        "draft": "Accent",
        "review": "Warning",
        "gap": "Attention",
    }
    badge_color = mode_colors.get(mode, "Default")

    body: list[dict] = [
        {
            "type": "TextBlock",
            "text": "RFP Assistant",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": mode.upper(),
                            "color": badge_color,
                            "size": "Small",
                            "weight": "Bolder",
                        }
                    ],
                }
            ],
        },
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
            "spacing": "Medium",
        },
    ]

    if citations:
        facts = [
            {
                "title": c.get("doc_id", ""),
                "value": c.get("snippet", ""),
            }
            for c in citations
        ]
        body.append(
            {
                "type": "TextBlock",
                "text": "Sources",
                "weight": "Bolder",
                "spacing": "Medium",
                "wrap": True,
            }
        )
        body.append({"type": "FactSet", "facts": facts})

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body,
    }


def build_error_card(title: str, message: str) -> dict:
    """Return a simple error Adaptive Card."""
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "RFP Assistant",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": title,
                "color": "Attention",
                "weight": "Bolder",
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": message,
                "wrap": True,
            },
        ],
    }
