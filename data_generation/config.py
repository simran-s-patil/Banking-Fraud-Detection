"""Settings for Phase 2 synthetic data generation.

Everything tunable lives here: counts, rates, ranges and name pools. All data is
synthetic. generate_data.py and validate_data.py both import this file.
"""
from datetime import date

# ---- Command-line defaults -------------------------------------------------
DEFAULT_SEED = 42
DEFAULT_CUSTOMERS = 500
DEFAULT_ACCOUNTS = 800
DEFAULT_MERCHANTS = 60
DEFAULT_TRANSACTIONS = 20000

# ---- Fixed date window (no current time is ever used) ----------------------
WINDOW_START = date(2025, 1, 1)
WINDOW_END = date(2025, 12, 31)
BATCH_SIZE = 500                      # max rows per INSERT statement

# ---- Customers and accounts ------------------------------------------------
DOB_MIN = date(1950, 1, 1)            # everyone is an adult (oldest/youngest bound)
DOB_MAX = date(2003, 12, 31)          # adult (18+) even on 2022-01-01, the earliest customer date
CUSTOMER_EARLY_SHARE = 0.80           # share of customers created before the window
CUSTOMER_EARLY_RANGE = (date(2022, 1, 1), date(2024, 12, 31))
CUSTOMER_LATE_RANGE = (date(2025, 1, 1), date(2025, 9, 30))
FIRST_ACCOUNT_DELAY_DAYS = (0, 14)    # account opened this long after customer
EXTRA_ACCOUNT_DELAY_DAYS = (0, 300)
ACCOUNT_LATEST_OPEN = date(2025, 10, 31)
CURRENT_ACCOUNT_SHARE = 0.15
ACCOUNT_STATUS_MIX = [("ACTIVE", 0.92), ("DORMANT", 0.04), ("FROZEN", 0.02), ("CLOSED", 0.02)]
# Opening balance and typical transaction size (median, in rupees)
OPENING_BALANCE_MEDIAN = {"Savings": 200000, "Current": 1500000}
OPENING_BALANCE_SIGMA = 0.7
OPENING_BUFFER_MULT = 300             # opening balance is at least this many typical amounts
TYPICAL_AMOUNT_MEDIAN = {"Savings": 1500, "Current": 6000}
TYPICAL_AMOUNT_SIGMA = 0.5            # spread between accounts
AMOUNT_NOISE_SIGMA = 0.9              # spread within one account
SMALL_PAYMENT_SHARE = 0.06            # everyday Rs 1-30 payments among normal rows
NORMAL_ROUND_SHARE = 0.15             # normal rows rounded down to a multiple of Rs 100
FAN_OUT_ROUND_SHARE = 0.30            # share of fan_out rows rounded to Rs 100
PAYOUT_ROUND_SHARE = 0.50             # share of business_payouts rows rounded to Rs 100
AMOUNT_CAP = 500000                   # no single transaction above this (rupees)

# ---- Transaction mix -------------------------------------------------------
P2P_SHARE = 0.60                      # the rest is CNP_ECOM
P2P_RECEIVER_MIX = [0.40, 0.25, 0.35]  # account only / account + its UPI / external UPI only
CNP_MERCHANT_NULL_RATE = 0.02         # documented edge case: CNP row without merchant
CNP_FIELD_NULL_RATE = 0.05            # device / IP / location / token missing (each)
STATUS_PROBS = [("SUCCESS", 0.90), ("FAILED", 0.05), ("PENDING", 0.03), ("REVERSED", 0.02)]
HOUR_WEIGHTS = [0.2, 0.1, 0.1, 0.1, 0.15, 0.3, 0.8, 1.5, 2.5, 3.5, 4, 4, 4.5, 4,
                3.5, 3.5, 4, 4.5, 5, 5, 4.5, 3.5, 2, 1]
NIGHT_HOURS = (0, 1, 2, 3, 4, 5)
NIGHT_NOISE = 0.15                    # share of non-odd-hour fraud/edge groups at night
FESTIVAL_DAYS = [date(2025, 1, 14), date(2025, 3, 14), date(2025, 8, 27),
                 date(2025, 10, 20), date(2025, 12, 25)]

# ---- Labels: scenarios and patterns ---------------------------------------
FRAUD_RATE = 0.03
EDGE_RATE = 0.05                      # legitimate look-alikes
# (fraud pattern, legitimate look-alike, weight)
PATTERN_PAIRS = [
    ("high_amount",       "large_planned_purchase",    0.18),
    ("velocity_burst",    "festival_burst",            0.17),
    ("odd_hour",          "night_shift",               0.15),
    ("fan_out",           "business_payouts",          0.15),
    ("merchant_anomaly",  "new_merchant_trial",        0.12),
    ("card_testing",      "small_recurring_payments",  0.12),
    ("device_geo_change", "travel_purchase",           0.11),
]
FRAUD_PATTERNS = [p[0] for p in PATTERN_PAIRS]
EDGE_PATTERNS = [p[1] for p in PATTERN_PAIRS]
HIGH_RISK_CATEGORIES = ["Gaming", "Digital Goods", "Jewellery", "Electronics"]

