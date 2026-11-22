"""Make the pull request comment from the answer of the review model.

The model must give a quote for each finding. This program keeps a finding only if its quote
is in the text that the model got. Thus a finding about text that does not exist is deleted.
"""

import json
import re
import sys
from pathlib import Path

CHECKS = ("claims", "method", "code", "documents", "sources", "interpretation")
MIN_QUOTE = 20


def plain(text: str) -> str:
    """Return text with no diff marks at the start of a line and with single spaces."""
    lines = [re.sub(r"^[+\-]", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def keep(findings: list[dict], context: str) -> tuple[list[dict], int]:
    """Return the findings whose quote is in the context, and the number of deleted findings."""
    known = plain(context)
    kept = []
    for finding in findings:
        quote = plain(str(finding.get("quote", "")))
        if len(quote) >= MIN_QUOTE and quote in known:
            kept.append(finding)
    return kept, len(findings) - len(kept)


def render(answer: dict, context: str) -> str:
    """Return the comment as Markdown."""
    findings, deleted = keep(answer.get("findings", []), context)
    lines = [
        f"**Findings: {len(findings)}.** Deleted because the quote is not in the text: {deleted}.",
        "",
    ]
    for check in CHECKS:
        of_check = [finding for finding in findings if finding.get("check") == check]
        if of_check:
            lines += [f"#### {check}", ""]
        for finding in of_check:
            lines += [
                f"- **{finding.get('level', 'LOW')}** `{finding.get('file', '')}`",
                f"  > {plain(str(finding['quote']))}",
                f"  {finding.get('problem', '')} **Action:** {finding.get('action', '')}",
            ]
    for title, key in (
        ("Examined", "examined"),
        ("Weakest claim", "weakest_claim"),
        ("Test", "test"),
    ):
        lines += ["", f"**{title}.** {answer.get(key, '')}"]
    return "\n".join(lines) + "\n"


def main(response_path: str, context_path: str) -> None:
    """Print the comment for the answer in one file and the context in a second file."""
    context = Path(context_path).read_text()
    text = json.loads(Path(response_path).read_text())["choices"][0]["message"]["content"]
    try:
        print(render(json.loads(text), context))
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
        print("The model did not give the JSON form. Its answer, with no check of the quotes:\n")
        print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
