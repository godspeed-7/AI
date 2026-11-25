"""Build the AMS HR sample data as CSV files (for future agent tools).

In:  the rules in ../policies/ (entitlements, probation, expense
     limits) and the holiday dates in the Employee Handbook (chapter 6);
     --employees N, the company's size (default 1,200; 40 = the
     original 40 people only).
Out: twelve CSV files in this folder:
       employees.csv            N employees in Bengaluru, Pune, Austin
       leave_balances.csv       2026 entitlement, carry-over, used, pending
       leave_requests.csv       every 2026 leave request
       expense_claims.csv       expense items from business trips
       employee_private.csv     personal data (phone, bank, PAN, SSN…)
       assets.csv               IT devices, current and past
       servicedesk_tickets.csv  hardware and lost-device tickets
       trainings.csv            mandatory trainings in AMS Learn
       salaries.csv             pay history, from the pay in effect
                                on 1 Jan 2025
       ratings.csv              April performance ratings
       projects.csv             client and internal projects
       project_assignments.csv  who is on which project, and when

Strategy: the 40 hand-written employees (AMS-1001..1040) and their
rows come first, built exactly as before (SEED), so their rows and IDs
never change. Then build_new_employees() fills each department up to
its share of N under the same 6 directors, with its own seed
(NEW_SEED); their requests, balances and claims follow the same rules
and are numbered after the original ones. Hand-written "scenario" rows
need data + policy together to answer (see README.md). TODAY is fixed,
so "on probation" or "52 days late" never changes. validate() checks
every row against the policy rules before anything is written.

Caveats:
- Fictional data; names are random pairs of common first and last
  names (FAMOUS lists real people's names never to produce). Where
  the policies are silent, the assumptions are listed in README.md.
- New people only ever report to a director or to another new person,
  so the 40's teams stay as they were; only the directors gain reports.
- Each later file (personal data, assets, trainings, pay, projects) has
  its own seed and is built after the first four, so adding one never
  changes them.
- Re-running overwrites all twelve CSV files.
"""

import argparse
import csv
import random
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
HOLIDAY_FILE = (
    DATA_DIR.parent / "policies" / "people" / "employee_handbook.txt"
)
# The holiday calendar is chapter 6 of the Employee Handbook.
HOLIDAY_CHAPTER = 6

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

# --- The rest of the company (build_new_employees) -------------------------
DEFAULT_SIZE = 1200  # the handbook's 700 + 350 + 150 (Employee 2.2.1)
NEW_SEED = 43  # its own seed, so the original 40's rows never change
# Each department's share of the company; Engineering takes the rest.
DEPARTMENT_SHARES = {"Delivery": 0.26, "Sales": 0.08,
                     "IT and Security": 0.05, "People Operations": 0.025,
                     "Finance": 0.025}
# Where each department sits (Bengaluru, Pune, Austin).
# Each department's people in (Bengaluru, Pune, Austin) at 1,200. The
# totals are the handbook's offices (Employee 2.2.1): headquarters about
# 700, Pune the Delivery centre about 350, Austin the client office
# about 150. Other sizes keep these shares.
OFFICE_SPLIT = {
    "Engineering": (508, 112, 52), "Delivery": (90, 199, 23),
    "Sales": (34, 0, 62), "IT and Security": (25, 30, 5),
    "People Operations": (16, 9, 5), "Finance": (27, 0, 3),
}
OFFICES = ("Bengaluru", "Pune", "Austin")
TEAM_SIZE = 8           # one team lead per ~8 people
LEADS_PER_MANAGER = 6   # a manager (L5) runs up to 6 team leads
RESIGNED_SHARE = 0.015  # India: share of people serving notice
TRIPS_PER_PERSON = 18 / 40  # as many trips per person as the 40 have
TRAVEL_WEIGHT = {"Sales": 3, "Delivery": 2}  # everyone else: 1

TECH_DEPARTMENTS = {"Engineering", "IT and Security"}
TITLES = {  # grade -> (tech title, business title)
    "L1": ("Associate", "Associate"),
    "L2": ("Engineer", "Analyst"),
    "L3": ("Senior Engineer", "Senior Analyst"),
    "L4": ("Team Lead", "Team Lead"),
    "L5": ("Manager", "Manager"),
}
# Joined between these years (inclusive), by grade.
JOIN_YEARS = {"L5": (2012, 2021), "L4": (2014, 2023), "L3": (2016, 2025),
              "L2": (2019, 2026), "L1": (2023, 2026)}

INDIAN_MALE = """Aarav Aditya Ajay Akash Akhil Alok Anand Anil Ankit Anurag
Arvind Ashish Ashwin Bharat Chetan Deepak Dhruv Dinesh Ganesh Gaurav
Girish Gopal Hari Hemant Imran Irfan Jatin Jayant Kiran Kunal Lokesh
Mahesh Manish Mohit Naveen Nitin Pankaj Pradeep Prakash Pranav Prasad
Rajesh Rakesh Ramesh Ravi Rohit Sameer Sandeep Santosh Saurabh Shreyas
Srinivas Sudhir Sunil Tarun Tushar Uday Venkat Vijay Vinay Vishal
Yash""".split()
INDIAN_FEMALE = """Aishwarya Akshata Amrita Anjali Ankita Anusha Aparna Archana Asha
Bhavana Chitra Deepa Gayatri Geeta Harini Isha Jyoti Kavya Keerthi Komal
Lavanya Madhuri Manisha Meena Megha Monika Nandini Nisha Padma Preeti
Priyanka Radha Rashmi Rekha Revathi Riya Sakshi Sangeeta Shalini Shilpa
Shreya Simran Smita Sonal Sowmya Sunita Swathi Tanvi Uma Vandana Vidya
Yamini Zoya Farah Nazia Tanya""".split()
INDIAN_FIRST = INDIAN_MALE + INDIAN_FEMALE
INDIAN_LAST = """Agarwal Ahuja Arora Bajaj Banerjee Bansal Basu Bhatt Bhosale
Bose Chandra Chatterjee Chauhan Chavan Das Deshpande Dixit Dubey Dutta
Fernandes Gaikwad Gill Gokhale Goswami Gowda Hegde Hussain Iyengar Jain
Kamath Kapoor Khan Khanna Kini Krishnan Kulkarni Kumar Mahajan Menon
Mishra Mukherjee Murthy Naik Nair Pandey Patel Pillai Prabhu Qureshi
Raman Ranade Rao Rathore Reddy Sen Sethi Sharma Shenoy Shetty Shinde
Shukla Singh Sinha Srinivasan Subramanian Thakur Trivedi Varma
Venkatesan Yadav""".split()
US_MALE = """James John Robert David William Joseph Thomas Christopher
Matthew Anthony Mark Steven Andrew Joshua Ryan Brandon Justin Eric
Jacob Nathan Aaron Adam Jason Kyle Sean Zachary Ethan Logan Evan Carlos
Luis Miguel""".split()
US_FEMALE = """Mary Patricia Linda Elizabeth Barbara Susan Jessica Karen
Lisa Nancy Sandra Kimberly Donna Michelle Amanda Melissa Stephanie
Rebecca Laura Megan Hannah Olivia Lauren Nicole Samantha Maria
Sofia""".split()
US_FIRST = US_MALE + US_FEMALE
US_LAST = """Smith Johnson Williams Brown Jones Garcia Miller Davis
Rodriguez Martinez Hernandez Lopez Gonzalez Wilson Anderson Taylor Moore
Martin Lee Perez Thompson White Harris Sanchez Clark Lewis Robinson
Walker Young Allen Wright Scott Torres Hill Flores Green Adams Nelson
Baker Hall Rivera Campbell Roberts Phillips Evans Parker Collins Edwards
Stewart Morris Murphy Cook Rogers Cooper Peterson Reed Bailey Bell
Kelly Howard Ward Cox Richardson Wood Bennett Gray Hughes Price
Sanders""".split()
# --- Personal data (build_private) -----------------------------------------
PRIVATE_SEED = 44  # its own seed: the other files never change
# Where people live: (area, PIN or ZIP), in their office's city.
HOME_AREAS = {
    "Bengaluru": [("Indiranagar", "560038"), ("Koramangala", "560034"),
                  ("HSR Layout", "560102"), ("Whitefield", "560066"),
                  ("Jayanagar", "560041"), ("JP Nagar", "560078"),
                  ("Malleshwaram", "560003"), ("Hebbal", "560024"),
                  ("Electronic City", "560100"), ("Marathahalli", "560037"),
                  ("BTM Layout", "560076"), ("Banashankari", "560070")],
    "Pune": [("Kothrud", "411038"), ("Aundh", "411007"), ("Baner", "411045"),
             ("Hinjewadi", "411057"), ("Viman Nagar", "411014"),
             ("Hadapsar", "411028"), ("Wakad", "411057"),
             ("Shivajinagar", "411005"), ("Magarpatta", "411013")],
    "Austin": [("Downtown", "78701"), ("East Austin", "78702"),
               ("Tarrytown", "78703"), ("South Congress", "78704"),
               ("Hyde Park", "78705"), ("Northwest Hills", "78731"),
               ("Riverside", "78741"), ("South Austin", "78745"),
               ("Circle C", "78748"), ("Great Hills", "78759")],
}
US_STREETS = ["Oak", "Cedar", "Maple", "Pecan", "Willow", "Riverside",
              "Lakeview", "Hillcrest", "Sunset", "Bluebonnet", "Mesquite",
              "Live Oak", "Barton", "Shoal Creek"]
# (bank, IFSC prefix or routing number, account number length)
INDIA_BANKS = [("HDFC Bank", "HDFC", 14), ("ICICI Bank", "ICIC", 12),
               ("State Bank of India", "SBIN", 11), ("Axis Bank", "UTIB", 15),
               ("Kotak Mahindra Bank", "KKBK", 10)]
US_BANKS = [("JPMorgan Chase", "111000614", 10),
            ("Bank of America", "111000025", 12),
            ("Wells Fargo", "111900659", 10), ("Frost Bank", "114000093", 10)]
# US phones: 555-0100..0199 is reserved for fiction in every area code.
US_AREA_CODES = {"Austin": (512, 737),
                 "elsewhere": (512, 737, 214, 469, 713, 832, 210, 817)}
AGE_AT_JOIN = {"L1": (21, 24), "L2": (22, 30), "L3": (25, 35),
               "L4": (28, 40), "L5": (32, 45), "L6": (35, 50)}
