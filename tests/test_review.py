"""Tests of the program that makes the review comment."""

import importlib.util
from pathlib import Path

PATH = Path(__file__).parent.parent / ".github" / "review.py"
SPEC = importlib.util.spec_from_file_location("review", PATH)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)

CONTEXT = """<<<DIFF>>>
+    return round(float(part) / float(total), 4) if total else None
-    old_line_that_was_removed = 1
<<<END DIFF>>>
"""


def finding(quote, check="code"):
    return {
        "check": check,
        "level": "HIGH",
        "file": "a.py",
        "quote": quote,
        "problem": "P.",
        "action": "A.",
    }


def test_finding_with_a_quote_that_is_not_in_the_text_is_deleted():
    real = finding("return round(float(part) / float(total), 4) if total else None")
    invented = finding("this line is not in the diff or in a document")
    short = finding("return")
    kept, deleted = review.keep([real, invented, short], CONTEXT)
    assert (kept, deleted) == ([real], 2)


def test_quote_can_have_different_spaces_and_no_diff_mark():
    spaced = finding("return   round(float(part) / float(total), 4)   if total else None")
    assert review.keep([spaced], CONTEXT) == ([spaced], 0)


def test_comment_gives_the_findings_and_the_number_of_deleted_findings():
    answer = {
        "findings": [
            finding("old_line_that_was_removed = 1", "method"),
            finding("an invented quote that is long enough"),
        ],
        "examined": "E.",
        "weakest_claim": "W.",
        "test": "T.",
    }
    comment = review.render(answer, CONTEXT)
    assert "**Findings: 1.** Deleted because the quote is not in the text: 1." in comment
    assert "#### method" in comment
    assert "#### code" not in comment
    assert "**Weakest claim.** W." in comment
