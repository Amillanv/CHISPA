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
    """Return text with single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def plain_quote(text: str) -> str:
    """Return a quote in the form of a known line.

    A model frequently copies the "+" at the start of a diff line, and it changes straight
    quote marks to curved quote marks. The two changes do not make a quote wrong.
    """
    marks = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
    return plain(re.sub(r"^\s*\+", "", text.translate(marks)))


def known_lines(context: str) -> list[str]:
    """Return each line that a quote can come from.

    In the diff, that is a line that the pull request adds or keeps. A deleted line is not in
    the head of the pull request, thus it is not a line to review. A document gives all lines.
    """
    lines, in_diff = [], False
    for line in context.splitlines():
        if line.startswith("<<<"):
            in_diff = line.startswith("<<<DIFF")
        elif not in_diff:
            lines.append(plain(line))
        elif not line.startswith(("-", "+++", "@@", "diff ", "index ")):
            lines.append(plain(line[1:]))
    return lines


def keep(findings: list[dict], context: str) -> tuple[list[dict], int]:
    """Return the findings whose quote is in one known line, and the number of deleted findings."""
    lines = known_lines(context)
    kept = []
    for finding in findings:
        quote = plain_quote(str(finding.get("quote", "")))
        if len(quote) >= MIN_QUOTE and any(quote in line for line in lines):
            kept.append(finding)
        else:
            # The log of the workflow shows what was deleted. The comment does not.
            print(f"deleted: {finding.get('file', '')}: {quote[:200]}", file=sys.stderr)
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
                f"  > {plain_quote(str(finding['quote']))}",
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
        # We do not show an answer that the quote check did not read.
        print("The model did not give the JSON form. There is no review. Run the workflow again.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
