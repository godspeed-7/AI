# AMS HR sample data

Structured data about AMS employees, for the agent's tools. The policy
documents in `../policies/` say what the rules are; this data
says who the employees are and what they've done. Interesting questions
need both: "can Rahul take 6 days off?" needs his balance and probation
status (here) and the probation rule (policy).

Fictional, and consistent with the policies. **The data is as of
16 November 2026** (`TODAY` in the script); use that date, not the real
one, when reasoning about it.

Rebuild all twelve files (same output every time), from `ams-data/`:

```bash
uv run python db/build_hr_data.py                  # 1,200 employees
uv run python db/build_hr_data.py --employees 40   # the original 40 only
```

The script checks every row against the policy rules before writing.
Then rebuild the agent's database: `uv run python build_hr_db.py` in
`ams-assistant/`.

## The company

- **The original 40** (AMS-1001 to AMS-1040): written by hand; the
  scenarios below are about them. Their rows and IDs never change,
  whatever the size: they are built first, with their own seed.
- **The other 1,160** (AMS-1041 to AMS-2200, numbered in joining
  order): generated with the same rules and their own seed. Each
  department grows under its director, office by office: managers (L5)
  → team leads (L4) → teams of 6–8 (L1–L3), a team in its manager's
  office. New people never report to one of the 40 below
  director, so those teams are unchanged; only the 6 directors have
  more direct reports.
- Their requests, claims and trips are numbered after the original ones
  (LR-0199, EXP-0061, TRIP-024 onwards).
- Names are random pairs of common first and last names: Indian in
  India, American in Austin. Every name is unique (no "which Rahul?").

The offices are the handbook's (Employee 2.2.1): Bengaluru, the
headquarters, about 700; Pune, the Delivery centre, about 350; Austin,
the client office, about 150.

| Department | People | Bengaluru · Pune · Austin |
|---|---|---|
| Engineering | 672 | 508 · 112 · 52 |
| Delivery | 312 | 90 · 199 · 23 |
| Sales | 96 | 34 · 0 · 62 |
| IT and Security | 60 | 25 · 30 · 5 |
| People Operations | 30 | 16 · 9 · 5 |
| Finance | 30 | 27 · 0 · 3 |
| **All** | **1,200** | **700 · 350 · 150** |

## Files

| File | Rows | One row per |
|---|---|---|
| `employees.csv` | 1,200 | employee (Bengaluru 700, Pune 350, Austin 150) |
| `leave_balances.csv` | 3,600 | employee × leave type, for 2026 |
| `leave_requests.csv` | 6,354 | leave request in 2026 |
| `expense_claims.csv` | 1,599 | expense item (several items make one trip) |
| `employee_private.csv` | 1,200 | employee: personal data (sensitive) |
| `assets.csv` | 6,461 | IT device, current or past (laptops, accessories, on-call phones) |
| `servicedesk_tickets.csv` | 370 | ServiceDesk ticket (hardware and lost devices), since 1 Jan 2025 |
| `trainings.csv` | 8,844 | mandatory training assigned in AMS Learn, since 1 Jan 2025 |
| `salaries.csv` | 3,184 | pay change (joining or a 1 July raise), from the pay in effect on 1 Jan 2025 (sensitive) |
| `ratings.csv` | 2,047 | April performance rating, 2025 and 2026 |
| `projects.csv` | 64 | client or internal project (50 running today) |
| `project_assignments.csv` | 1,245 | person on a project for a period, since 1 Jan 2025 |

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
`lost_receipt_declaration`, `status` (`submitted`, `approved`, `paid`),
`approver_id`.

**employee_private.csv** (sensitive, kept apart from `employees.csv` as
HR systems do): `employee_id`, `date_of_birth`, `phone`,
`personal_email`, `home_address`, `bank_name`, `bank_account_number`,
`ifsc` (India) or `routing_number` (US), `pan`, `aadhaar`, `uan` (India)
or `ssn` (US), `emergency_contact_name`, `emergency_contact_relation`,
`emergency_contact_phone`. No agent tool reads it yet: it's there for
the privacy steps (who may see it, hiding it from the model and from
traces).

All fake, in real formats, so privacy tools (e.g. Presidio) recognise
them, but no value can belong to a real person where a safe range
exists:
- US phones are 555-0100 to 555-0199, the range kept for fiction;
  Indian mobiles are random (there is no such range), so never call or
  message them
