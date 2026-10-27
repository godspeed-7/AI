"""Build the AMS HR sample data as CSV files (for future agent tools).

In:  the rules in ../policies/ (entitlements, probation, expense
     limits) and the holiday dates in holiday_calendar_2026.txt.
Out: four CSV files in this folder:
       employees.csv       40 employees in Bengaluru, Pune, and Austin
       leave_balances.csv  2026 entitlement, carry-over, used, pending
       leave_requests.csv  every 2026 leave request
       expense_claims.csv  expense items from business trips

Strategy: a few hand-written "scenario" rows that need data + policy
together to answer (see README.md), plus generated rows with a fixed
random seed, so every run produces the same files. TODAY is fixed, so
"on probation" or "52 days late" never changes. validate() checks every
row against the policy rules before anything is written.

Caveats:
- Fictional data. Where the policies are silent, the assumptions are
  listed in README.md (e.g. sick and casual leave aren't prorated).
- Re-running overwrites the four CSV files.
"""

import csv
import random
import re
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
HOLIDAY_FILE = DATA_DIR.parent / "policies" / "holiday_calendar_2026.txt"

# The fixed "current date" the data describes.
TODAY = date(2026, 11, 16)
YEAR = 2026
SEED = 42

INDIA_OFFICES = {"Bengaluru", "Pune"}