# ---- Validation tolerances -------------------------------------------------
RATE_TOLERANCE = 0.005                # scenario share, absolute
PATTERN_TOLERANCE_ABS = 3             # pattern count: max(abs, rel * expected)
PATTERN_TOLERANCE_REL = 0.10
P2P_SHARE_TOLERANCE = 0.03
STATUS_GAP_TOLERANCE = 0.05           # fraud vs legit status share gap
STATUS_GAP_MIN_ROWS = 100             # only checked when fraud rows >= this
SIMPLE_RULE_MAX_PRECISION = 0.90      # no simple rule may reach this
SIMPLE_HIGH_AMOUNT = 50000            # rule 1: amount >= this (rupees)
SIMPLE_BURST_COUNT = 4                # rule 3: this many txns by one sender ...
SIMPLE_BURST_MINUTES = 10             # ... inside this window

# ---- Synthetic identity pools ---------------------------------------------
FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Ishaan", "Rahul",
               "Siddharth", "Nikhil", "Varun", "Manish", "Anil", "Suresh", "Deepak", "Pranav",
               "Ananya", "Diya", "Meera", "Priya", "Kavya", "Sneha", "Neha", "Pooja",
               "Riya", "Isha", "Lakshmi", "Sunita", "Divya", "Aishwarya", "Tanvi", "Nisha",
               "Farhan", "Zoya", "Imran", "Ayesha", "Gurpreet", "Simran", "Joseph", "Maria"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Gupta", "Singh",
              "Kulkarni", "Desai", "Mehta", "Joshi", "Rao", "Menon", "Pillai", "Bose",
              "Banerjee", "Chatterjee", "Das", "Khan", "Ansari", "Shaikh", "Gill", "Kaur",
              "D'Souza", "Fernandes", "O'Neil", "Thomas", "George", "Hegde", "Shetty", "Naidu"]
CITIES = [("Bengaluru", "Karnataka"), ("Mysuru", "Karnataka"), ("Mumbai", "Maharashtra"),
          ("Pune", "Maharashtra"), ("Chennai", "Tamil Nadu"), ("Hyderabad", "Telangana"),
          ("Kochi", "Kerala"), ("Delhi", "Delhi"), ("Kolkata", "West Bengal"),
          ("Ahmedabad", "Gujarat"), ("Jaipur", "Rajasthan"), ("Lucknow", "Uttar Pradesh")]
STREETS = ["Imaginary Lane", "Sample Road", "Synthetic Avenue", "Testing Street",
           "Fictional Cross", "Demo Layout", "Placeholder Nagar", "Mock Colony"]
UPI_WORDS = ["ravi", "meera", "kiran", "asha", "gopal", "latha", "farid", "sana",
             "mohan", "geeta", "tarun", "usha"]
UPI_DOMAIN = "synthupi"
EMAIL_DOMAIN = "example.com"
IP_PREFIXES = ["192.0.2.", "198.51.100.", "203.0.113."]   # RFC 5737 documentation ranges
PHONE_PREFIX = "00000"                # non-routable
FIRST_ACCOUNT_NUMBER = 100000000001

# ---- Merchants: category -> (amount factor, name nouns) --------------------
MERCHANT_CATEGORIES = {
    "Electronics":   (3.0, ["Gadget Hub", "Circuit World", "Volt Store"]),
    "Groceries":     (0.6, ["Fresh Basket", "Daily Mart", "Green Cart"]),
    "Fashion":       (1.2, ["Style Loom", "Thread House", "Urban Wear"]),
    "Travel":        (2.5, ["Trip Wings", "Journey Desk", "Route Planner"]),
    "Food Delivery": (0.5, ["Tasty Box", "Quick Bites", "Spice Route"]),
    "Gaming":        (0.8, ["Pixel Arena", "Level Up", "Joystick Zone"]),
    "Digital Goods": (0.7, ["App Vault", "Stream Pass", "E-Book Shelf"]),
    "Jewellery":     (4.0, ["Gold Leaf", "Silver Arc", "Gem Gallery"]),
    "Utilities":     (1.0, ["Power Pay", "Water Desk", "Net Bill"]),
    "Pharmacy":      (0.7, ["Care Chemist", "Well Pharma", "Health Shelf"]),
    "Education":     (1.5, ["Learn Lab", "Study Path", "Skill Forge"]),
    "Entertainment": (0.9, ["Show Time", "Movie Bay", "Fun Park"]),
}
MERCHANT_PREFIXES = ["Blue", "Red", "Lotus", "Maple", "Nova", "Zen", "Orbit", "Cedar",
                     "Amber", "Delta", "Echo", "Jade", "Karma", "Lumen", "Pearl", "Sunrise"]
MERCHANT_WEBSITE_NULL_RATE = 0.10
