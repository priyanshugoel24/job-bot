"""
Production config — committed to git.
Sensitive values (API keys, passwords) are read from environment variables.
Set these in your Railway/Render dashboard before deploying.

Required env vars:
  GEMINI_API_KEY       — Google AI Studio key (aistudio.google.com/app/apikey)

Optional (only needed if you trigger scraping from the cloud):
  LINKEDIN_EMAIL / LINKEDIN_PASSWORD
  NAUKRI_EMAIL  / NAUKRI_PASSWORD

Optional overrides:
  OUTPUT_DIR           — default: "output"
"""

import os

# ── Paths ────────────────────────────────────────────────
OUTPUT_DIR        = os.environ.get("OUTPUT_DIR", "output")
JOBS_FILE         = os.path.join(OUTPUT_DIR, "jobs.json")
APPLICATIONS_FILE = os.path.join(OUTPUT_DIR, "applications.json")
COVER_LETTERS_DIR = os.path.join(OUTPUT_DIR, "cover_letters")

# ── Secrets (env vars only in production) ────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

CREDENTIALS = {
    "linkedin": {
        "email":    os.environ.get("LINKEDIN_EMAIL", ""),
        "password": os.environ.get("LINKEDIN_PASSWORD", ""),
    },
    "naukri": {
        "email":    os.environ.get("NAUKRI_EMAIL", ""),
        "password": os.environ.get("NAUKRI_PASSWORD", ""),
    },
}

# ── Candidate profile (not sensitive — treat like a public CV) ────
PROFILE = {
    "name":    "Priyanshu Goel",
    "email":   "priyanshugoel24@gmail.com",
    "phone":   "+91 9625086105",
    "linkedin": "https://www.linkedin.com/in/priyanshu-goel-25b705258",
    "github":   "https://github.com/priyanshugoel24",
    "college":  "Delhi Technological University",
    "degree":   "B.Tech Computer Science",
    "cgpa":     "8.36",
    "grad_year": "May 2026",

    "current_role":      "Software Developer Intern (Backend)",
    "current_company":   "Paytm",
    "current_ctc":       "12 LPA",
    "promoting_to":      "SDE-1",
    "promotion_timeline": "~6 weeks",

    "target_ctc_min": 20,
    "target_ctc_max": 40,

    "skills": [
        "Python", "TypeScript", "JavaScript", "C++", "C", "SQL",
        "Next.js", "PostgreSQL", "ASP.NET Core", "Prisma", "React",
        "Scikit-Learn", "Pandas", "NumPy", "Matplotlib",
        "Git", "GitHub", "Vercel", "Supabase", "Postman",
        "REST APIs", "Agile", "Unit Testing", "Data Structures",
        "Algorithms", "System Design", "Machine Learning",
    ],

    "experiences": [
        {
            "company": "Paytm",
            "role": "Software Developer Intern (Backend)",
            "duration": "Jan 2026 – Present",
            "highlights": [
                "Building high-scale backend systems serving millions of users",
                "Working with distributed systems, REST APIs, and databases",
                "Transitioning to full-time SDE-1 role",
            ],
        },
        {
            "company": "Securiton India Private Ltd",
            "role": "Systems Trainee — Development",
            "duration": "Dec 2024 – Feb 2025",
            "highlights": [
                "Built ticketing portal using Angular, ASP.NET Core, and SQL",
                "Implemented UI components and API integrations",
                "Enhanced unit test coverage across critical modules",
                "5-member Agile team, sprint-based delivery",
            ],
        },
    ],

    "projects": [
        {
            "name": "HackFlow",
            "description": "Real-time collaboration platform for hackathons",
            "stack": "Next.js, TypeScript, Supabase, Prisma, Ably, Gemini API, Tailwind CSS",
            "highlights": [
                "Improved platform performance by 35% via caching, memoization, lazy loading",
                "Integrated AI features using Gemini API",
                "Deployed on Vercel for global scalability",
                "Live product with real users",
            ],
            "url": "https://github.com/priyanshugoel24/hackflow",
        },
        {
            "name": "SpendWise",
            "description": "ML pipeline for transaction categorization",
            "stack": "Python, Scikit-Learn, Pandas, NumPy, Matplotlib, joblib",
            "highlights": [
                "90% accuracy on transaction categorization",
                "Designed reusable TF-IDF + numeric feature preprocessing pipelines",
                "Benchmarked Logistic Regression vs Naive Bayes",
            ],
            "url": "https://github.com/priyanshugoel24/spendwise",
        },
    ],

    "achievements": [
        "Top 50 out of 500+ teams at Vihaan 7.0 (DTU official hackathon)",
        "PR Coordinator & Chief Video Editor, Pratibimb–DTU",
    ],
}

# ── Search filters ────────────────────────────────────────
SEARCH_FILTERS = {
    "role_priorities": [
        "Software Developer", "Software Engineer", "SDE", "SWE",
        "Backend Developer", "Backend Engineer", "Full Stack Developer",
    ],
    "excluded_roles": [
        "intern", "internship", "senior", "sr.", "lead", "manager",
        "principal", "staff", "director", "architect", "frontend only",
    ],
    "locations": [
        "Noida", "Gurgaon", "Gurugram", "Bangalore", "Bengaluru",
        "Hyderabad", "Pune", "Remote", "Work from home",
    ],
    "min_ctc_lpa": 20,
    "experience_max_years": 1,
    "target_companies": {
        "tier_1_mnc": [
            "Google", "Microsoft", "Amazon", "Meta", "Apple", "Adobe",
            "Oracle", "Salesforce", "Goldman Sachs", "Morgan Stanley",
            "JPMorgan", "Atlassian", "Qualcomm", "Intel", "Samsung",
        ],
        "tier_1_indian": [
            "Flipkart", "Paytm", "Zomato", "Swiggy", "CRED", "Razorpay",
            "PhonePe", "Meesho", "Zepto", "Groww", "Ola", "Nykaa",
            "BharatPe", "Chargebee", "Freshworks", "Zoho", "InMobi",
            "Dream11", "MPL", "Vedantu", "Unacademy", "Byju's",
        ],
        "high_paying_startups": [
            "Postman", "BrowserStack", "Setu", "Slintel", "Darwinbox",
            "Leadsquared", "Cleartax", "Lendingkart", "Slice", "Fi",
            "Jupiter", "Jar", "M2P", "Cashfree", "Instamojo",
        ],
    },
    "positive_keywords": [
        "competitive compensation", "esop", "equity", "stock options",
        "top talent", "best engineers", "scale", "millions of users",
        "high growth", "series b", "series c", "funded",
    ],
}