# --- Employees ----------------------------------------------------------
# id, name, office, department, grade, job title, manager, joined.
# Resignation date is set only for the employee serving notice.
EMPLOYEES = [
    ("AMS-1001", "Priya Nair", "Bengaluru", "Engineering", "L6",
     "Director", "", "2016-03-01"),
    ("AMS-1002", "Arjun Mehta", "Bengaluru", "Delivery", "L6",
     "Director", "", "2015-07-13"),
    ("AMS-1003", "Sarah Mitchell", "Austin", "Sales", "L6",
     "Director", "", "2017-02-06"),
    ("AMS-1004", "Kavita Rao", "Bengaluru", "Finance", "L6",
     "Director", "", "2018-01-08"),
    ("AMS-1005", "Neha Kulkarni", "Pune", "People Operations", "L6",
     "Director", "", "2019-04-01"),
    ("AMS-1006", "Vikram Desai", "Pune", "IT and Security", "L6",
     "Director", "", "2017-09-18"),
    ("AMS-1007", "Sanjay Gupta", "Bengaluru", "Engineering", "L5",
     "Manager", "AMS-1001", "2018-06-04"),
    ("AMS-1008", "Daniel Brooks", "Austin", "Engineering", "L5",
     "Principal", "AMS-1001", "2019-10-14"),
    ("AMS-1009", "Meera Joshi", "Pune", "Engineering", "L5",
     "Manager", "AMS-1001", "2020-02-17"),
    ("AMS-1010", "Rohan Kapoor", "Bengaluru", "Delivery", "L5",
     "Manager", "AMS-1002", "2019-08-05"),
    ("AMS-1011", "Karthik Subramanian", "Bengaluru", "Engineering", "L4",
     "Team Lead", "AMS-1007", "2021-03-15"),
    ("AMS-1012", "Pooja Shetty", "Bengaluru", "Engineering", "L4",
     "Team Lead", "AMS-1007", "2020-11-02"),
    ("AMS-1013", "Amit Patil", "Pune", "Engineering", "L4",
     "Team Lead", "AMS-1009", "2021-06-21"),
    ("AMS-1014", "Rahul Verma", "Pune", "Engineering", "L2",
     "Engineer", "AMS-1009", "2026-07-20"),
    ("AMS-1015", "Ananya Iyer", "Bengaluru", "Engineering", "L3",
     "Senior Engineer", "AMS-1012", "2021-08-09"),
    ("AMS-1016", "Siddharth Menon", "Bengaluru", "Engineering", "L2",
     "Engineer", "AMS-1012", "2023-01-16"),
    ("AMS-1017", "Divya Reddy", "Bengaluru", "Engineering", "L1",
     "Associate", "AMS-1011", "2025-07-07"),
    ("AMS-1018", "Harish Kumar", "Bengaluru", "Engineering", "L3",
     "Senior Engineer", "AMS-1011", "2019-05-20"),
    ("AMS-1019", "Sneha Pillai", "Bengaluru", "Delivery", "L4",
     "Team Lead", "AMS-1010", "2020-09-07"),
    ("AMS-1020", "Manoj Tiwari", "Bengaluru", "Delivery", "L2",
     "Analyst", "AMS-1019", "2024-02-12"),
    ("AMS-1021", "Lakshmi Krishnan", "Bengaluru", "Delivery", "L3",
     "Senior Analyst", "AMS-1019", "2022-10-03"),
    ("AMS-1022", "Farhan Sheikh", "Bengaluru", "Finance", "L4",
     "Team Lead", "AMS-1004", "2020-01-20"),
    ("AMS-1023", "Ritu Agarwal", "Bengaluru", "Finance", "L2",
     "Analyst", "AMS-1022", "2024-08-19"),
    ("AMS-1024", "Nikhil Bhat", "Pune", "Engineering", "L3",
     "Senior Engineer", "AMS-1013", "2022-04-11"),
    ("AMS-1025", "Swati Deshmukh", "Pune", "Engineering", "L1",
     "Associate", "AMS-1013", "2026-06-01"),
    ("AMS-1026", "Omkar Jadhav", "Pune", "Delivery", "L2",
     "Analyst", "AMS-1010", "2023-07-03"),
    ("AMS-1027", "Shruti Pawar", "Pune", "People Operations", "L3",
     "Senior Analyst", "AMS-1005", "2021-11-22"),
    ("AMS-1028", "Jennifer Walsh", "Austin", "Sales", "L5",
     "Manager", "AMS-1003", "2018-04-23"),
    ("AMS-1029", "Kevin Nguyen", "Austin", "Sales", "L4",
     "Team Lead", "AMS-1028", "2020-08-31"),
    ("AMS-1030", "Ashley Ramirez", "Austin", "Sales", "L2",
     "Analyst", "AMS-1029", "2024-03-18"),
    ("AMS-1031", "Emily Carter", "Austin", "Sales", "L3",
     "Senior Analyst", "AMS-1028", "2022-05-16"),
    ("AMS-1032", "Michael Turner", "Austin", "Engineering", "L2",
     "Engineer", "AMS-1008", "2026-09-14"),
    ("AMS-1033", "Brian Foster", "Austin", "Engineering", "L3",
     "Senior Engineer", "AMS-1008", "2019-06-10"),
    ("AMS-1034", "Rachel Kim", "Austin", "Engineering", "L4",
     "Team Lead", "AMS-1008", "2021-01-11"),
    ("AMS-1035", "Tyler Morgan", "Austin", "Delivery", "L3",
     "Senior Analyst", "AMS-1002", "2023-09-05"),
    ("AMS-1036", "Abhishek Singh", "Pune", "IT and Security", "L4",
     "Team Lead", "AMS-1006", "2020-03-09"),
    ("AMS-1037", "Pallavi Ghosh", "Pune", "IT and Security", "L2",
     "Engineer", "AMS-1036", "2025-01-13"),
    ("AMS-1038", "Suresh Naidu", "Bengaluru", "IT and Security", "L3",
     "Senior Engineer", "AMS-1036", "2018-12-03"),
    ("AMS-1039", "Aditi Saxena", "Bengaluru", "People Operations", "L4",
     "Team Lead", "AMS-1005", "2021-05-03"),
    ("AMS-1040", "Varun Malhotra", "Bengaluru", "Sales", "L3",
     "Senior Analyst", "AMS-1003", "2022-07-25"),
]

# Scenario: Karthik resigned on 26 Oct; L4 in India -> 60 days' notice,
# counted from the day the resignation is submitted.
RESIGNATIONS = {"AMS-1011": date(2026, 10, 26)}
NOTICE_DAYS_INDIA = {"L1": 30, "L2": 30, "L3": 30, "L4": 60, "L5": 60,
                     "L6": 90}

# --- Policy rules used to build and check the data -----------------------
INDIA_ENTITLEMENT = {"annual": 20, "sick": 10, "casual": 6}
US_ENTITLEMENT = {"sick": 5, "floating": 2}  # PTO depends on service
MAX_CARRY_OVER = {"annual": 5, "pto": 10}
CARRY_OVER_DEADLINE = {"annual": date(YEAR, 3, 31),
                       "pto": date(YEAR, 6, 30)}
