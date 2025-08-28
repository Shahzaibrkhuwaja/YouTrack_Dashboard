# Projects to include in the dashboard (YouTrack short codes)
ACTIVE_PROJECTS = [
    "APLUS",
    "AT",
    "AC",
    # "MEP",
]

# Period filters (for Created Date)
PERIOD_KEYS = (
    "current_month",
    "previous_month",
    "last_6_months",
    "last_1_year",
)

# Key -> UI label (for dropdowns etc.)
PERIOD_LABELS = {
    "current_month": "Current Month",
    "previous_month": "Previous Month",
    "last_6_months": "Last 6 Months",
    "last_1_year": "Last 1 Year",
}


# Task Types to exclude
EXCLUDED_TYPES = [
    "Deployment"
]