- SSNs are 9xx-01..49-xxxx, a shape never issued to anyone
- Aadhaar numbers have a valid check digit (Verhoeff), as real ones do;
  PANs follow the real pattern (4th letter P for a person, 5th the
  surname's initial); UANs start 100 or 101
- personal emails end in `.example`, a domain that can't exist
- banks, IFSC prefixes and US routing numbers are real (they're public);
  account numbers are random
- addresses: a real area and PIN or ZIP in the person's office city,
  with a made-up house number and street

**assets.csv** (the IT and Security Handbook, chapter 3): `asset_id`
(AST-…), `employee_id`, `asset_type` (`laptop`, `monitor`, `keyboard`,
`mouse`, `headset`, `phone`), `build` (laptops: `standard` for L1–L3,
`lead` or `macbook` for L4+, `developer` in Engineering and Delivery),
`model`, `serial_number`, `issued_on`, `status` (`assigned`, `retired`,
`lost`), `ended_on` (the day it was retired or lost), `purpose` (`main`;
`client`: a second laptop for client work; `second`: a second monitor;
`on_call`: a phone). Every laptop a person has had is listed: refreshed
every 3 years until 31 March 2026 and every 4 years from then (3 for the
Developer build). The refresh date isn't stored: it follows from
`issued_on`, `build` and the rule (section 3.4), as available leave days
follow from the balances.

**servicedesk_tickets.csv**: `ticket_id` (SD-…), `employee_id`,
`asset_id` (the device; for a request, the one it delivered), `category`
(`HW` or `SEC`, as in the handbook), `request_type` (`fault`, `damage`,
`request`, `lost`, `stolen`), `summary`, `incident_date` (damage, lost or
stolen), `opened_on`, `resolved_on`, `status` (`open`, `resolved`),
`approved_by` (the manager for a Developer build or a second monitor,
the department head for a client laptop), `police_report` (stolen
devices). Only tickets opened from 1 January 2025 are kept.

**trainings.csv** (the L&D Handbook, chapter 2): `assignment_id`
(LRN-…), `employee_id`, `course` (`Code of Conduct`, `Information
Security`, `POSH` in India or `Anti-harassment` in the US, `Anti-harassment:
managers' module` for US managers, `Anti-bribery`, `Secure coding`,
`Phishing awareness`), `reason` (`new_joiner`: within 30 days of
joining; `annual`: everyone, every year; `role`: anti-bribery for
Sales, Finance, Delivery and L5+, secure coding for Engineering, the
managers' module; `phishing`: after a failed phishing test, within 14
days), `assigned_on`, `due_date`, `completed_on`. The status isn't
stored: no `completed_on` and a past `due_date` means overdue. Only
trainings assigned from 1 January 2025 are kept.

**salaries.csv** (the Employee Handbook, chapter 9): `employee_id`,
`effective_from` (the day this pay started), `reason` (`joining`, or
`annual_review`: the raise on 1 July after the April rating),
`annual_pay` (India: annual fixed pay; US: annual base salary),
`currency` (`INR` or `USD`). The first row is the pay in effect on
1 January 2025: the 1 July 2024 raise, or the joining pay for people who
joined from 2024 (not yet rated). The current pay is the latest row. Not
stored, because it follows from the pay and the rules: basic pay (40% of
fixed pay), HRA (50% of basic), provident fund (12% of basic), monthly
pay, the target bonus (the grade's %, 9.4.1).

**ratings.csv** (the Employee Handbook, chapter 10): `employee_id`,
`review_year` (2025 or 2026: the April rating for the financial year
that ended on 31 March), `rating` (`Outstanding`, `Exceeds
expectations`, `Meets expectations`, `Partially meets expectations`,
`Does not meet expectations`). People who joined on or after 1 January
of that year aren't rated (10.2.4), so they have no row for it.

**projects.csv** (looked up only: no handbook has project rules yet):
`project_id` (PRJ-…), `name`, `client` (made up; empty for an internal
project), `industry` (`banking`, `retail`, `healthcare`: the handbook's
industries, Employee 2.1; empty for internal), `odc` (`yes`: the work happens in the
client's project area, banking on the Bengaluru 4th floor and retail on
the Pune 1st floor; Facilities 2.1.2, 2.2.2, 3.4), `project_manager_id`
(a Delivery employee, named here and not in the assignments),
`start_date`, `end_date` (planned). Whether a project is running isn't
stored: it follows from the dates.

**project_assignments.csv**: `employee_id`, `project_id`,
`allocation_percent` (100, or 50 when split across two projects),
`start_date`, `end_date` (the last day on it; empty: until the project
ends). Only Engineering and Delivery staff (L1–L4 and principals) are on
projects. Someone with nothing running today is "on the bench": that
isn't stored either, and no handbook has rules for it.

## Assumptions where the policies are silent

- Only annual leave (India) and PTO (US) are prorated for 2026 joiners;
  sick, casual, and floating days are given in full.
- Carried-over days were used first and all of them before the
  carry-over deadline (31 March in India, 30 June in the US), so none
  have expired.
- Sick and casual leave is never booked ahead; future requests are
  all `pending`.
- Directors have no manager, so their requests have no approver.
- Laptops are refreshed on or up to two weeks before their due date;
  the old one is `retired`. A lost or stolen one is replaced within
  3 working days, and its refresh clock starts again.
- Accessories aren't refreshed; people who joined before 2021 got theirs
  between 2021 and 2023. On-call phones were first issued in 2024.
- Generated tickets keep the rules (at most 2 repairs in 6 months, one
  accidental damage in 12 months, lost devices reported within a day,
  a police report for stolen ones); the scenario people below break
  them on purpose. Repairs take 1–5 working days; a fault opened in the
  last week is still `open`.
- Yearly trainings are assigned on the first working day of the year;
  most people finish shortly before the deadline, about 3% late, and a
  few 2026 ones aren't done yet. Someone who joined less than 6 months
  before a yearly deadline isn't given that one (they just did it as a
  new joiner). Phishing tests ran twice a year; about 3% of people failed
  each one.
- Not in the data: the "Managing at AMS" course for first-time managers
  (2.4.3), since we don't record when someone first got a direct report.
- Pay ranges per grade (the handbook names them but gives no numbers):
  India L1 ₹4.5–7.5 lakh, L2 ₹7.5–13 lakh, L3 ₹12–21 lakh, L4
  ₹18–30 lakh, L5 ₹30–50 lakh, L6 ₹55–95 lakh a year; US L1
  $68–88k, L2 $85–115k, L3 $115–150k, L4 $140–175k, L5 $165–210k,
  L6 $210–280k. Longer-serving people sit higher in the range; a few
  are just above it, as happens in real companies.
- Raises average what surveys report for the year (India about 9%, US
  about 3.5%): more for a better rating, more for people low in their
  range, none for "does not meet expectations". About 60% of people are
  rated "meets expectations", 6% "outstanding" and 3% "does not meet".
- Teams in one office share a project (1–4 teams), run by a Delivery
  lead from that office; Indian clients are served from Bengaluru and
  Pune, US clients from Austin. People join a project about two weeks
  after joining AMS; about 4% rolled off recently and have none, a few
  seniors split their time 50/50, and about 30% of teams came from an
  earlier project since 2025. Not in the data: timesheets, billing,
  utilisation or bench limits (no handbook has rules for them).
- Not in the data: payslips (net pay needs income tax under Indian and
  US law, which the handbooks don't contain) and past bonus payouts
  (they depend on a company-results figure no document gives).
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
| When will Ananya Iyer (AMS-1015) get a new laptop? | Standard build, issued 15 May 2023 (the first one was replaced early) | 4 years from 1 April 2026, also for laptops issued before; it was 3 years (IT 3.4.1) | 15 May 2027; not May 2026 (the old 3-year rule) |
| When is Nikhil Bhat's (AMS-1024) laptop due? | Developer build, issued 20 Nov 2023 | The Developer build stays on 3 years; IT contacts you about 30 days before (IT 3.4.2–3.4.3) | 20 Nov 2026, in 4 days; IT should already have been in touch |
| Can Siddharth Menon (AMS-1016) get his laptop replaced early? | Three fault tickets for shutdowns: 10 Jun, 24 Aug, 2 Nov 2026 | Early replacement after three repair tickets within 6 months, with IT and Security's approval (IT 3.4.4) | Yes, he can ask; IT and Security approve it |
| Will Pallavi Ghosh (AMS-1037) pay for her cracked screen? | Accidental damage on 13 Feb and 9 Oct 2026 | The first in 12 months is free; for a second, AMS may recover up to INR 15,000 if it was negligence (IT 3.5.3) | Possibly: it's her second in 12 months, so up to INR 15,000 if negligent |
| Will Suresh Naidu (AMS-1038) pay for his lost phone? | On-call phone lost on 2 Nov, reported on 5 Nov 2026 | Report within 24 hours; if not, AMS may recover up to INR 30,000 (IT 3.6.1, 3.6.3) | Possibly: reported 3 days late, so up to INR 30,000 |
| What must Karthik Subramanian (AMS-1011) return, and can he buy his laptop? | Developer laptop (AST-10068), keyboard and headset; last working day 24 Dec 2026 | Return everything by the last working day; retired laptops aren't sold to people leaving (IT 3.7.1, 3.7.4) | All three by 24 December 2026; no, he can't buy it |
| Which trainings does Ananya Iyer (AMS-1015) still have to do? | 2026: Code of Conduct and Information Security done; POSH not done | POSH by 31 December every year (L&D 2.3.3) | POSH, by 31 December 2026 |
| Why can't Michael Turner (AMS-1032) open the client systems? | Joined 14 Sep 2026; Information Security (due 14 Oct) not done; secure coding (due 13 Nov) not done | Over 30 days overdue: client access suspended until done (L&D 2.2, 2.5.3) | His Information Security training is 33 days overdue; access comes back when he finishes it. Secure coding is overdue too |
| Was Harish Kumar (AMS-1018) eligible for the October 2026 promotions? | Information Security due 30 Sep, done 12 Oct; rated "Exceeds expectations" in April 2026 | Any overdue training on 1 October: not eligible that cycle (L&D 2.5.2) | No; he can be for April 2027 if nothing is overdue on 1 April |
| What must Kevin Nguyen (AMS-1029) finish by the end of the year? | Austin, Sales, team lead with a report; three 2026 courses not done | US: anti-harassment and, for managers, its module; Sales: anti-bribery; all by 31 December (L&D 2.3.3, 2.4.1) | Anti-harassment, the managers' module and anti-bribery, by 31 December 2026 |
| When must Manoj Tiwari (AMS-1020) finish the phishing course? | Assigned 5 Nov 2026 after the 3 Nov phishing test | Within 14 days (L&D 2.4.4) | By 19 November 2026 |
| What is Ananya Iyer's (AMS-1015) target bonus? | L3, India; annual fixed pay INR 16,86,000 since 1 Jul 2026 | L3–L4: 10% of annual fixed pay; the actual bonus is 0–150% of target with company results and the rating; paid with the June salary (Employee 9.4) | INR 1,68,600 at today's pay, paid with the June 2027 salary; the actual amount depends on company results and her rating |
| Can Pooja Shetty (AMS-1012) see Ananya's salary? Can Siddharth Menon (AMS-1016)? | Pooja is Ananya's manager; Siddharth is on the same team | Salaries are confidential between the employee, their managers and People Operations (Employee 9.5, Legal 7.4) | Pooja yes; Siddharth no |
| Why didn't Ritu Agarwal's (AMS-1023) pay go up in July 2026? | Rated "Does not meet expectations" in April 2026; INR 9,92,000 since 1 Jul 2025 | No increase and no bonus for "does not meet" (Employee 9.3.2, 9.4.2); a 60-day improvement plan is possible (10.5) | Because of her April 2026 rating; she got no bonus in June 2026 either |
| Which project is Ananya Iyer (AMS-1015) on, and who runs it? | PRJ-001 Card payments platform upgrade (Amberleaf Bank), in the banking ODC, since 2 Sep 2024; manager Sneha Pillai (AMS-1019) | Banking ODCs are on the Bengaluru 4th floor; no personal phones inside (Facilities 2.1.2, 3.4.3) | Card payments platform upgrade for Amberleaf Bank; Sneha Pillai is the project manager |
| Lakshmi Krishnan (AMS-1021) changed projects. Can she still enter the banking ODC, and when must her old access go? | Off PRJ-002 (Cobalt Bay Bank, ODC) after 30 Oct; on PRJ-003 from 2 Nov 2026 | ODC access is removed on the day you leave the project (Facilities 3.4.2); other old access within 5 working days of the move (IT 4.5) | No: her ODC access ended on 30 October; the rest of her old project access must be gone by 9 November 2026, 5 working days after the move on 2 November |
| What happens to the client's software on Harish Kumar's (AMS-1018) laptop? | PRJ-005 Claims processing portal (Corvana Hospitals) ends on 30 Nov 2026 | Client-required software is removed when the project ends (IT 7.5) | It's removed when the project ends, on 30 November 2026 |
| How long can Brian Foster (AMS-1033) stay without a project? | Nothing running since PRJ-007 ended on 30 Sep 2026 | No handbook has bench rules | The handbooks don't say; ask his manager or People Operations |
| Why wasn't Omkar Jadhav (AMS-1026) considered for promotion in October 2026? | Rated "Partially meets expectations" in April 2026 | Promotion needs a last rating of "meets expectations" or higher (Employee 10.4.2) | His last rating was below "meets"; it also capped his June 2026 bonus at half his target (9.4.2) |

## How real is this data?

**Real: the shape.** Each file is a system a real company runs, with the
same kinds of fields: an HR system (employees, leave, personal data,
like Workday or Keka), an expense system, an IT asset register and
ServiceDesk (like ServiceNow: asset tag, serial number, owner, status),
a learning system (AMS Learn), compensation history and ratings (like
Workday: each pay change with its date and reason), and project staffing
(like a PSA tool such as Workday PSA: projects, and people assigned with a
percentage and dates). The personal data is what Indian law
makes HR collect: the EPFO lists Aadhaar, PAN and the bank account with
IFSC as KYC for every employee's UAN. The rules come from the handbooks,
which were researched from real company handbooks and Indian and US law,
and written in our own words. Proportions are plausible: teams of 6–8,
a grade pyramid, three offices, about 1.5% serving notice.

**Made up: the values.** Every person, number and date is generated from
those rules. That's how real companies build development and test
systems: data-protection regulators (e.g. Spain's AEPD, under the GDPR)
say to keep real personal data out of them and use artificial data with
the real structure.

**Simpler than a real company:**
- Too clean: no typos, missing fields, duplicates, two people with the
  same name, or old leftover records.
- No career history: nobody was promoted or moved teams; a person's
  grade is the one they joined with.
- Nobody has left yet (15 people are serving notice); no interns or
  contractors.
- The ServiceDesk has only hardware and lost devices; a real one is
  mostly password resets and access requests, many times the tickets.
- Some numbers are estimates, not facts: department sizes, laptops
  breaking about 10% a year, 30% of leads choosing a MacBook, 3% failing
  a phishing test, the pay ranges and the share of each rating. The
  pay ranges are anchored on public figures: Indian IT freshers start at
  about ₹3–4 lakh on standard tracks and ₹7 lakh on digital ones, team
  leads earn about ₹19–22 lakh, and Austin software developers average
  $139,390 (BLS, May 2024). AMS pays a little above the big IT services
  firms.
- Indian mobile numbers are random (no range is kept for fiction).

Sources: [ServiceNow asset fields](https://www.servicenow.com/docs/r/it-asset-management/hardware-asset-management/asset-record-fields.html),
[EPFO UAN and KYC](https://www.epfindia.gov.in/site_docs/PDFs/UAN_PDFs/UAN_Presentation.pdf),
[AEPD on test environments](https://www.aepd.es/en/prensa-y-comunicacion/blog/data-breaches-development-and-pre-production-enviroments),
[Aon: India salary increases](https://www.aon.com/apac/in-the-press/asia-newsroom/2026/aon-survey-projects-slight-uptick-in-salaries-in-india-2026),
[WTW: US 2026 salary budgets](https://worldatwork.org/publications/workspan-daily/wtw-2026-u-s-salary-increase-budgets-will-hold-steady-at-3-5),
[Mercer: 2026 actual increases](https://worldatwork.org/publications/workspan-daily/shrinkage-sign-mercer-says-actual-pay-increases-trailed-predictions),
[BLS: Austin wages, May 2024](https://www.bls.gov/regions/southwest/news-release/2025/occupationalemploymentandwages_austin_20250617.htm),
[Indian IT fresher pay](https://www.businesstoday.in/latest/trends/story/rs-316-lpa-in-2007-rs-336-lpa-in-2026-indias-it-fresher-pay-freezes-even-as-revenues-double-515211-2026-02-09),
[TCS pay by role](https://www.upgrad.com/blog/tcs-salary-in-india/),
[Workday PSA](https://www.workday.com/en-us/products/professional-services-automation/overview.html).