PROBATION_ANNUAL_LIMIT = 5  # India: annual days usable during probation

# Expense limits by grade band (travel_expense_policy.txt).
INDIA_HOTEL = {"low": {"A": 4500, "B": 3000}, "mid": {"A": 6500, "B": 4500},
               "high": {"A": 9000, "B": 6000}}
INDIA_DA = {"low": {"A": 1200, "B": 900}, "mid": {"A": 1800, "B": 1300},
            "high": {"A": 2500, "B": 1800}}
TIER_A_CITIES = {"Bengaluru", "Chennai", "Delhi NCR", "Hyderabad",
                 "Kolkata", "Mumbai", "Pune"}
INDIA_TRIP_CITIES = ["Mumbai", "Delhi NCR", "Hyderabad", "Chennai",
                     "Mysuru", "Coimbatore", "Nagpur", "Bengaluru", "Pune"]
US_TRIP_CITIES = ["Dallas", "Houston", "New York", "Chicago"]
# The first claims are hand-written scenarios that break rules.
SCENARIO_CLAIMS = 6


def india_band(grade: str) -> str:
    """Grade band used by the India expense tables."""
    return {"L1": "low", "L2": "low", "L3": "mid", "L4": "mid",
            "L5": "high", "L6": "high"}[grade]


def us_hotel_limit(grade: str) -> int:
    return 180 if grade in ("L1", "L2", "L3") else 250


def us_daily_allowance(grade: str) -> int:
    return 60 if grade in ("L1", "L2", "L3") else 75


# --- Helpers -------------------------------------------------------------
def load_holidays() -> dict[str, set[date]]:
    """Read each office's fixed holidays from the holiday calendar."""
    sections = {"Bengaluru": "3.1", "Pune": "4.1", "Austin": "6.1"}
    lines = HOLIDAY_FILE.read_text(encoding="utf-8").splitlines()
    holidays = {}

    for office, section in sections.items():
        start = next(i for i, line in enumerate(lines)
                     if line.startswith(f"{section} "))
        dates = set()
        for line in lines[start + 1:]:
            match = re.search(r"\| (\d{1,2} \w+ \d{4}) \|", line)
            if match:
                dates.add(_parse_date(match.group(1)))
            elif re.match(r"\d+\.\d* ", line):
                break  # next section
        holidays[office] = dates

    return holidays


def _parse_date(text: str) -> date:
    from datetime import datetime
    return datetime.strptime(text, "%d %B %Y").date()


