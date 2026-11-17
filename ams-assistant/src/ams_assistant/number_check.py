"""Invented numbers: the numbers in a reply that nothing the model saw
backs up (EVAL_PLAYBOOK.md, C6), for both evals.

In:  the reply, and everything the model saw as one text (question,
     instructions, tool results or handbook chunks).
Out: invented_numbers() -> the reply's unbacked numbers as written,
     e.g. ["9"]; [] when every number is backed.

Strategy: numbers are compared by value, each only with its own kind:
codes as text (LR-0199, L3, TRV-F-02, section 3.5.1), dates as month
and day (2026-02-09 = "9 February"), plain numbers (7.0 = 7, "USD
1,850" = 1850, "50%" = 50; a date's year is a plain number). Dates
apart, "9 days" can't match "joined 9 August". A plain number the text
lacks still counts if the reply works it out from two of its backed
numbers: + − × ÷ or a percentage (X3: 420 ÷ 2 = 210, 210 − 180 = 30).

Caveats:
- Digits only: "two weeks" or "half" aren't checked.
- A real number in the wrong place passes (sick and casual swapped);
  with many numbers about, a made-up one can equal a sum by chance.
- A score for a person to read, not a gate: it can misfire.
"""

import re
from itertools import permutations

MONTHS = {name: number
          for number, names in enumerate((
              "January Jan", "February Feb", "March Mar", "April Apr",
              "May", "June Jun", "July Jul", "August Aug",
              "September Sept Sep", "October Oct", "November Nov",
              "December Dec"), start=1)
          for name in names.split()}
# Capitalised only, so the verb "may" isn't a month.
MONTH = ("(?P<month>" + "|".join(sorted(MONTHS, key=len, reverse=True))
         + r")\b")
DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
YEAR = r"(?:,?\s+(?P<year>\d{4})\b)?"

# Codes: letters then digits (AMS-1015, LR-0199, TRV-F-02, L3) or a
# section with two dots or more (3.5.1).
CODE = re.compile(r"\b(?:[A-Za-z]+-)*[A-Za-z]+-?\d+(?:-\d+)*\b"
                  r"|\b\d+(?:\.\d+){2,}\b")
DATES = [
    re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b"),
    # "3-4 December", "3 to 5 December 2026": two dates, one month.
    re.compile(rf"\b{DAY}\s*(?:-|–|to|and)\s*(?P<day2>\d{{1,2}})"
               rf"(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH}{YEAR}"),
    re.compile(rf"\b{DAY}\s+(?:of\s+)?{MONTH}{YEAR}"),
    re.compile(rf"\b{MONTH}\.?\s+{DAY}\b{YEAR}"),  # "Dec. 4"
]
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
                    r"(?:st|nd|rd|th)?(?!\w)")


def find_numbers(text: str) -> tuple[list[str], list[tuple], list[tuple]]:
    """The numbers in `text`, by kind: codes (upper case), dates as
    (as written, (month, day)) and plain numbers as (as written,
    value). Each piece found is blanked out, so it counts once."""
    codes = [match.group().upper() for match in CODE.finditer(text)]
    text = CODE.sub(" ", text)
    dates, numbers = [], []
    for pattern in DATES:
        for match in pattern.finditer(text):
            month = match["month"]
            month = int(month) if month.isdigit() else MONTHS[month]
            days = [match["day"]]
            if "day2" in pattern.groupindex:
                days.append(match["day2"])
            dates += [(match.group(), (month, int(day))) for day in days]
            if match["year"]:
                numbers.append((match["year"], float(match["year"])))
        text = pattern.sub(" ", text)
    numbers += [(match.group(),
                 float(match[1].replace(",", "")
                       + (f".{match[2]}" if match[2] else "")))
                for match in NUMBER.finditer(text)]
    return codes, dates, numbers


def worked_out(value: float, backed: set[float]) -> bool:
    """Is `value` one step of maths on two other backed numbers?"""
    for a, b in permutations(backed, 2):
        results = [a + b, a - b, a * b, a * b / 100]
        if b:
            results.append(a / b)
        if any(abs(result - value) < 0.01 for result in results):
            return True
    return False


def invented_numbers(reply: str, seen: str) -> list[str]:
    """The reply's numbers (as written) that `seen` doesn't back: not
    in it, and for a plain number not worked out in the reply from
    backed ones either."""
    seen_codes, seen_dates, seen_numbers = find_numbers(seen)
    seen_days = {date for _, date in seen_dates}
    seen_values = {round(value, 2) for _, value in seen_numbers}
    codes, dates, numbers = find_numbers(reply)

    invented = [code for code in codes if code not in seen_codes]
    invented += [text for text, date in dates if date not in seen_days]
    backed = {value for _, value in numbers
              if round(value, 2) in seen_values}
    left = [(text, value) for text, value in numbers
            if round(value, 2) not in seen_values]
    # A worked-out number can be used in the next step (X3: 210, then
    # 210 − 180 = 30), so go round until nothing new is backed.
    while new := [(text, value) for text, value in left
                  if worked_out(value, backed)]:
        backed.update(value for _, value in new)
        left = [item for item in left if item not in new]
    invented += [text for text, _ in left]
    return list(dict.fromkeys(invented))