# Aadhaar's check digit (Verhoeff), as UIDAI uses and Presidio checks.
VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
              [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
              [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
              [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
              [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
              [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
              [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
              [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]

# --- Assets and ServiceDesk (IT and Security Handbook, chapter 3) ----------
ASSET_SEED = 46  # its own seed: the other files never change
POLICY_CHANGE = date(2026, 4, 1)  # IT-EQP-2026 v2.0: refresh 3 -> 4 years
TICKETS_FROM = date(2025, 1, 1)   # ServiceDesk history kept from here
LAPTOP_MODELS = {"standard": "Lenovo ThinkPad (14-inch)",
                 "lead": "Lenovo ThinkPad X1 (14-inch)",
                 "macbook": "Apple MacBook Pro (14-inch)",
                 "developer": "Dell Precision (16-inch)"}
SERIAL_PREFIX = {"Lenovo": "PF", "Apple": "C02", "Dell": "DL",
                 "Logitech": "LG", "Jabra": "JB", "Samsung": "R5"}
# (type, model, share of people who have one) - 3.3 Accessories.
ACCESSORIES = [("monitor", "Dell 27-inch monitor", 0.85),
               ("keyboard", "Logitech wireless keyboard", 0.70),
               ("mouse", "Logitech wireless mouse", 0.75),
               ("headset", "Jabra Evolve2 headset", 0.90)]
PHONE_MODEL = "Samsung Galaxy A-series (on-call)"
MACBOOK_SHARE = 0.30          # of L4+ who choose a MacBook (3.2.2)
DEVELOPER_SHARE = {"Engineering": 0.35, "Delivery": 0.10}  # 3.2.3
CLIENT_LAPTOP_SHARE = 0.01    # Engineering and Delivery (3.2.4)
SECOND_MONITOR_SHARE = 0.10   # of people with a monitor (3.3)
ON_CALL_SHARE = {"IT and Security": 0.60}  # + Engineering L4/L5: 0.15
FAULTS_PER_YEAR = 0.10        # HW fault tickets per person
DAMAGE_PER_YEAR = 0.015       # accidental damage
LOSS_PER_YEAR = 0.004         # lost or stolen devices
FAULTS = {
    "laptop": ["Battery drains within two hours", "Keyboard keys not "
               "working", "Laptop overheating", "Screen flickering",
               "Charger not working", "Wi-Fi keeps disconnecting",
               "Trackpad not responding", "Laptop very slow to start"],
    "monitor": ["Monitor not turning on", "Dead pixels on the monitor"],
    "keyboard": ["Keyboard not connecting"],
    "mouse": ["Mouse not connecting"],
    "headset": ["Headset microphone not working"],
    "phone": ["On-call phone not charging"],
}
DAMAGES = ["Screen cracked after the laptop fell",
           "Water spilled on the laptop", "Laptop hinge broken"]
LOSSES = [("lost", "Laptop left in a cab"),
          ("lost", "Laptop bag left at the airport"),
          ("stolen", "Bag with the laptop stolen at the station"),
          ("stolen", "Laptop stolen in a break-in at home")]
# Hand-written in add_asset_scenarios (README scenarios).
ASSET_SCENARIO_IDS = {"AMS-1015", "AMS-1016", "AMS-1024", "AMS-1037",
                      "AMS-1038"}

# --- Mandatory training (L&D Handbook, chapter 2: AMS Learn) ---------------
TRAINING_SEED = 47  # its own seed: the other files never change
TRAININGS_FROM = date(2025, 1, 1)  # AMS Learn history kept from here
TRAINING_YEARS = (2025, 2026)
# Every year, for everyone (2.3): course -> (month, day) due.
ANNUAL = {"Code of Conduct": (3, 31), "Information Security": (9, 30),
          "POSH": (12, 31), "Anti-harassment": (12, 31)}
NEW_JOINER_DAYS = 30           # 2.2
SECURE_CODING_DAYS = 60        # 2.4.2: within 60 days, then every 2 years
PHISHING_DAYS = 14             # 2.4.4
PHISHING_TESTS = [date(2025, 5, 13), date(2025, 11, 4), date(2026, 5, 12),
                  date(2026, 11, 3)]  # simulations, twice a year
PHISHING_FAIL_SHARE = 0.03
ANTI_BRIBERY_DEPARTMENTS = {"Sales", "Finance", "Delivery"}  # + L5 and up
LATE_SHARE = 0.03              # finished after the deadline
NEVER_SHARE = 0.005            # 2026 trainings still not done
# Hand-written in training_outcomes (README scenarios).
TRAINING_SCENARIO_IDS = {"AMS-1015", "AMS-1018", "AMS-1020", "AMS-1029",
                         "AMS-1032"}

# --- Pay and ratings (Employee Handbook, chapters 9 and 10) ----------------
PAY_SEED = 48  # its own seed: the other files never change
PAY_FROM = date(2025, 1, 1)  # pay history kept from the pay in effect here
LAST_REVIEW = date(2024, 7, 1)  # the raise before PAY_FROM
REVIEW_YEARS = (2025, 2026)  # ratings in April (10.2.1), raises 1 July
RATINGS = ["Outstanding", "Exceeds expectations", "Meets expectations",
           "Partially meets expectations", "Does not meet expectations"]
NO_RAISE = "Does not meet expectations"  # no increase (9.3.2)
RATING_SHARES = [0.06, 0.22, 0.60, 0.09, 0.03]  # an estimate (README)
# How much of the average raise each rating gets.
RAISE_FACTOR = dict(zip(RATINGS, [1.6, 1.3, 1.0, 0.4, 0.0]))
# The average raise each year: Aon for India (8.9% in 2025, 9.0% in
# 2026), WTW and Mercer for the US (3.5%, 3.4%).
AVERAGE_RAISE = {("India", 2025): 0.089, ("India", 2026): 0.090,
                 ("US", 2025): 0.035, ("US", 2026): 0.034}
# The pay range for each grade, (min, max): India annual fixed pay in
# INR, US annual base salary in USD (9.2, 9.3.2). Estimates (README).
PAY_RANGES = {
    "India": {"L1": (450_000, 750_000), "L2": (750_000, 1_300_000),
              "L3": (1_200_000, 2_100_000), "L4": (1_800_000, 3_000_000),
              "L5": (3_000_000, 5_000_000), "L6": (5_500_000, 9_500_000)},
    "US": {"L1": (68_000, 88_000), "L2": (85_000, 115_000),
           "L3": (115_000, 150_000), "L4": (140_000, 175_000),
           "L5": (165_000, 210_000), "L6": (210_000, 280_000)},
}
PAY_STEP = {"India": 1_000, "US": 100}  # pay is rounded to this
CURRENCY = {"India": "INR", "US": "USD"}
# README scenarios: their (2025, 2026) ratings.
SCENARIO_RATINGS = {
    "AMS-1015": ("Exceeds expectations", "Meets expectations"),  # Ananya
    "AMS-1018": ("Meets expectations", "Exceeds expectations"),  # Harish
    "AMS-1023": ("Meets expectations", NO_RAISE),                # Ritu
    "AMS-1026": ("Meets expectations",                           # Omkar
                 "Partially meets expectations"),
}

# --- Projects (query-only: no handbook has project rules yet) --------------
PROJECT_SEED = 49  # its own seed: the other files never change
PROJECTS_FROM = date(2025, 1, 1)  # assignments kept if running from here
ON_PROJECTS = ("Engineering", "Delivery")
# Made-up clients (a web search found no company with these names), in
# the handbook's industries: banking, retail, healthcare (Employee 2.1).
CLIENTS = {
    "India": [("Amberleaf Bank", "banking"), ("Cobalt Bay Bank", "banking"),
              ("Marigold Mart", "retail"), ("Peppercorn Stores", "retail"),
              ("Corvana Hospitals", "healthcare")],
    "US": [("Ferrowind Outfitters", "retail"),
           ("Quillfield Health", "healthcare")],
}
# Client project areas (ODCs): banking on the Bengaluru 4th floor, retail
# on the Pune 1st floor (Facilities 2.1.2, 2.2.2, 3.4).
ODC_OFFICE = {"banking": "Bengaluru", "retail": "Pune"}
PROJECT_NAMES = {
    "banking": ["Mobile banking app", "Loan origination system",
                "Fraud monitoring dashboards", "KYC onboarding portal",
                "Treasury reporting", "Net banking redesign",
                "Payments hub", "Credit card rewards platform",
                "Branch teller system", "Regulatory reporting",
                "Wealth management portal", "Customer data platform",
                "ATM monitoring", "Customer service chatbot"],
    "retail": ["E-commerce checkout rebuild", "Inventory sync service",
               "Point-of-sale upgrade", "Supplier portal",
               "Price management tool", "Click and collect",
               "Product search", "Order management system",
               "Store staff app", "Returns portal", "Demand forecasting",
               "Product catalogue migration", "Gift card service",
               "Delivery slot booking"],
    "healthcare": ["Patient scheduling app", "Lab results portal",
                   "Billing system migration", "Care team messaging",
                   "Patient intake forms", "Telehealth visits",
                   "Pharmacy refills", "Claims data warehouse",
                   "Hospital information system", "Bed management dashboard",
                   "Health records upgrade", "Discharge summary service",
                   "Doctor rostering tool", "Patient feedback app"],
    "": ["Internal developer platform", "Test automation framework",
         "Cloud cost dashboards", "Design system", "Data platform",
         "Security tooling", "CI pipeline upgrade", "Observability stack"],
}
TEAMS_PER_PROJECT = (1, 4)  # teams of the same office share a project
INTERNAL_SHARE = 0.15  # Engineering-only projects that are internal
ODC_SHARE = 0.5        # banking/retail projects run in the client's ODC
MOVED_SHARE = 0.3      # projects whose teams came from an earlier one
ROLLED_OFF_SHARE = 0.04  # rolled off recently: no project today
SPLIT_SHARE = 0.06     # seniors split 50/50 across two projects

# Real, well-known people: never generate these names.
FAMOUS = {"Anil Kapoor", "Sunil Shetty", "Shilpa Shetty", "Rakesh Sharma",
          "Kiran Rao", "Madhuri Dixit", "Imran Khan", "Irfan Khan",
          "Farah Khan", "Rajesh Khanna", "Smita Patel", "James Taylor",
          "Elizabeth Taylor", "John Smith", "John Adams", "John Lewis",
          "John Kelly", "James Brown", "Robert Lee", "Andrew Johnson",
          "Christopher Evans", "Mark Taylor", "Susan Collins",
          "Patricia Smith", "Thomas Martin"}


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
    sections = {
        office: f"{HOLIDAY_CHAPTER}.{section}"
        for office, section in {"Bengaluru": "3.1", "Pune": "4.1",
                                "Austin": "6.1"}.items()
    }
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
            elif re.match(r"\d+\.\d+(?:\.\d+)* ", line):
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
        notice_from = (date.fromisoformat(emp["resignation_date"])
                       if emp["resignation_date"] else None)

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
    by_person_and_type = defaultdict(list)  # in the requests' order
    for r in requests:
        by_person_and_type[(r["employee_id"], r["leave_type"])].append(r)

    for emp in employees:
        joined = date.fromisoformat(emp["join_date"])
        for leave_type in leave_types(emp["office"]):
            entitled = entitlement(emp, leave_type)

            mine = by_person_and_type[(emp["employee_id"], leave_type)]
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


def claim_adder(emps: dict, claims: list, first_number: int):
    """add(...) appends one expense item to `claims`, numbered from
    EXP-<first_number>."""
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
            "claim_id": f"EXP-{first_number + len(claims):04d}",
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
    return add


def add_trip(add, emp: dict, trip_no: int, rng: random.Random,
             joined_by: date | None = None):
    """One business trip within the limits and on time: a hotel, the
    daily allowance and a taxi. Skipped if it would be submitted after
    TODAY, or (joined_by) start before that date."""
    india = emp["office"] in INDIA_OFFICES
    cities = [c for c in (INDIA_TRIP_CITIES if india else
                          US_TRIP_CITIES) if c != emp["office"]]
    city = rng.choice(cities)
    nights = rng.randint(1, 3)
    start = date(YEAR, 2, 2) + timedelta(days=rng.randint(0, 250))
    end = start + timedelta(days=nights)
    submitted = end + timedelta(days=rng.randint(2, 20))
    if submitted > TODAY or (joined_by and start < joined_by):
        return
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


def build_claims(employees: list, rng: random.Random) -> list[dict]:
    """Scenario claims first (EXP-0001..), then generated trips."""
    emps = {e["employee_id"]: e for e in employees}
    claims = []
    add = claim_adder(emps, claims, 1)

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
        add_trip(add, rng.choice(travellers), trip_no, rng)

    return claims


# --- The rest of the company ------------------------------------------------
def department_sizes(total: int, existing: list[dict]) -> dict[str, int]:
    """Each department's head count for a company of `total`: its share,
    never fewer than it has now; Engineering takes the rest."""
    have = defaultdict(int)
    for e in existing:
        have[e["department"]] += 1
    sizes = {dept: max(have[dept], round(total * share))
             for dept, share in DEPARTMENT_SHARES.items()}
    sizes["Engineering"] = total - sum(sizes.values())
    assert sizes["Engineering"] >= have["Engineering"], sizes
    return sizes


def office_sizes(dept: str, size: int,
                 existing: list[dict]) -> dict[str, int]:
    """How many new people each office gets in this department, so the
    whole department (with the people it has) follows OFFICE_SPLIT."""
    split = OFFICE_SPLIT[dept]
    exact = [size * n / sum(split) for n in split]
    target = [int(x) for x in exact]
    leftover = size - sum(target)  # to the largest remainders
    for i in sorted(range(3), key=lambda i: target[i] - exact[i])[:leftover]:
        target[i] += 1
    have = [sum(e["department"] == dept and e["office"] == office
                for e in existing) for office in OFFICES]
    new = [max(0, t - h) for t, h in zip(target, have)]
    # An office already over its share: the biggest one makes up for it.
    biggest = new.index(max(new))
    new[biggest] -= sum(new) - (size - sum(have))
    return dict(zip(OFFICES, new))


def unique_name(rng: random.Random, office: str, taken: set[str]) -> str:
    """A first + last name pair no one else has and no famous person
    has; Indian names in India, US names in Austin."""
    first, last = ((INDIAN_FIRST, INDIAN_LAST) if office in INDIA_OFFICES
                   else (US_FIRST, US_LAST))
    while True:
        name = f"{rng.choice(first)} {rng.choice(last)}"
        if name not in taken and name not in FAMOUS:
            taken.add(name)
            return name


def join_monday(rng: random.Random, grade: str) -> date:
    """A Monday (people join on Mondays) in the grade's JOIN_YEARS, not
    after TODAY, on day 1-28 so a 6-month probation date exists."""
    low, high = JOIN_YEARS[grade]
    first = date(low, 1, 1)
    last = min(date(high, 12, 31), TODAY)
    day = first + timedelta(days=rng.randint(0, (last - first).days))
    day -= timedelta(days=day.weekday())  # back to Monday
    if day.day > 28:
        day -= timedelta(days=7)
    return max(day, first + timedelta(days=(7 - first.weekday()) % 7))


def build_new_employees(existing: list[dict], total: int,
                        rng: random.Random) -> list[dict]:
    """Fill every department up to its size, under its director:
    managers (L5) → team leads (L4) → teams of ~8 (L1–L3). IDs from
    AMS-1041 in joining order."""
    directors = {e["department"]: e for e in existing if e["grade"] == "L6"}
    taken = {e["name"] for e in existing}
    people = []  # dicts with a temporary "key" and "boss" (a key or ID)

    def person(dept, grade, boss, office):
        joined = join_monday(rng, grade)
        p = {"key": len(people), "boss": boss, "department": dept,
             "grade": grade, "office": office, "join_date": joined,
             "name": unique_name(rng, office, taken)}
        people.append(p)
        return p

    sizes = department_sizes(total, existing)
    for dept in ["Engineering", *DEPARTMENT_SHARES]:  # a fixed order
        director = directors[dept]["employee_id"]
        # Each office has its own managers and teams: a team sits
        # together, in its manager's office.
        for office, new in office_sizes(dept, sizes[dept],
                                        existing).items():
            if new <= 0:
                continue
            leads = max(1, round(new / TEAM_SIZE))
            managers = leads // LEADS_PER_MANAGER
            members = new - leads - managers

            bosses = [person(dept, "L5", director, office)
                      for _ in range(managers)]
            team_leads = []
            for n in range(leads):
                manager = (bosses[n // LEADS_PER_MANAGER]
                           if n < managers * LEADS_PER_MANAGER else None)
                team_leads.append(person(
                    dept, "L4", manager["key"] if manager else director,
                    office))
            for n in range(members):
                grade = rng.choices(["L1", "L2", "L3"], [20, 40, 40])[0]
                person(dept, grade, team_leads[n % leads]["key"], office)

    # IDs in joining order; then point each boss key at that ID.
    people.sort(key=lambda p: (p["join_date"], p["name"]))
    first_id = 1 + max(int(e["employee_id"][4:]) for e in existing)
    ids = {p["key"]: f"AMS-{first_id + n}" for n, p in enumerate(people)}

    india = [p for p in people if p["office"] in INDIA_OFFICES
             and p["grade"] != "L5"
             and probation_end_date(p["office"], p["join_date"]) <= TODAY]
    resigning = {p["key"] for p in rng.sample(
        india, round(len(india) * RESIGNED_SHARE))}

    rows = []
    for p in sorted(people, key=lambda p: ids[p["key"]]):
        tech = 0 if p["department"] in TECH_DEPARTMENTS else 1
        boss = p["boss"]
        resigned = last_day = None
        if p["key"] in resigning:
            notice = NOTICE_DAYS_INDIA[p["grade"]]
            resigned = TODAY - timedelta(days=rng.randint(1, notice - 1))
            while resigned.weekday() > 4:  # resign on a working day
                resigned -= timedelta(days=1)
            last_day = resigned + timedelta(days=notice - 1)
        joined = p["join_date"]
        if resigned:
            status = "notice_period"
        elif probation_end_date(p["office"], joined) > TODAY:
            status = "probation"
        else:
            status = "confirmed"
        first, last = p["name"].lower().split(" ", 1)
        rows.append({
            "employee_id": ids[p["key"]],
            "name": p["name"],
            "email": f"{first}.{last}@ams.example",
            "office": p["office"],
            "department": p["department"],
            "grade": p["grade"],
            "job_title": TITLES[p["grade"]][tech],
            "manager_id": ids[boss] if isinstance(boss, int) else boss,
            "join_date": joined.isoformat(),
            "status": status,
            "probation_end_date": probation_end_date(
                p["office"], joined).isoformat(),
            "resignation_date": resigned.isoformat() if resigned else "",
            "last_working_day": last_day.isoformat() if last_day else "",
        })
    return rows


def build_new_claims(employees: list, new: list, rng: random.Random,
                     first_claim: int, first_trip: int) -> list[dict]:
    """Trips for the new people, as many per person as the 40 have; Sales
    and Delivery travel most. Numbered after the original claims."""
    emps = {e["employee_id"]: e for e in employees}
    claims = []
    add = claim_adder(emps, claims, first_claim)
    travellers = [e for e in new if e["status"] != "probation"]
    weights = [TRAVEL_WEIGHT.get(e["department"], 1) for e in travellers]
    for n in range(round(len(new) * TRIPS_PER_PERSON)):
        emp = rng.choices(travellers, weights)[0]
        joined = date.fromisoformat(emp["join_date"])
        add_trip(add, emp, first_trip + n, rng,
                 joined_by=joined + timedelta(days=30))
    return claims


# --- Personal data ------------------------------------------------------------
def verhoeff_digit(digits: str) -> int:
    """The check digit that makes `digits` + it pass verhoeff_valid()."""
    check = 0
    for i, digit in enumerate(reversed(digits)):
        check = VERHOEFF_D[check][VERHOEFF_P[(i + 1) % 8][int(digit)]]
    return VERHOEFF_INV[check]


def verhoeff_valid(number: str) -> bool:
    check = 0
    for i, digit in enumerate(reversed(number)):
        check = VERHOEFF_D[check][VERHOEFF_P[i % 8][int(digit)]]
    return check == 0


def build_private(employees: list[dict],
                  rng: random.Random) -> list[dict]:
    """employee_private.csv: what HR holds about each person beyond the
    job. Fake, in real formats: Indian mobiles, US 555-01xx numbers,
    PAN, Aadhaar (valid check digit), UAN, SSNs never issued (9xx-01..49),
    .example email domains."""
    taken = set()  # every phone, email and ID number given out

    def fresh(make):
        while True:
            value = make()
            if value not in taken:
                taken.add(value)
                return value

    def digits(n: int, first: str = "123456789") -> str:
        return rng.choice(first) + "".join(
            rng.choice("0123456789") for _ in range(n - 1))

    def phone(office: str, where: str = "Austin") -> str:
        if office in INDIA_OFFICES:
            return fresh(lambda: "+91 " + digits(5, "6789") + " "
                         + digits(5, "0123456789"))
        return fresh(lambda: f"+1 {rng.choice(US_AREA_CODES[where])}"
                     f"-555-01{rng.randint(0, 99):02d}")

    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"

    def pan(last: str) -> str:
        """5 letters (4th: P for a person, 5th: the surname's initial),
        4 digits, a letter."""
        return fresh(lambda: "".join(rng.choice(letters) for _ in range(3))
                     + "P" + last[0].upper() + digits(4, "0123456789")
                     + rng.choice(letters))

    def aadhaar() -> str:
        """12 digits, not starting with 0 or 1, the last a check digit."""
        def make():
            body = digits(11, "23456789")
            return body + str(verhoeff_digit(body))
        return fresh(make)

    def uan() -> str:
        """12 digits starting 100 or 101, as EPFO issues them."""
        return fresh(lambda: rng.choice(["100", "101"])
                     + digits(9, "0123456789"))

    def ssn() -> str:
        """Area 9xx with group 01-49: a shape never issued to anyone."""
        return fresh(lambda: f"9{rng.randint(0, 99):02d}-"
                     f"{rng.randint(1, 49):02d}-{rng.randint(1, 9999):04d}")

    def ordinal(n: int) -> str:
        suffix = "th" if 11 <= n % 100 <= 13 else {
            1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    rows = []
    for e in employees:
        india = e["office"] in INDIA_OFFICES
        first, last = e["name"].split(" ", 1)
        joined = date.fromisoformat(e["join_date"])

        # Born so they were 21+ when they joined and are under 60 now.
        low, high = AGE_AT_JOIN[e["grade"]]
        years_here = (TODAY - joined).days / 365.25
        age = max(21, min(rng.randint(low, high), int(59 - years_here)))
        born = joined - timedelta(days=round(age * 365.25)
                                  + rng.randint(0, 364))

        area, code = rng.choice(HOME_AREAS[e["office"]])
        if india:
            home = (f"{rng.randint(1, 450)}, {ordinal(rng.randint(1, 18))} "
                    f"Cross, {area}, {e['office']} {code}")
            bank, prefix, length = rng.choice(INDIA_BANKS)
        else:
            home = (f"{rng.randint(100, 9899)} {rng.choice(US_STREETS)} "
                    f"{rng.choice(['St', 'Ave', 'Dr', 'Ln'])}, {area}, "
                    f"Austin, TX {code}")
            bank, prefix, length = rng.choice(US_BANKS)

        if age < 28:
            relation = rng.choice(["Father", "Mother"])
        else:
            relation = rng.choices(["Spouse", "Father", "Mother", "Brother",
                                    "Sister"], [70, 8, 8, 7, 7])[0]
        # The contact's first name fits the relation; a spouse's either.
        men, women = ((INDIAN_MALE, INDIAN_FEMALE) if india
                      else (US_MALE, US_FEMALE))
        pool = {"Father": men, "Brother": men, "Mother": women,
                "Sister": women}.get(relation, men + women)
        contact_first = rng.choice([n for n in pool if n != first])

        handle = f"{first}.{last}".lower()
        rows.append({
            "employee_id": e["employee_id"],
            "date_of_birth": born.isoformat(),
            "phone": phone(e["office"]),
            "personal_email": fresh(lambda: f"{handle}{rng.randint(10, 99)}@"
                                    f"{rng.choice(['mail', 'inbox', 'post'])}"
                                    ".example"),
            "home_address": home,
            "bank_name": bank,
            "bank_account_number": fresh(lambda: digits(length)),
            "ifsc": f"{prefix}0{digits(6, '0123456789')}" if india else "",
            "routing_number": "" if india else prefix,
            "pan": pan(last) if india else "",
            "aadhaar": aadhaar() if india else "",
            "uan": uan() if india else "",
            "ssn": "" if india else ssn(),
            "emergency_contact_name": f"{contact_first} {last}",
            "emergency_contact_relation": relation,
            "emergency_contact_phone": phone(e["office"], "elsewhere"),
        })
    return rows


def validate_private(employees: list[dict], private: list[dict]):
    """Fail loudly if a personal-data row is out of shape."""
    assert [p["employee_id"] for p in private] == \
        [e["employee_id"] for e in employees], "one row per employee"
    for column in ("phone", "personal_email", "bank_account_number", "pan",
                   "aadhaar", "uan", "ssn"):
        values = [p[column] for p in private if p[column]]
        assert len(set(values)) == len(values), f"duplicate {column}"
    emps = {e["employee_id"]: e for e in employees}
    for p in private:
        e = emps[p["employee_id"]]
        born = date.fromisoformat(p["date_of_birth"])
        age_now = (TODAY - born).days / 365.25
        age_at_join = (date.fromisoformat(e["join_date"]) - born).days / 365.25
        assert 21 <= age_at_join and age_now < 60, p
        if e["office"] in INDIA_OFFICES:
            assert re.fullmatch(r"\+91 [6-9]\d{4} \d{5}", p["phone"]), p
            assert re.fullmatch(r"[A-Z]{3}P[A-Z]\d{4}[A-Z]", p["pan"]), p
            assert p["pan"][4] == e["name"].split(" ", 1)[1][0].upper(), p
            assert re.fullmatch(r"[2-9]\d{11}", p["aadhaar"]), p
            assert verhoeff_valid(p["aadhaar"]), p
            assert re.fullmatch(r"10[01]\d{9}", p["uan"]), p
            assert re.fullmatch(r"[A-Z]{4}0\d{6}", p["ifsc"]), p
            assert not (p["ssn"] or p["routing_number"]), p
        else:
            assert re.fullmatch(r"\+1 \d{3}-555-01\d\d", p["phone"]), p
            assert re.fullmatch(r"9\d\d-(0[1-9]|[1-4]\d)-\d{4}", p["ssn"]), p
            assert p["routing_number"] and not (
                p["pan"] or p["aadhaar"] or p["uan"] or p["ifsc"]), p
        assert p["personal_email"].endswith(".example"), p
    print("All personal-data checks passed.")


# --- Assets and ServiceDesk -----------------------------------------------------
def add_years(day: date, years: int) -> date:
    """The same date `years` later (29 February -> 28 February)."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def working_day(day: date, step: int = 1) -> date:
    """`day`, or the nearest weekday after (step 1) or before (step -1)."""
    while day.weekday() > 4:
        day += timedelta(days=step)
    return day


def laptop_due(issued: date, build: str) -> date:
    """When a laptop is replaced (IT-EQP-2026 3.4): 3 years for the
    Developer build; 4 for the rest, from 1 April 2026, even for laptops
    issued before. One that reached 3 years before that date was
    replaced then, under version 1.3's 3-year cycle."""
    three = add_years(issued, 3)
    if build == "developer" or three < POLICY_CHANGE:
        return three
    return add_years(issued, 4)


class AssetBuilder:
    """Devices (AST-10001..) and ServiceDesk tickets, in the order the
    people come; tickets are numbered later (numbered_tickets)."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.assets = []
        self.tickets = []
        self.serials = set()

    def asset(self, emp: dict, kind: str, model: str, issued: date,
              build: str = "", purpose: str = "main") -> dict:
        brand = model.split(" ")[0]
        while True:
            serial = SERIAL_PREFIX[brand] + "".join(
                self.rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXYZ")
                for _ in range(8))
            if serial not in self.serials:
                self.serials.add(serial)
                break
        row = {"asset_id": f"AST-{10001 + len(self.assets)}",
               "employee_id": emp["employee_id"], "asset_type": kind,
               "build": build, "model": model, "serial_number": serial,
               "issued_on": issued.isoformat(), "status": "assigned",
               "ended_on": "", "purpose": purpose}
        self.assets.append(row)
        return row

    @staticmethod
    def end(asset: dict, status: str, day: date):
        asset["status"], asset["ended_on"] = status, day.isoformat()

    def ticket(self, emp: dict, asset: dict | None, category: str,
               request_type: str, summary: str, opened: date,
               resolved: date | None = None, incident: date | None = None,
               approved_by: str = "",
               police_report: str = "") -> dict | None:
        """A ticket about `asset` (for a request: the device it
        delivered). None, and nothing kept, if it was opened before
        TICKETS_FROM: the history starts there."""
        if opened < TICKETS_FROM:
            return None
        if resolved is None and request_type in ("fault", "damage"):
            resolved = working_day(opened + timedelta(
                days=self.rng.choice([1, 1, 2, 2, 2, 3, 5])))
            if opened >= TODAY - timedelta(days=7):
                resolved = None  # opened in the last week: still open
        is_open = resolved is None or resolved > TODAY
        row = {"employee_id": emp["employee_id"],
               "asset_id": asset["asset_id"] if asset else "",
               "category": category, "request_type": request_type,
               "summary": summary,
               "incident_date": incident.isoformat() if incident else "",
               "opened_on": opened.isoformat(),
               "resolved_on": "" if is_open else resolved.isoformat(),
               "status": "open" if is_open else "resolved",
               "approved_by": approved_by, "police_report": police_report}
        self.tickets.append(row)
        return row


def police_report(rng: random.Random, office: str, day: date) -> str:
    if office in INDIA_OFFICES:
        return f"FIR {rng.randint(100, 999)}/{day.year}, {office} police"
    return f"APD {day.year % 100}-{rng.randint(1000000, 9999999)}"


def random_day(rng: random.Random, first: date, last: date) -> date | None:
    """A weekday from first to last, or None if there is none."""
    if last < first:
        return None
    day = first + timedelta(days=rng.randint(0, (last - first).days))
    day = working_day(day, -1)
    return day if day >= first else None


def add_laptops(b: AssetBuilder, emp: dict,
                events: bool) -> list[tuple[dict, date, date]]:
    """The person's main laptops from joining to TODAY: refreshed when
    due, the Developer build from when they asked for it, a lost or
    stolen one replaced (events: random losses and their tickets).
    Returns (laptop, from, to) for each one in turn."""
    rng = b.rng
    joined = date.fromisoformat(emp["join_date"])
    grade, dept = emp["grade"], emp["department"]
    if grade in ("L4", "L5", "L6"):
        build = "macbook" if rng.random() < MACBOOK_SHARE else "lead"
    else:
        build = "standard"
    developer_from = None
    if dept in DEVELOPER_SHARE and grade != "L6" \
            and rng.random() < DEVELOPER_SHARE[dept]:
        developer_from = (joined if rng.random() < 0.6 else random_day(
            rng, joined + timedelta(days=60), TODAY - timedelta(days=14)))
    loss_on = None
    if events:
        first = max(TICKETS_FROM, joined + timedelta(days=30))
        years = max(0, (TODAY - first).days) / 365.25
        if rng.random() < LOSS_PER_YEAR * years:
            loss_on = random_day(rng, first, TODAY - timedelta(days=7))

    issued = working_day(joined)
    if developer_from == joined:
        build = "developer"
    laptop = b.asset(emp, "laptop", LAPTOP_MODELS[build], issued, build)
    history = []
    while True:
        due = laptop_due(issued, build)
        change, why = None, None
        if developer_from and build != "developer" \
                and issued < developer_from <= min(due, TODAY):
            change, why = developer_from, "developer"
        if loss_on and issued < loss_on <= min(due, TODAY) \
                and (change is None or loss_on < change):
            change, why = loss_on, "loss"
        if change is None and due <= TODAY:
            change, why = working_day(due - timedelta(
                days=rng.randint(0, 14)), -1), "refresh"
        if change is None:
            history.append((laptop, issued, TODAY))
            return history

        history.append((laptop, issued, change))
        requested = None
        if why == "loss":
            kind, summary = rng.choice(LOSSES)
            b.end(laptop, "lost", change)
            replaced = working_day(change + timedelta(
                days=rng.randint(1, 3)))
            b.ticket(emp, laptop, "SEC", kind, summary,
                     change + timedelta(days=rng.randint(0, 1)),
                     resolved=replaced, incident=change,
                     police_report=police_report(rng, emp["office"], change)
                     if kind == "stolen" else "")
            loss_on, issued = None, replaced
        else:
            b.end(laptop, "retired", change)
            issued = change
            if why == "developer":
                build = "developer"
                if change >= TICKETS_FROM:
                    requested = change - timedelta(days=rng.randint(5, 10))
        laptop = b.asset(emp, "laptop", LAPTOP_MODELS[build], issued,
                         build)
        if requested:  # the request names the laptop it delivered
            b.ticket(emp, laptop, "HW", "request", "Developer build laptop",
                     requested, resolved=change,
                     approved_by=emp["manager_id"])


def add_other_devices(b: AssetBuilder, emp: dict, emps: dict,
                      on_call: bool | None = None) -> list[dict]:
    """Accessories (3.3), a second monitor with the manager's OK, an
    on-call phone, a second laptop for client work (3.2.4)."""
    rng = b.rng
    joined = date.fromisoformat(emp["join_date"])
    devices = []

    def issue_day():
        if joined >= date(2021, 1, 1):
            return working_day(joined + timedelta(days=rng.randint(0, 5)))
        return random_day(rng, date(2021, 1, 4), date(2023, 12, 29))

    for kind, model, share in ACCESSORIES:
        if rng.random() < share:
            first = issue_day()
            devices.append(b.asset(emp, kind, model, first))
            if kind == "monitor" and emp["manager_id"] \
                    and rng.random() < SECOND_MONITOR_SHARE:
                day = random_day(rng, first + timedelta(days=30),
                                 TODAY - timedelta(days=3))
                if day:
                    second = b.asset(emp, kind, model, day,
                                     purpose="second")
                    devices.append(second)
                    if day >= TICKETS_FROM:
                        b.ticket(emp, second, "HW", "request",
                                 "Second monitor",
                                 day - timedelta(days=rng.randint(3, 8)),
                                 resolved=day,
                                 approved_by=emp["manager_id"])
    if on_call is None:
        share = ON_CALL_SHARE.get(emp["department"], 0)
        if emp["department"] == "Engineering" and emp["grade"] in ("L4",
                                                                   "L5"):
            share = 0.15
        on_call = rng.random() < share
    if on_call:  # on-call phones were first issued in 2024
        day = (issue_day() if joined >= date(2024, 1, 1) else
               random_day(rng, date(2024, 1, 2), date(2025, 6, 30)))
        devices.append(b.asset(emp, "phone", PHONE_MODEL, day,
                               purpose="on_call"))
    if emp["department"] in DEVELOPER_SHARE and emp["grade"] != "L6" \
            and rng.random() < CLIENT_LAPTOP_SHARE:
        day = random_day(rng, max(TICKETS_FROM,
                                  joined + timedelta(days=30)), TODAY)
        if day:
            build = "lead" if emp["grade"] in ("L4", "L5") else "standard"
            head = next(e["employee_id"] for e in emps.values()
                        if e["department"] == emp["department"]
                        and e["grade"] == "L6")
            client = b.asset(emp, "laptop", LAPTOP_MODELS[build], day,
                             build, purpose="client")
            devices.append(client)
            b.ticket(emp, client, "HW", "request",
                     "Second laptop for client work",
                     day - timedelta(days=rng.randint(5, 10)),
                     resolved=day, approved_by=head)
    return devices


def add_incidents(b: AssetBuilder, emp: dict,
                  laptops: list[tuple[dict, date, date]],
                  devices: list[dict]):
    """Random faults (at most 2 in any 6 months) and accidental damage
    (at most 1 in 12 months): within the rules, so the scenarios stand
    out."""
    rng = b.rng
    joined = date.fromisoformat(emp["join_date"])
    first = max(TICKETS_FROM, joined + timedelta(days=14))
    years = max(0, (TODAY - first).days) / 365.25

    def laptop_on(day):
        return next((lap for lap, start, stop in laptops
                     if start <= day < stop or (stop == TODAY
                                                and start <= day)), None)

    faults = []
    for _ in range(round(years * 3)):
        if rng.random() < FAULTS_PER_YEAR / 3:
            day = random_day(rng, first, TODAY)
            if not day or sum(abs((day - f).days) < 183
                              for f in faults) >= 2:
                continue
            kinds = [d for d in devices if d["issued_on"] <= day.isoformat()
                     and d["status"] == "assigned"]
            device = (laptop_on(day) if rng.random() < 0.7 or not kinds
                      else rng.choice(kinds))
            if device:
                faults.append(day)
                b.ticket(emp, device, "HW", "fault",
                         rng.choice(FAULTS[device["asset_type"]]), day)
    if rng.random() < DAMAGE_PER_YEAR * years:
        day = random_day(rng, first, TODAY - timedelta(days=3))
        laptop = laptop_on(day) if day else None
        if laptop:
            b.ticket(emp, laptop, "HW", "damage", rng.choice(DAMAGES),
                     working_day(day + timedelta(days=rng.randint(0, 1))),
                     incident=day)


def add_asset_scenario(b: AssetBuilder, emp: dict, emps: dict):
    """One README scenario person: devices and tickets that need the IT
    handbook (chapter 3) to answer."""
    d = date
    match emp["employee_id"]:
        case "AMS-1015":
            # Ananya: her laptop since 15 May 2023 is due on 15 May 2027
            # (4 years, the handbook's own example), not May 2026 (the
            # old 3 years). The first one was replaced early (failures).
            first = b.asset(emp, "laptop", LAPTOP_MODELS["standard"],
                            d(2021, 8, 9), "standard")
            b.end(first, "retired", d(2023, 5, 15))
            b.asset(emp, "laptop", LAPTOP_MODELS["standard"],
                    d(2023, 5, 15), "standard")
            add_other_devices(b, emp, emps, on_call=False)

        case "AMS-1016":
            # Siddharth: a third repair ticket within 6 months for the
            # same fault (he may ask for early replacement; IT and
            # Security decide).
            laptop = add_laptops(b, emp, events=False)[-1][0]
            for opened, resolved, summary in [
                (d(2026, 6, 10), d(2026, 6, 12),
                 "Laptop shuts down without warning"),
                (d(2026, 8, 24), d(2026, 8, 27),
                 "Laptop shuts down again; motherboard replaced"),
                (d(2026, 11, 2), d(2026, 11, 4),
                 "Laptop still shuts down after the motherboard repair"),
            ]:
                b.ticket(emp, laptop, "HW", "fault", summary, opened,
                         resolved=resolved)
            add_other_devices(b, emp, emps, on_call=False)

        case "AMS-1024":
            # Nikhil: a Developer build since 20 Nov 2023 is due on
            # 20 Nov 2026 (3 years), 4 days after TODAY.
            first = b.asset(emp, "laptop", LAPTOP_MODELS["standard"],
                            d(2022, 4, 11), "standard")
            b.end(first, "retired", d(2023, 11, 20))
            b.asset(emp, "laptop", LAPTOP_MODELS["developer"],
                    d(2023, 11, 20), "developer")
            add_other_devices(b, emp, emps, on_call=False)

        case "AMS-1037":
            # Pallavi: a second accidental damage within 12 months (AMS
            # may recover up to INR 15,000 if it was negligence).
            laptop = add_laptops(b, emp, events=False)[-1][0]
            for incident, opened, resolved, summary in [
                (d(2026, 2, 13), d(2026, 2, 16), d(2026, 2, 18),
                 "Coffee spilled on the keyboard"),
                (d(2026, 10, 9), d(2026, 10, 12), d(2026, 10, 15),
                 "Screen cracked: laptop dropped from the desk"),
            ]:
                b.ticket(emp, laptop, "HW", "damage", summary, opened,
                         resolved=resolved, incident=incident)
            add_other_devices(b, emp, emps, on_call=True)

        case "AMS-1038":
            # Suresh: lost his on-call phone on 2 Nov, reported it 3 days
            # later (not within 24 hours: AMS may recover up to
            # INR 30,000).
            add_laptops(b, emp, events=False)
            devices = add_other_devices(b, emp, emps, on_call=True)
            phone = next(x for x in devices if x["asset_type"] == "phone")
            b.end(phone, "lost", d(2026, 11, 2))
            b.ticket(emp, phone, "SEC", "lost",
                     "On-call phone lost on the bus", d(2026, 11, 5),
                     resolved=d(2026, 11, 9), incident=d(2026, 11, 2))
            b.asset(emp, "phone", PHONE_MODEL, d(2026, 11, 9),
                    purpose="on_call")


def build_assets(b: AssetBuilder, employees: list[dict], emps: dict):
    """These people's devices and tickets; the scenario people by
    hand."""
    for emp in employees:
        if emp["employee_id"] in ASSET_SCENARIO_IDS:
            add_asset_scenario(b, emp, emps)
            continue
        laptops = add_laptops(b, emp, events=True)
        devices = add_other_devices(b, emp, emps)
        add_incidents(b, emp, laptops, devices)


def numbered_tickets(tickets: list[dict], first: int) -> list[dict]:
    """Sorted by the day opened, numbered SD-<first>.., ID first."""
    ordered = sorted(tickets,
                     key=lambda t: (t["opened_on"], t["employee_id"]))
    return [{"ticket_id": f"SD-{first + n}", **t}
            for n, t in enumerate(ordered)]


def validate_assets(employees: list[dict], assets: list[dict],
                    tickets: list[dict]):
    """Fail loudly if a device or ticket breaks the IT handbook's rules
    (the scenario people break them on purpose, so they're skipped)."""
    emps = {e["employee_id"]: e for e in employees}
    by_id = {a["asset_id"]: a for a in assets}
    for column, rows in (("asset_id", assets), ("serial_number", assets),
                         ("ticket_id", tickets)):
        values = [r[column] for r in rows]
        assert len(set(values)) == len(values), f"duplicate {column}"

    main = defaultdict(list)
    for a in assets:
        e = emps[a["employee_id"]]
        assert a["issued_on"] >= e["join_date"], a
        assert a["issued_on"] <= TODAY.isoformat(), a
        if a["asset_type"] == "laptop":
            if a["build"] == "standard":
                assert e["grade"] in ("L1", "L2", "L3"), a
            elif a["build"] in ("lead", "macbook"):
                assert e["grade"] in ("L4", "L5", "L6"), a
            else:
                assert e["department"] in DEVELOPER_SHARE, a
            if a["purpose"] == "main" and a["status"] == "assigned":
                main[a["employee_id"]].append(a)
                due = laptop_due(date.fromisoformat(a["issued_on"]),
                                 a["build"])
                assert due > TODAY, f"overdue laptop: {a}"
    for e in employees:
        assert len(main[e["employee_id"]]) == 1, \
            f"{e['employee_id']}: {len(main[e['employee_id']])} laptops"

    by_person = defaultdict(list)
    for t in tickets:
        e = emps[t["employee_id"]]
        assert t["opened_on"] >= e["join_date"], t
        assert t["opened_on"] >= TICKETS_FROM.isoformat(), t
        if t["asset_id"]:
            assert by_id[t["asset_id"]]["employee_id"] == e["employee_id"], t
        if t["request_type"] == "request" and t["status"] == "resolved":
            # a fulfilled request names the device, issued that day
            assert by_id[t["asset_id"]]["issued_on"] == t["resolved_on"], t
        assert not t["approved_by"] or t["approved_by"] in emps, t
        by_person[e["employee_id"]].append(t)
    for emp_id, mine in by_person.items():
        if emp_id in ASSET_SCENARIO_IDS:
            continue
        faults = sorted(date.fromisoformat(t["opened_on"]) for t in mine
                        if t["request_type"] == "fault")
        for a, c in zip(faults, faults[2:]):
            assert (c - a).days >= 183, f"{emp_id}: 3 faults in 6 months"
        damage = sorted(date.fromisoformat(t["incident_date"]) for t in mine
                        if t["request_type"] == "damage")
        for a, c in zip(damage, damage[1:]):
            assert (c - a).days >= 365, f"{emp_id}: 2 damages in 12 months"
        for t in mine:
            if t["category"] == "SEC":
                late = (date.fromisoformat(t["opened_on"])
                        - date.fromisoformat(t["incident_date"])).days
                assert late <= 1, f"lost device reported late: {t}"
                assert (t["request_type"] == "stolen") == bool(
                    t["police_report"]), t
    print("All asset and ServiceDesk checks passed.")


# --- Mandatory training -----------------------------------------------------------
def harassment_course(emp: dict) -> str:
    """POSH in India, the anti-harassment course in the US (2.2)."""
    return "POSH" if emp["office"] in INDIA_OFFICES else "Anti-harassment"


def due_trainings(emp: dict, reports: set[str]) -> list[tuple]:
    """(course, reason, assigned_on, due_date) for every training the
    rules give this person, assigned from TRAININGS_FROM to TODAY."""
    joined = date.fromisoformat(emp["join_date"])
    india = emp["office"] in INDIA_OFFICES
    rows = []

    # New joiners: three courses within 30 days (2.2).
    if joined + timedelta(days=NEW_JOINER_DAYS) >= TRAININGS_FROM:
        for course in ("Code of Conduct", "Information Security",
                       harassment_course(emp)):
            rows.append((course, "new_joiner", joined,
                         joined + timedelta(days=NEW_JOINER_DAYS)))

    # Every year (2.3), and the role-based yearly ones (2.4.1, 2.3.3).
    yearly = [c for c in ANNUAL
              if c in ("Code of Conduct", "Information Security",
                       harassment_course(emp))]
    role = []
    if emp["department"] in ANTI_BRIBERY_DEPARTMENTS \
            or emp["grade"] in ("L5", "L6"):
        role.append("Anti-bribery")
    if not india and emp["employee_id"] in reports:
        role.append("Anti-harassment: managers' module")
    for year in TRAINING_YEARS:
        assigned = working_day(date(year, 1, 1))
        for course in yearly + role:
            month, day = ANNUAL.get(course, (12, 31))
            due = date(year, month, day)
            # Just did it as a new joiner, or joined too late for it.
            recent = (NEW_JOINER_DAYS if course in role else 180)
            if due < joined + timedelta(days=recent) or assigned > TODAY:
                continue
            rows.append((course, "annual" if course in yearly else "role",
                         max(assigned, joined), due))

    # Secure coding: Engineering, within 60 days, then every 2 years.
    if emp["department"] == "Engineering":
        due, k = joined + timedelta(days=SECURE_CODING_DAYS), 0
        while due <= TODAY + timedelta(days=SECURE_CODING_DAYS):
            assigned = joined if k == 0 else due - timedelta(days=60)
            if due >= TRAININGS_FROM and assigned <= TODAY:
                rows.append(("Secure coding", "role", assigned, due))
            k += 1
            due = add_years(joined + timedelta(days=SECURE_CODING_DAYS),
                            2 * k)
    return rows


def finished_on(rng: random.Random, assigned: date, due: date,
                quick: bool) -> date | None:
    """When a person finished a training: mostly on time and close to the
    deadline (quick: soon after it was assigned), sometimes late, now and
    then not at all; None if not (yet) by TODAY."""
    r = rng.random()
    if r < NEVER_SHARE and due.year == 2026:
        return None
    if r < NEVER_SHARE + LATE_SHARE:
        day = due + timedelta(days=rng.randint(1, 45))
    elif quick:
        day = assigned + timedelta(days=rng.randint(1, max(1, (due
                                                     - assigned).days - 5)))
    else:  # most people finish shortly before the deadline
        span = (due - assigned).days
        day = due - timedelta(days=round(span * rng.betavariate(1, 8)))
    day = max(working_day(day, -1), assigned)
    return day if day <= TODAY else None


def training_outcomes(emp_id: str) -> dict:
    """The README scenarios: (course, due) -> finished on (None: not
    done); every other training of theirs is done 2 weeks early."""
    d = date
    return {
        # Harish: Information Security done 12 days late, so overdue on
        # 1 October: not eligible for that promotion cycle (2.5.2).
        "AMS-1018": {("Information Security", d(2026, 9, 30)):
                     d(2026, 10, 12)},
        # Michael: a new joiner (14 Sep) who hasn't done Information
        # Security, more than 30 days overdue: client access suspended
        # (2.5.3); secure coding just overdue too.
        "AMS-1032": {("Code of Conduct", d(2026, 10, 14)): d(2026, 9, 18),
                     ("Anti-harassment", d(2026, 10, 14)): d(2026, 9, 25),
                     ("Information Security", d(2026, 10, 14)): None,
                     ("Secure coding", d(2026, 11, 13)): None},
    }.get(emp_id, {})


def build_trainings(employees: list[dict], rng: random.Random,
                    reports: set[str]) -> list[dict]:
    """Every training these people were assigned, with when they finished
    it; failed phishing tests add the extra course (2.4.4)."""
    rows = []
    for emp in employees:
        emp_id = emp["employee_id"]
        joined = date.fromisoformat(emp["join_date"])
        scenario = emp_id in TRAINING_SCENARIO_IDS
        outcomes = training_outcomes(emp_id)
        mine = due_trainings(emp, reports)
        if scenario:
            if emp_id == "AMS-1020":  # Manoj failed the 3 Nov test
                assigned = working_day(date(2026, 11, 5))
                mine.append(("Phishing awareness", "phishing", assigned,
                             assigned + timedelta(days=PHISHING_DAYS)))
        else:
            for test in PHISHING_TESTS:
                if joined < test and rng.random() < PHISHING_FAIL_SHARE:
                    assigned = working_day(test + timedelta(days=2))
                    if assigned <= TODAY:
                        mine.append(("Phishing awareness", "phishing",
                                     assigned, assigned + timedelta(
                                         days=PHISHING_DAYS)))
        for course, reason, assigned, due in sorted(mine,
                                                    key=lambda m: m[2]):
            if scenario:
                done = outcomes.get((course, due),
                                    working_day(due - timedelta(days=14),
                                                -1))
                if done and (done > TODAY or done < assigned):
                    done = None if done > TODAY else assigned
                if emp_id == "AMS-1020" and reason == "phishing":
                    done = None
            else:
                done = finished_on(rng, assigned, due,
                                   quick=reason in ("new_joiner",
                                                    "phishing"))
            rows.append({"employee_id": emp_id, "course": course,
                         "reason": reason,
                         "assigned_on": assigned.isoformat(),
                         "due_date": due.isoformat(),
                         "completed_on": done.isoformat() if done else ""})
    return rows


def numbered_trainings(rows: list[dict], first: int) -> list[dict]:
    """Sorted by the day assigned, numbered LRN-<first>.., ID first."""
    ordered = sorted(rows, key=lambda r: (r["assigned_on"],
                                          r["employee_id"], r["course"]))
    return [{"assignment_id": f"LRN-{first + n}", **r}
            for n, r in enumerate(ordered)]


def validate_trainings(employees: list[dict], rows: list[dict],
                       reports: set[str]):
    """Fail loudly if a training breaks the L&D handbook's rules."""
    emps = {e["employee_id"]: e for e in employees}
    ids = [r["assignment_id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate assignment_id"
    keys = [(r["employee_id"], r["course"], r["due_date"]) for r in rows]
    assert len(set(keys)) == len(keys), "the same training twice"
    has_conduct = set()
    for r in rows:
        e = emps[r["employee_id"]]
        india = e["office"] in INDIA_OFFICES
        assert e["join_date"] <= r["assigned_on"] <= TODAY.isoformat(), r
        assert r["due_date"] > r["assigned_on"], r
        assert not r["completed_on"] or (
            r["assigned_on"] <= r["completed_on"] <= TODAY.isoformat()), r
        course = r["course"]
        if course == "POSH":
            assert india, r
        elif course == "Anti-harassment":
            assert not india, r
        elif course == "Anti-harassment: managers' module":
            assert not india and e["employee_id"] in reports, r
        elif course == "Anti-bribery":
            assert e["department"] in ANTI_BRIBERY_DEPARTMENTS \
                or e["grade"] in ("L5", "L6"), r
        elif course == "Secure coding":
            assert e["department"] == "Engineering", r
        if course == "Code of Conduct":
            has_conduct.add(e["employee_id"])
    assert has_conduct == set(emps), "someone has no Code of Conduct"
    print("All training checks passed.")


# --- Pay and ratings --------------------------------------------------------------
def country(emp: dict) -> str:
    return "India" if emp["office"] in INDIA_OFFICES else "US"


def round_pay(pay: float, where: str) -> int:
    step = PAY_STEP[where]
    return int(round(pay / step) * step)


def raise_for(rng: random.Random, pay: int, emp: dict, year: int,
              rating: str) -> float:
    """This year's raise, as a fraction: the average raise, more for a
    better rating, more low in the pay range and less high in it
    (9.3.2), give or take a tenth."""
    where = country(emp)
    low, high = PAY_RANGES[where][emp["grade"]]
    position = (pay - low) / (high - low)  # 0 = the minimum, 1 = the max
    if position < 1 / 3:
        by_position = 1.1
    elif position < 2 / 3:
        by_position = 0.95
    elif position <= 1:
        by_position = 0.8
    else:  # already above the range
        by_position = 0.5
    average_factor = sum(s * RAISE_FACTOR[r]
                         for r, s in zip(RATINGS, RATING_SHARES))
    return (AVERAGE_RAISE[where, year] / average_factor
            * RAISE_FACTOR[rating] * by_position * rng.uniform(0.9, 1.1))


def build_pay(employees: list[dict], rng: random.Random
              ) -> tuple[list[dict], list[dict]]:
    """Each person's April ratings and pay history: the pay in effect on
    PAY_FROM (or at joining), then a raise every 1 July after a rating
    that earns one."""
    salaries, ratings = [], []
    for emp in employees:
        emp_id, where = emp["employee_id"], country(emp)
        joined = date.fromisoformat(emp["join_date"])
        low, high = PAY_RANGES[where][emp["grade"]]

        def pay_row(day: date, reason: str, pay: int):
            salaries.append({"employee_id": emp_id,
                             "effective_from": day.isoformat(),
                             "reason": reason, "annual_pay": pay,
                             "currency": CURRENCY[where]})

        if joined >= date(LAST_REVIEW.year, 1, 1):
            # Not rated in April 2024 (10.2.4): still on joining pay.
            pay = round_pay(low + rng.uniform(0.05, 0.45) * (high - low),
                            where)
            pay_row(joined, "joining", pay)
        else:  # higher in the range the longer they've been in the grade
            years = (LAST_REVIEW - joined).days / 365.25
            position = (min(0.5, 0.1 + 0.06 * years)
                        + rng.uniform(-0.08, 0.08))
            pay = round_pay(low + position * (high - low), where)
            pay_row(LAST_REVIEW, "annual_review", pay)

        for k, year in enumerate(REVIEW_YEARS):
            if joined >= date(year, 1, 1):
                continue  # joined on or after 1 January: not rated yet
            rating = (SCENARIO_RATINGS[emp_id][k]
                      if emp_id in SCENARIO_RATINGS
                      else rng.choices(RATINGS, RATING_SHARES)[0])
            ratings.append({"employee_id": emp_id, "review_year": year,
                            "rating": rating})
            if rating != NO_RAISE and date(year, 7, 1) <= TODAY:
                pay = round_pay(pay * (1 + raise_for(rng, pay, emp, year,
                                                     rating)), where)
                pay_row(date(year, 7, 1), "annual_review", pay)
    return salaries, ratings


def validate_pay(employees: list[dict], salaries: list[dict],
                 ratings: list[dict]):
    """Fail loudly if a pay change or rating breaks the Employee
    Handbook's rules (chapters 9 and 10)."""
    keys = [(s["employee_id"], s["effective_from"]) for s in salaries]
    assert len(set(keys)) == len(keys), "two pay changes on one day"
    rated = {(r["employee_id"], r["review_year"]): r["rating"]
             for r in ratings}
    assert len(rated) == len(ratings), "rated twice in one year"
    by_person = defaultdict(list)
    for s in salaries:
        by_person[s["employee_id"]].append(s)

    for e in employees:
        emp_id, where = e["employee_id"], country(e)
        low, high = PAY_RANGES[where][e["grade"]]
        for year in REVIEW_YEARS:  # rated if joined before 1 January
            rating = rated.get((emp_id, year))
            assert (rating is not None) == (
                e["join_date"] < f"{year}-01-01"), (emp_id, year)
            assert rating is None or rating in RATINGS, rating
            raised = any(s["effective_from"] == f"{year}-07-01"
                         for s in by_person[emp_id])
            assert raised == (rating not in (None, NO_RAISE)), \
                (emp_id, year, rating)

        mine = by_person[emp_id]
        assert mine, f"{emp_id}: no pay"
        first = mine[0]
        assert first["effective_from"] <= max(
            PAY_FROM.isoformat(), e["join_date"]), first
        if first["reason"] == "joining":
            assert first["effective_from"] == e["join_date"], first
        for before, s in zip([None] + mine, mine):
            assert s["currency"] == CURRENCY[where], s
            assert low <= s["annual_pay"] <= high * 1.1, s
            if before:
                assert s["effective_from"].endswith("-07-01"), s
                rise = s["annual_pay"] / before["annual_pay"] - 1
                assert 0 < rise <= 0.2, (s, rise)
    print("All pay and rating checks passed.")


# --- Projects ---------------------------------------------------------------------
def monday_from(day: date) -> date:
    """The first Monday on or after `day`."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def month_end(day: date) -> date:
    first_of_next = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def scenario_projects() -> tuple[list[dict], list[dict]]:
    """The original 40's projects and assignments, by hand (README
    scenarios). Project managers are named on the project, not assigned."""
    d = date
    projects = [  # name, client, industry, ODC, manager, start, end
        ("Card payments platform upgrade", "Amberleaf Bank", "banking",
         "yes", "AMS-1019", d(2024, 9, 2), d(2027, 6, 30)),
        ("Core banking data migration", "Cobalt Bay Bank", "banking",
         "yes", "AMS-1019", d(2024, 6, 3), d(2027, 3, 31)),
        ("Store analytics dashboards", "Peppercorn Stores", "retail",
         "no", "AMS-1010", d(2026, 11, 2), d(2027, 9, 30)),
        ("Loyalty app", "Marigold Mart", "retail",
         "yes", "AMS-1010", d(2024, 11, 4), d(2027, 3, 31)),
        ("Claims processing portal", "Corvana Hospitals", "healthcare",
         "no", "AMS-1010", d(2024, 10, 7), d(2026, 11, 30)),
        ("Delivery route planning", "Ferrowind Outfitters", "retail",
         "no", "AMS-1035", d(2025, 4, 7), d(2027, 4, 30)),
        ("Warehouse scanner app", "Ferrowind Outfitters", "retail",
         "no", "AMS-1035", d(2024, 8, 5), d(2026, 9, 30)),
    ]
    rows = [{"key": n, "name": name, "client": client, "industry": industry,
             "odc": odc, "project_manager_id": pm, "start": start,
             "end": end} for n, (name, client, industry, odc, pm, start,
                                 end) in enumerate(projects)]
    assignments = [  # project (0 = the first above), who, %, from, to
        # Pooja's team, in the Bengaluru banking ODC.
        (0, "AMS-1012", 100, d(2024, 9, 2), None),
        (0, "AMS-1015", 100, d(2024, 9, 2), None),  # Ananya
        (0, "AMS-1016", 100, d(2024, 9, 2), None),
        (0, "AMS-1020", 100, d(2024, 9, 2), None),
        # Lakshmi: left the banking ODC project on 30 Oct, a new one 2 Nov.
        (1, "AMS-1021", 100, d(2024, 6, 3), d(2026, 10, 30)),
        (2, "AMS-1021", 100, d(2026, 11, 2), None),
        # Amit's team, in the Pune retail ODC.
        (3, "AMS-1013", 100, d(2024, 11, 4), None),
        (3, "AMS-1024", 100, d(2024, 11, 4), None),
        (3, "AMS-1026", 100, d(2024, 11, 4), None),
        (3, "AMS-1025", 100, d(2026, 6, 15), None),
        (3, "AMS-1014", 100, d(2026, 8, 3), None),
        # Karthik's team: the project ends on 30 Nov 2026.
        (4, "AMS-1011", 100, d(2024, 10, 7), None),
        (4, "AMS-1018", 100, d(2024, 10, 7), None),  # Harish
        (4, "AMS-1017", 100, d(2025, 7, 21), None),
        # Austin; Daniel (a principal) splits his time.
        (5, "AMS-1034", 100, d(2025, 4, 7), None),
        (5, "AMS-1008", 50, d(2025, 4, 7), None),
        (5, "AMS-1032", 100, d(2026, 9, 28), None),
        (6, "AMS-1034", 100, d(2024, 8, 5), d(2025, 4, 4)),
        (6, "AMS-1008", 50, d(2024, 8, 5), d(2026, 9, 30)),
        # Brian: on no project since this one ended on 30 Sep 2026.
        (6, "AMS-1033", 100, d(2024, 8, 5), d(2026, 9, 30)),
    ]
    return rows, [{"project": p, "employee_id": e, "allocation_percent": a,
                   "start": s, "end": t} for p, e, a, s, t in assignments]


def build_projects(employees: list[dict], first_new: int,
                   rng: random.Random) -> tuple[list[dict], list[dict]]:
    """The 40's projects by hand, then the new teams': teams of one
    office share a project, some came from an earlier project, a few
    people rolled off or split their time 50/50."""
    projects, assignments = scenario_projects()
    new = employees[first_new:]
    reports = defaultdict(list)
    for e in new:
        reports[e["manager_id"]].append(e)
    used_names = {(p["client"], p["name"]) for p in projects}

    def project(office, teams, pm, start, end):
        india = office in INDIA_OFFICES
        if all(t[0]["department"] == "Engineering" for t in teams) \
                and rng.random() < INTERNAL_SHARE:
            client, industry = "", ""
        else:  # the client with the fewest projects so far
            choices = CLIENTS["India" if india else "US"]
            fewest = min(sum(p["client"] == c for p in projects)
                         for c, _ in choices)
            client, industry = rng.choice(
                [(c, i) for c, i in choices
                 if sum(p["client"] == c for p in projects) == fewest])
        names = [n for n in PROJECT_NAMES[industry]
                 if (client, n) not in used_names]
        name = base = (rng.choice(names) if names
                       else rng.choice(PROJECT_NAMES[industry]))
        phase = 2
        while (client, name) in used_names:  # a follow-on project
            name, phase = f"{base} phase {phase}", phase + 1
        used_names.add((client, name))
        odc = ("yes" if ODC_OFFICE.get(industry) == office
               and rng.random() < ODC_SHARE else "no")
        row = {"key": len(projects), "name": name, "client": client,
               "industry": industry, "odc": odc, "project_manager_id": pm,
               "start": start, "end": end, "office": office}
        projects.append(row)
        return row

    def assign(p, emp, allocation, start, end):
        row = {"project": p["key"], "employee_id": emp["employee_id"],
               "allocation_percent": allocation, "start": start,
               "end": end}
        assignments.append(row)
        return row

    split_people = []
    for office in OFFICES:
        leads = [e for e in new if e["office"] == office
                 and e["department"] in ON_PROJECTS and e["grade"] == "L4"]
        teams = [[lead] + reports[lead["employee_id"]] for lead in leads]
        rng.shuffle(teams)
        managers = [e for e in new if e["office"] == office
                    and e["department"] == "Delivery"
                    and e["grade"] in ("L4", "L5")] or [
            e for e in employees if e["department"] == "Delivery"
            and e["grade"] in ("L4", "L5")]  # none here: anyone's
        while teams:
            group = teams[:rng.randint(*TEAMS_PER_PROJECT)]
            teams = teams[len(group):]
            delivery = [t[0] for t in group
                        if t[0]["department"] == "Delivery"]
            pm = delivery[0] if delivery else rng.choice(managers)
            start = monday_from(random_day(rng, date(2023, 3, 1),
                                           date(2026, 6, 30)))
            end = month_end(TODAY + timedelta(days=30 * rng.randint(2, 24)))
            current = project(office, group, pm["employee_id"], start, end)
            moved = start < TODAY - timedelta(days=60) \
                and rng.random() < MOVED_SHARE
            team_from = start
            if moved:  # the teams came from an earlier project
                team_from = monday_from(random_day(
                    rng, max(start, date(2025, 2, 3)),
                    TODAY - timedelta(days=21)))
                earlier = project(office, group, pm["employee_id"],
                                  monday_from(random_day(
                                      rng, date(2023, 1, 2), team_from
                                      - timedelta(days=180))),
                                  team_from - timedelta(days=3))
            for person in (e for t in group for e in t):
                if person is pm:
                    continue
                joined = date.fromisoformat(person["join_date"])
                staffed = monday_from(joined + timedelta(days=14))
                if moved and staffed <= earlier["end"] - timedelta(days=14):
                    assign(earlier, person, 100,
                           max(earlier["start"], staffed), earlier["end"])
                begin = max(team_from, staffed)
                if begin > TODAY:
                    continue  # just joined: not on a project yet
                leaves = person["last_working_day"]
                until = (min(date.fromisoformat(leaves), current["end"])
                         if leaves else None)
                if until is None and person["grade"] != "L4" \
                        and begin <= TODAY - timedelta(days=45) \
                        and rng.random() < ROLLED_OFF_SHARE:
                    until = random_day(rng, max(begin + timedelta(days=30),
                                                TODAY - timedelta(days=60)),
                                       TODAY - timedelta(days=7))
                split = (until is None and person["grade"] in ("L3", "L4")
                         and person["department"] == "Engineering"
                         and rng.random() < SPLIT_SHARE)
                row = assign(current, person, 50 if split else 100, begin,
                             until)
                if split:
                    split_people.append((person, current, row))

    # A second project for the 50/50 people: another running one in the
    # same office.
    running = [p for p in projects[7:] if p["start"] <= TODAY < p["end"]]
    for person, first, row in split_people:
        others = [p for p in running
                  if p is not first and p["office"] == person["office"]]
        if not others:
            row["allocation_percent"] = 100
            continue
        other = rng.choice(others)
        assign(other, person, 50, max(row["start"], other["start"]), None)

    # Number the projects: the 40's first, then the rest by start date.
    ordered = projects[:7] + sorted(projects[7:], key=lambda p: (
        p["start"], p["client"], p["name"]))
    ids = {p["key"]: f"PRJ-{n:03d}" for n, p in enumerate(ordered, 1)}
    project_rows = [{"project_id": ids[p["key"]], "name": p["name"],
                     "client": p["client"], "industry": p["industry"],
                     "odc": p["odc"],
                     "project_manager_id": p["project_manager_id"],
                     "start_date": p["start"].isoformat(),
                     "end_date": p["end"].isoformat()} for p in ordered]
    first = [a for a in assignments if a["project"] < 7]
    rest = sorted((a for a in assignments if a["project"] >= 7),
                  key=lambda a: (a["employee_id"], a["start"],
                                 ids[a["project"]]))
    assignment_rows = [{"employee_id": a["employee_id"],
                        "project_id": ids[a["project"]],
                        "allocation_percent": a["allocation_percent"],
                        "start_date": a["start"].isoformat(),
                        "end_date": a["end"].isoformat() if a["end"]
                        else ""} for a in first + rest]
    return project_rows, assignment_rows


def validate_projects(employees: list[dict], projects: list[dict],
                      assignments: list[dict]):
    """Fail loudly if a project or assignment doesn't fit the people, its
    dates, or the ODC rules (Facilities 2.1.2, 2.2.2, 3.4)."""
    emps = {e["employee_id"]: e for e in employees}
    by_id = {p["project_id"]: p for p in projects}
    assert len(by_id) == len(projects), "duplicate project_id"
    names = [(p["client"], p["name"]) for p in projects]
    assert len(set(names)) == len(names), "two projects, one name"
    clients = {client: (where, industry) for where, rows in CLIENTS.items()
               for client, industry in rows}
    staffed = defaultdict(list)
    for a in assignments:
        staffed[a["project_id"]].append(a)

    for p in projects:
        assert p["start_date"] < p["end_date"], p
        assert p["end_date"] >= PROJECTS_FROM.isoformat(), p
        assert p["odc"] in ("yes", "no"), p
        pm = emps[p["project_manager_id"]]
        assert pm["department"] == "Delivery" \
            and pm["grade"] in ("L3", "L4", "L5"), p
        assert staffed[p["project_id"]], f"{p['project_id']}: nobody on it"
        where = None
        if p["client"]:
            where, industry = clients[p["client"]]
            assert p["industry"] == industry, p
        else:  # internal
            assert p["industry"] == "" and p["odc"] == "no", p
        if p["odc"] == "yes":
            assert p["industry"] in ODC_OFFICE, p
        for a in staffed[p["project_id"]]:
            e = emps[a["employee_id"]]
            assert a["employee_id"] != p["project_manager_id"], (p, a)
            if p["odc"] == "yes":  # an ODC is in one office
                assert e["office"] == ODC_OFFICE[p["industry"]], (p, a)
            if where:  # Indian clients from India, US clients from Austin
                assert (e["office"] in INDIA_OFFICES) == (where == "India")

    spans = defaultdict(list)
    for a in assignments:
        e, p = emps[a["employee_id"]], by_id[a["project_id"]]
        assert e["department"] in ON_PROJECTS, a
        assert e["grade"] in ("L1", "L2", "L3", "L4") \
            or e["job_title"] == "Principal", a
        end = a["end_date"] or p["end_date"]
        assert e["join_date"] <= a["start_date"] <= TODAY.isoformat(), a
        assert p["start_date"] <= a["start_date"] < end <= p["end_date"], a
        assert end >= PROJECTS_FROM.isoformat(), a
        assert not e["last_working_day"] or end <= e["last_working_day"], a
        assert a["allocation_percent"] in (50, 100), a
        spans[a["employee_id"]].append((a["start_date"], end,
                                        a["allocation_percent"]))
    for emp_id, mine in spans.items():  # never more than 100% at once
        for day, _, _ in mine:
            total = sum(pct for s, t, pct in mine if s <= day <= t)
            assert total <= 100, (emp_id, day, total)
    print("All project checks passed.")


def numbered_requests(requests: list[dict], first: int) -> list[dict]:
    """Sorted by start date, numbered LR-<first>.., ID first."""
    ordered = sorted(requests,
                     key=lambda r: (r["start_date"], r["employee_id"]))
    return [{"request_id": f"LR-{first + n:04d}", **r}
            for n, r in enumerate(ordered)]


# --- Checks --------------------------------------------------------------
def validate(employees, balances, requests, claims):
    """Fail loudly if any generated row breaks a policy rule."""
    emps = {e["employee_id"]: e for e in employees}
    for column in ("employee_id", "name", "email"):
        values = [e[column] for e in employees]
        assert len(set(values)) == len(values), f"duplicate {column}"
    for rows, column in ((requests, "request_id"), (claims, "claim_id")):
        values = [r[column] for r in rows]
        assert len(set(values)) == len(values), f"duplicate {column}"
    if len(employees) == DEFAULT_SIZE:  # the handbook's offices (2.2.1)
        for dept, split in OFFICE_SPLIT.items():
            have = tuple(sum(e["department"] == dept and e["office"] == o
                             for e in employees) for o in OFFICES)
            assert have == split, f"{dept}: {have}, not {split}"

    for e in employees:
        manager = e["manager_id"]
        assert not manager or manager in emps, f"{e['employee_id']}: " \
            "unknown manager"
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--employees", type=int, default=DEFAULT_SIZE,
                        help=f"company size (default {DEFAULT_SIZE}; "
                        f"{len(EMPLOYEES)} = the original people only)")
    total = parser.parse_args().employees
    assert total >= len(EMPLOYEES), f"at least {len(EMPLOYEES)} employees"

    rng = random.Random(SEED)
    holidays = load_holidays()

    # The original 40, exactly as before.
    employees = build_employees()
    emps = {e["employee_id"]: e for e in employees}

    builder = RequestBuilder(holidays)
    add_scenario_requests(builder, emps)
    add_generated_requests(builder, employees, rng)
    requests = numbered_requests(builder.requests, 1)

    balances = build_balances(employees, requests, rng)
    claims = build_claims(employees, rng)

    # The rest of the company, numbered after them.
    if total > len(employees):
        new_rng = random.Random(NEW_SEED)
        new = build_new_employees(employees, total, new_rng)
        new_builder = RequestBuilder(holidays)
        add_generated_requests(new_builder, new, new_rng)
        new_requests = numbered_requests(new_builder.requests,
                                         len(requests) + 1)
        balances += build_balances(new, new_requests, new_rng)
        last_trip = max(int(c["trip_id"][5:]) for c in claims)
        claims += build_new_claims(employees + new, new, new_rng,
                                   len(claims) + 1, last_trip + 1)
        employees += new
        requests += new_requests

    validate(employees, balances, requests, claims)
    private = build_private(employees, random.Random(PRIVATE_SEED))
    validate_private(employees, private)

    # Devices and tickets: the original 40 first, so their IDs never
    # change; tickets numbered by date within each group.
    emps = {e["employee_id"]: e for e in employees}
    assets = AssetBuilder(random.Random(ASSET_SEED))
    build_assets(assets, employees[:len(EMPLOYEES)], emps)
    split = len(assets.tickets)
    build_assets(assets, employees[len(EMPLOYEES):], emps)
    tickets = (numbered_tickets(assets.tickets[:split], 10001)
               + numbered_tickets(assets.tickets[split:], 10001 + split))
    validate_assets(employees, assets.assets, tickets)

    # Trainings: the original 40 first, numbered by day assigned.
    reports = {e["manager_id"] for e in employees if e["manager_id"]}
    learn_rng = random.Random(TRAINING_SEED)
    first = build_trainings(employees[:len(EMPLOYEES)], learn_rng, reports)
    rest = build_trainings(employees[len(EMPLOYEES):], learn_rng, reports)
    trainings = (numbered_trainings(first, 10001)
                 + numbered_trainings(rest, 10001 + len(first)))
    validate_trainings(employees, trainings, reports)

    # Pay and ratings: the original 40 first, so theirs never change.
    pay_rng = random.Random(PAY_SEED)
    salaries, ratings = build_pay(employees[:len(EMPLOYEES)], pay_rng)
    more_salaries, more_ratings = build_pay(employees[len(EMPLOYEES):],
                                            pay_rng)
    salaries += more_salaries
    ratings += more_ratings
    validate_pay(employees, salaries, ratings)

    # Projects: the 40's by hand, then the new teams'.
    projects, assignments = build_projects(employees, len(EMPLOYEES),
                                           random.Random(PROJECT_SEED))
    validate_projects(employees, projects, assignments)

    print(f"Writing data as of {TODAY} to {DATA_DIR}:")
    write_csv("employees.csv", employees)
    write_csv("leave_balances.csv", balances)
    write_csv("leave_requests.csv", requests)
    write_csv("expense_claims.csv", claims)
    write_csv("employee_private.csv", private)
    write_csv("assets.csv", assets.assets)
    write_csv("servicedesk_tickets.csv", tickets)
    write_csv("trainings.csv", trainings)
    write_csv("salaries.csv", salaries)
    write_csv("ratings.csv", ratings)
    write_csv("projects.csv", projects)
    write_csv("project_assignments.csv", assignments)


if __name__ == "__main__":
    main()