def working_days(start: date, end: date, holidays: set[date]) -> list:
    """Weekdays from start to end (inclusive) that aren't holidays."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days


def prorate(entitlement: int, joined: date) -> float:
    """Entitlement for the rest of the year, to the nearest half day."""
    if joined <= date(YEAR, 1, 1):
        return float(entitlement)
    remaining = (date(YEAR, 12, 31) - joined).days + 1
    return round(entitlement * remaining / 365 * 2) / 2


def us_pto(joined: date) -> float:
    """15 days; 18 after 3 and 20 after 5 completed years. The increase
    applies from the leave year after the anniversary."""
    years_by_last_year_end = (date(YEAR - 1, 12, 31) - joined).days / 365.25
    if years_by_last_year_end >= 5:
        return 20.0
    if years_by_last_year_end >= 3:
        return 18.0
    return prorate(15, joined)


def entitlement(emp: dict, leave_type: str) -> float:
    """Days of this leave type the employee gets in YEAR."""
    joined = date.fromisoformat(emp["join_date"])
    if leave_type == "pto":
        return us_pto(joined)
    if emp["office"] in INDIA_OFFICES:
        if leave_type == "annual":
            return prorate(INDIA_ENTITLEMENT["annual"], joined)
        return float(INDIA_ENTITLEMENT[leave_type])
    return float(US_ENTITLEMENT[leave_type])


def employee_status(office: str, joined: date, emp_id: str) -> str:
    if emp_id in RESIGNATIONS:
        return "notice_period"
    probation_end = probation_end_date(office, joined)
    return "probation" if probation_end > TODAY else "confirmed"


def probation_end_date(office: str, joined: date) -> date:
    """India: 6 months. US: a 90-day introductory period."""
    if office in INDIA_OFFICES:
        month = joined.month + 6
        year = joined.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, joined.day)
    return joined + timedelta(days=90)


def leave_types(office: str) -> list[str]:
    if office in INDIA_OFFICES:
        return ["annual", "sick", "casual"]
    return ["pto", "sick", "floating"]


# --- Builders ------------------------------------------------------------
def build_employees() -> list[dict]:
    rows = []
    for (emp_id, name, office, dept, grade, title, manager,
         joined) in EMPLOYEES:
        joined_date = date.fromisoformat(joined)
        resigned = RESIGNATIONS.get(emp_id)
        last_day = ""
        if resigned:
            notice = NOTICE_DAYS_INDIA[grade]
            last_day = (resigned + timedelta(days=notice - 1)).isoformat()
        first, last = name.lower().split(" ", 1)
        rows.append({
            "employee_id": emp_id,
            "name": name,
            "email": f"{first}.{last.replace(' ', '')}@ams.example",
            "office": office,
            "department": dept,
            "grade": grade,
            "job_title": title,
            "manager_id": manager,
            "join_date": joined,
            "status": employee_status(office, joined_date, emp_id),
            "probation_end_date": probation_end_date(
                office, joined_date).isoformat(),
            "resignation_date": resigned.isoformat() if resigned else "",
            "last_working_day": last_day,
        })
    return rows


class RequestBuilder:
    """Creates non-overlapping leave requests on working days."""

    def __init__(self, holidays: dict[str, set[date]]):
        self.holidays = holidays
        self.requests = []
        self.taken = {}  # employee_id -> set of dates already requested

    def add(self, emp: dict, leave_type: str, start: date, end: date,
            status: str, submitted: date, half_day: bool = False) -> bool:
        office_holidays = self.holidays[emp["office"]]
        days = working_days(start, end, office_holidays)
        taken = self.taken.setdefault(emp["employee_id"], set())
        if not days or taken.intersection(days):
            return False
        taken.update(days)
        self.requests.append({
            "employee_id": emp["employee_id"],
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": 0.5 if half_day else float(len(days)),
            "status": status,
            "submitted_on": submitted.isoformat(),
            "approver_id": emp["manager_id"],
        })
        return True


def add_scenario_requests(builder: RequestBuilder, emps: dict):
    """Hand-written requests behind the README scenarios."""
    d = date
    rahul = emps["AMS-1014"]  # probation: 3 used + 2 pending = 5
    builder.add(rahul, "annual", d(2026, 9, 10), d(2026, 9, 11),
                "approved", d(2026, 8, 25))
    builder.add(rahul, "annual", d(2026, 10, 9), d(2026, 10, 9),
                "approved", d(2026, 9, 24))
    builder.add(rahul, "annual", d(2026, 12, 3), d(2026, 12, 4),
                "pending", d(2026, 11, 13))
    builder.add(rahul, "sick", d(2026, 8, 18), d(2026, 8, 18),
                "approved", d(2026, 8, 18))

    ananya = emps["AMS-1015"]  # 20 + 5 carried, 18 used, 0 pending
    for start, end, submitted in [
        (d(2026, 2, 9), d(2026, 2, 13), d(2026, 1, 20)),    # 5 days
        (d(2026, 3, 23), d(2026, 3, 25), d(2026, 3, 5)),    # 3 days
        (d(2026, 5, 18), d(2026, 5, 22), d(2026, 4, 27)),   # 5 days
        (d(2026, 8, 10), d(2026, 8, 14), d(2026, 7, 20)),   # 5 days
    ]:
        builder.add(ananya, "annual", start, end, "approved", submitted)

    emily = emps["AMS-1031"]  # PTO 18 + 6 carried, 11.5 used
    for start, end, submitted, half in [
        (d(2026, 3, 9), d(2026, 3, 13), d(2026, 2, 9), False),   # 5
        (d(2026, 6, 22), d(2026, 6, 23), d(2026, 6, 8), False),  # 2
        (d(2026, 8, 10), d(2026, 8, 13), d(2026, 7, 13), False),  # 4
        (d(2026, 10, 30), d(2026, 10, 30), d(2026, 10, 16), True),
    ]:
        builder.add(emily, "pto", start, end, "approved", submitted, half)


def add_generated_requests(builder: RequestBuilder, employees: list,
                           rng: random.Random):
    """Random but rule-respecting requests for everyone else."""
    scenario_ids = {"AMS-1014", "AMS-1015", "AMS-1031"}
    year_start, year_end = date(YEAR, 1, 5), date(YEAR, 12, 18)

    for emp in employees:
        if emp["employee_id"] in scenario_ids:
            continue
        joined = date.fromisoformat(emp["join_date"])
        earliest = max(year_start, joined + timedelta(days=14))
        india = emp["office"] in INDIA_OFFICES
        main_type = "annual" if india else "pto"
        notice_from = RESIGNATIONS.get(emp["employee_id"])

        plan = [(main_type, rng.randint(2, 5), (1, 5))]
        plan.append(("sick", rng.randint(0, 2), (1, 2)))
        plan.append(("casual" if india else "floating",
                     rng.randint(0, 2), (1, 1)))

        # Never request more than the year's entitlement (carry-over is
        # decided later, so it isn't counted on). Probation in India:
        # at most 5 annual days in total.
        probation = emp["status"] == "probation" and india

        for leave_type, count, (low, high) in plan:
            budget = entitlement(emp, leave_type)
            if leave_type == "annual" and probation:
                budget = min(budget, PROBATION_ANNUAL_LIMIT)
            for _ in range(count * 4):  # retries for overlaps/holidays
                if count == 0:
                    break
                span = (year_end - earliest).days
                if span <= 0:
                    break
                start = earliest + timedelta(days=rng.randint(0, span))
                length = rng.randint(low, high)
                end = start + timedelta(days=length - 1)
                if end.year != YEAR:
                    continue
                unplanned = leave_type in ("sick", "casual")
                future = start >= TODAY
                if unplanned and future:
                    continue  # sick/casual leave isn't booked ahead
                if notice_from and start >= notice_from:
                    continue  # no new leave during the notice period
                days = len(working_days(
                    start, end, builder.holidays[emp["office"]]))
                if days > budget:
                    continue

                status, submitted = _status_and_submitted(
                    start, unplanned, joined, rng)

                if builder.add(emp, leave_type, start, end, status,
                               submitted):
                    if status in ("approved", "pending"):
                        budget -= days
                    count -= 1


def _status_and_submitted(start: date, unplanned: bool, joined: date,
                          rng: random.Random) -> tuple[str, date]:
    """Future requests are pending; unplanned (sick/casual) ones are
    submitted on the day; planned past ones were mostly approved."""
    if start >= TODAY:
        status = "pending"
        submitted = TODAY - timedelta(days=rng.randint(1, 12))
    elif unplanned:
        status = "approved"
        submitted = start
    else:
        status = rng.choices(["approved", "rejected", "cancelled"],
                             weights=[90, 5, 5])[0]
        submitted = start - timedelta(days=rng.randint(10, 30))
    return status, max(submitted, joined)


def build_balances(employees: list, requests: list,
                   rng: random.Random) -> list[dict]:
    """Derive 2026 balances from the requests.

    used = approved days; pending = days awaiting approval. Carried-over
    days are used first and never more than were used before the
    carry-over deadline, so none of them have expired.
    """
    forced_carry = {("AMS-1015", "annual"): 5.0, ("AMS-1031", "pto"): 6.0}
    rows = []

    for emp in employees:
        joined = date.fromisoformat(emp["join_date"])
        for leave_type in leave_types(emp["office"]):
            entitled = entitlement(emp, leave_type)

            mine = [r for r in requests
                    if r["employee_id"] == emp["employee_id"]
                    and r["leave_type"] == leave_type]
            used = sum(r["days"] for r in mine if r["status"] == "approved")
            pending = sum(r["days"] for r in mine
                          if r["status"] == "pending")

            carried = 0.0
            if leave_type in MAX_CARRY_OVER and joined.year < YEAR:
                deadline = CARRY_OVER_DEADLINE[leave_type]
                used_by_deadline = sum(
                    r["days"] for r in mine if r["status"] == "approved"
                    and date.fromisoformat(r["start_date"]) <= deadline)
                key = (emp["employee_id"], leave_type)
                if key in forced_carry:
                    carried = forced_carry[key]
                else:
                    cap = min(MAX_CARRY_OVER[leave_type], used_by_deadline)
                    carried = float(rng.randint(0, int(cap)))

            rows.append({
                "employee_id": emp["employee_id"],
                "leave_year": YEAR,
                "leave_type": leave_type,
                "entitled_days": entitled,
                "carried_over_days": carried,
                "used_days": used,
                "pending_days": pending,
            })
    return rows


def build_claims(employees: list, rng: random.Random) -> list[dict]:
    """Scenario claims first (EXP-0001..), then generated trips."""
    emps = {e["employee_id"]: e for e in employees}
    claims = []

    def add(emp_id, trip, category, description, city, nights, amount,
            expense_date, submitted, receipt="yes", lost="no",
            status=None):
        emp = emps[emp_id]
        currency = "INR" if emp["office"] in INDIA_OFFICES else "USD"
        if status is None:
            age = (TODAY - submitted).days
            status = ("paid" if age > 20 else
                      "approved" if age > 7 else "submitted")
        claims.append({
            "claim_id": f"EXP-{len(claims) + 1:04d}",
            "employee_id": emp_id,
            "trip_id": trip,
            "category": category,
            "description": description,
            "city": city,
            "nights": nights,
            "amount": amount,
            "currency": currency,
            "expense_date": expense_date.isoformat(),
            "submitted_on": submitted.isoformat(),
            "receipt_attached": receipt,
            "lost_receipt_declaration": lost,
            "status": status,
            "approver_id": emp["manager_id"],
        })

    d = date
    # EXP-0001/0002: Emily, Dallas, hotel above the L3 cap, 52 days late.
    add("AMS-1031", "TRIP-001", "hotel", "Hotel, 2 nights", "Dallas", 2,
        420.00, d(2026, 9, 21), d(2026, 11, 12), status="submitted")
    add("AMS-1031", "TRIP-001", "daily_allowance", "Daily allowance, "
        "3 days", "Dallas", "", 180.00, d(2026, 9, 21), d(2026, 11, 12),
        receipt="no", status="submitted")
    # EXP-0003: Siddharth, taxi, submitted 104 days after the expense.
    add("AMS-1016", "TRIP-002", "taxi", "Airport taxi", "Mumbai", "",
        1850.00, d(2026, 7, 28), d(2026, 11, 9), status="submitted")
    # EXP-0004: Ritu, taxi with a lost receipt (declaration).
    add("AMS-1023", "TRIP-003", "taxi", "Taxi to client office",
        "Hyderabad", "", 1400.00, d(2026, 10, 20), d(2026, 10, 28),
        receipt="no", lost="yes", status="submitted")
    # EXP-0005: Varun, hotel minibar (not reimbursable).
    add("AMS-1040", "TRIP-004", "other", "Hotel minibar", "Mumbai", "",
        1200.00, d(2026, 11, 5), d(2026, 11, 10), status="submitted")
    # EXP-0006: Manoj (L2), Delhi NCR hotel above the Tier A cap.
    add("AMS-1020", "TRIP-005", "hotel", "Hotel, 2 nights", "Delhi NCR",
        2, 11000.00, d(2026, 10, 14), d(2026, 10, 22), status="submitted")

    # Generated trips: within limits and on time.
    travellers = [e for e in employees if e["status"] != "probation"]
    for trip_no in range(6, 24):
        emp = rng.choice(travellers)
        india = emp["office"] in INDIA_OFFICES
        cities = [c for c in (INDIA_TRIP_CITIES if india else
                              US_TRIP_CITIES) if c != emp["office"]]
        city = rng.choice(cities)
        nights = rng.randint(1, 3)
        start = d(YEAR, 2, 2) + timedelta(days=rng.randint(0, 250))
        end = start + timedelta(days=nights)
        submitted = end + timedelta(days=rng.randint(2, 20))
        if submitted > TODAY:
            continue
        trip = f"TRIP-{trip_no:03d}"

        if india:
            tier = "A" if city in TIER_A_CITIES else "B"
            band = india_band(emp["grade"])
            rate = INDIA_HOTEL[band][tier]
            nightly = rng.randrange(int(rate * 0.6), rate + 1, 50)
            da = INDIA_DA[band][tier]
            taxi = float(rng.randrange(300, 1600, 10))
        else:
            rate = us_hotel_limit(emp["grade"])
            nightly = rng.randint(int(rate * 0.6), rate)
            da = us_daily_allowance(emp["grade"])
            taxi = float(rng.randint(18, 85))

        add(emp["employee_id"], trip, "hotel", f"Hotel, {nights} "
            f"night{'s' if nights > 1 else ''}", city, nights,
            float(nightly * nights), end, submitted)
        add(emp["employee_id"], trip, "daily_allowance", "Daily "
            f"allowance, {nights + 1} days", city, "",
            float(da * (nights + 1)), end, submitted, receipt="no")
        threshold = 500 if india else 25
        add(emp["employee_id"], trip, "taxi", "Taxi", city, "", taxi,
            start, submitted,
            receipt="yes" if taxi > threshold else rng.choice(
                ["yes", "no"]))

    return claims


# --- Checks --------------------------------------------------------------
def validate(employees, balances, requests, claims):
    """Fail loudly if any generated row breaks a policy rule."""
    emps = {e["employee_id"]: e for e in employees}

    for e in employees:
        manager = e["manager_id"]
        assert not manager or emps[manager]["grade"] in ("L4", "L5", "L6"), \
            f"{e['employee_id']}: manager below L4"
        assert e["grade"] == "L6" or manager, f"{e['employee_id']}: no manager"

    for b in balances:
        e = emps[b["employee_id"]]
        assert b["leave_type"] in leave_types(e["office"]), b
        if b["leave_type"] in MAX_CARRY_OVER:
            assert b["carried_over_days"] <= MAX_CARRY_OVER[b["leave_type"]]
            assert b["carried_over_days"] <= b["used_days"], b
        available = (b["entitled_days"] + b["carried_over_days"]
                     - b["used_days"] - b["pending_days"])
        assert available >= 0, f"overdrawn: {b}"
        if (e["status"] == "probation" and b["leave_type"] == "annual"):
            assert b["used_days"] + b["pending_days"] <= 5, b

    for r in requests:
        e = emps[r["employee_id"]]
        assert r["start_date"] >= e["join_date"], r
        if r["status"] == "pending":
            assert r["start_date"] >= TODAY.isoformat(), r

    # Scenario claims (EXP-0001 to EXP-0006) break rules on purpose;
    # every generated claim must be within limits and on time.
    for c in claims[SCENARIO_CLAIMS:]:
        e = emps[c["employee_id"]]
        late = (date.fromisoformat(c["submitted_on"])
                - date.fromisoformat(c["expense_date"])).days
        assert late <= 30, c
        if c["category"] == "hotel":
            per_night = c["amount"] / c["nights"]
            if c["currency"] == "INR":
                tier = "A" if c["city"] in TIER_A_CITIES else "B"
                cap = INDIA_HOTEL[india_band(e["grade"])][tier]
            else:
                cap = us_hotel_limit(e["grade"])
            assert per_night <= cap, c
        threshold = 500 if c["currency"] == "INR" else 25
        if c["category"] != "daily_allowance" and c["amount"] > threshold:
            assert c["receipt_attached"] == "yes", c

    print("All policy checks passed.")


def write_csv(name: str, rows: list[dict]):
    path = DATA_DIR / name
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name:<20} {len(rows):>4} rows")


def main():
    rng = random.Random(SEED)
    holidays = load_holidays()

    employees = build_employees()
    emps = {e["employee_id"]: e for e in employees}

    builder = RequestBuilder(holidays)
    add_scenario_requests(builder, emps)
    add_generated_requests(builder, employees, rng)
    requests = sorted(builder.requests,
                      key=lambda r: (r["start_date"], r["employee_id"]))
    for number, request in enumerate(requests, start=1):
        request["request_id"] = f"LR-{number:04d}"
    requests = [{"request_id": r.pop("request_id"), **r} for r in requests]

    balances = build_balances(employees, requests, rng)
    claims = build_claims(employees, rng)

    validate(employees, balances, requests, claims)

    print(f"Writing data as of {TODAY} to {DATA_DIR}:")
    write_csv("employees.csv", employees)
    write_csv("leave_balances.csv", balances)
    write_csv("leave_requests.csv", requests)
    write_csv("expense_claims.csv", claims)


if __name__ == "__main__":
    main()
