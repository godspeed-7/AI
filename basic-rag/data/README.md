# AMS HR sample data

Structured data about AMS employees, for future agent tools. The policy
documents in `../documents/policies/` say what the rules are; this data
says who the employees are and what they've done. Interesting questions
need both: "can Rahul take 6 days off?" needs his balance and probation
status (here) and the probation rule (policy).

Fictional, and consistent with the policies. **The data is as of
16 November 2026** (`TODAY` in the script); use that date, not the real
one, when reasoning about it.

Rebuild all four files (same output every time):

```bash
uv run python data/build_hr_data.py
```

The script checks every row against the policy rules before writing.

## Files

| File | Rows | One row per |
|---|---|---|
| `employees.csv` | 40 | employee (Bengaluru 19, Pune 11, Austin 10) |
| `leave_balances.csv` | 120 | employee × leave type, for 2026 |
| `leave_requests.csv` | 198 | leave request in 2026 |
| `expense_claims.csv` | 60 | expense item (several items make one trip) |

**employees.csv:** `employee_id`, `name`, `email`, `office`, `department`,
`grade` (L1–L6), `job_title`, `manager_id` (always L4+, empty for
directors), `join_date`, `status` (`probation`, `confirmed`,
`notice_period`), `probation_end_date`, `resignation_date`,
`last_working_day`. Payroll isn't stored: Bengaluru and Pune are India
payroll, Austin is US payroll.

**leave_balances.csv:** `employee_id`, `leave_year`, `leave_type`,
`entitled_days`, `carried_over_days`, `used_days`, `pending_days`.
India types: `annual`, `sick`, `casual`. US types: `pto`, `sick`,
`floating`. Available days = entitled + carried over − used − pending
(not stored, so it can't go out of sync).

**leave_requests.csv:** `request_id`, `employee_id`, `leave_type`,
`start_date`, `end_date`, `days` (working days, excluding weekends and
the office's holidays; 0.5 for a half day), `status` (`approved`,
`pending`, `rejected`, `cancelled`), `submitted_on`, `approver_id`.

**expense_claims.csv:** `claim_id`, `employee_id`, `trip_id`, `category`
(`hotel`, `daily_allowance`, `taxi`, `other`), `description`, `city`,
`nights`, `amount`, `currency` (INR for India payroll, USD for US),
`expense_date`, `submitted_on`, `receipt_attached`,
`lost_receipt_declaration`, `status` (`submitted`, `paid`),
`approver_id`.

## Assumptions where the policies are silent

- Only annual leave (India) and PTO (US) are prorated for 2026 joiners;
  sick, casual, and floating days are given in full.
- Carried-over days were used first and all of them before the
  carry-over deadline (31 March in India, 30 June in the US), so none
  have expired.
- Sick and casual leave is never booked ahead; future requests are
  all `pending`.
- Directors have no manager, so their requests have no approver.
- US "probation" means the 90-day introductory period.

## Scenarios (need data + policy together)

| Question | What the data says | What the policy says | Expected answer |
|---|---|---|---|
| Can Rahul Verma (AMS-1014) take 6 more annual days in December? | Pune, on probation until 2027-01-20; 3 annual days used, 2 pending | India: at most 5 annual days during probation (onboarding 4.4) | No: his 5 probation days are all used or requested; more after confirmation on 20 Jan 2027 |
| How many annual days can Ananya Iyer (AMS-1015) carry into 2027? | Bengaluru; 20 entitled + 5 carried, 18 used, 7 available | Up to 5 days, use by 31 March (India 4.1–4.2) | 5, to be used by 31 March 2027; the other 2 lapse unless taken in 2026 |
| How much PTO does Emily Carter (AMS-1031) get in 2026? | Austin, joined 2022-05-16 | 18 days after 3 completed years, from the next leave year (US 3.2) | 18 days (she has 12.5 left) |
| How much PTO does Michael Turner (AMS-1032) have? | Austin, joined 2026-09-14; 4.5 entitled, 2 used, 2 pending | Prorated for joiners (US 3.3); 90-day introductory period | 0.5 days left; introductory period ends 13 Dec 2026 |
| When is Karthik Subramanian's (AMS-1011) last working day? | Bengaluru L4, resigned 2026-10-26 | L4–L5 in India: 60 days, starting the day of resignation (onboarding 5.1–5.2) | 24 December 2026 |
| Will Emily's Dallas hotel (EXP-0001) be paid in full? | US$420 for 2 nights, L3, submitted 52 days after the stay | US$180/night for L1–L3; after 30 days, department-head approval (travel 5.2, 8.3) | No: at most US$360, and only with department-head approval |
| Will Siddharth's taxi claim (EXP-0003) be paid? | Submitted 104 days after the expense | Over 90 days: not reimbursed (travel 8.3) | No |
| Can Ritu's taxi claim without a receipt (EXP-0004) be paid? | INR 1,400, lost-receipt declaration, her first this year | Declaration allowed twice a year, up to INR 2,000 each (travel 8.5) | Yes |
| Will Varun's minibar claim (EXP-0005) be paid? | INR 1,200, "Hotel minibar" | Minibar charges aren't reimbursed (travel 9) | No |
| Is Manoj's Delhi hotel (EXP-0006) within limits? | INR 11,000 for 2 nights, L2, Delhi NCR (Tier A) | L1–L2, Tier A: INR 4,500/night (travel 5.1) | No: the limit is INR 9,000 for 2 nights |
| Can Emily Carter get a corporate card? | Grade L3 | L5 and above only (travel 11) | No |
