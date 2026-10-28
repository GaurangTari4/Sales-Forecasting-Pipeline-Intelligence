TERRITORIES = [
    ("TER-001", "North America East", "NA"), ("TER-002", "North America West", "NA"),
    ("TER-003", "United Kingdom", "EMEA"), ("TER-004", "DACH", "EMEA"),
    ("TER-005", "India", "APAC"), ("TER-006", "ANZ", "APAC"),
]
STAGES = [("PROSPECTING", "Prospecting", 1, False), ("QUALIFICATION", "Qualification", 2, False),
          ("DISCOVERY", "Discovery", 3, False), ("PROPOSAL", "Proposal", 4, False),
          ("NEGOTIATION", "Negotiation", 5, False), ("CLOSED_WON", "Closed Won", 6, True),
          ("CLOSED_LOST", "Closed Lost", 6, True)]
STAGE_PRIORS = {"PROSPECTING": .12, "QUALIFICATION": .24, "DISCOVERY": .38, "PROPOSAL": .55, "NEGOTIATION": .73, "CLOSED_WON": 1.0, "CLOSED_LOST": 0.0}
INDUSTRIES = ["TECHNOLOGY", "FINANCIAL_SERVICES", "HEALTHCARE", "MANUFACTURING", "RETAIL", "PROFESSIONAL_SERVICES"]
PRODUCTS = [("Analytics Cloud", "SUBSCRIPTION"), ("Workflow Suite", "SUBSCRIPTION"), ("Secure Connect", "SUBSCRIPTION"), ("Implementation Services", "SERVICES")]
FIRST = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Cameron", "Quinn"]
LAST = ["Shah", "Patel", "Singh", "Khan", "Gupta", "Mehta", "Iyer", "Rao"]
