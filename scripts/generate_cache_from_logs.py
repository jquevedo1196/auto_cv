#!/usr/bin/env python3
"""
Parse agent logs from the 2026-03-26 run and generate a local cache file
to test the sync functionality.

This script extracts job data from the log output and creates
data/run_cache.json with all 297 jobs marked as unsynced (pending).

Usage:
    python scripts/generate_cache_from_logs.py
    python agent.py --sync   # then sync to Google Sheets
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# Output path
CACHE_PATH = Path(__file__).parent.parent / "data" / "run_cache.json"
RUN_ID = "run_20260326_015749_failed"
RUN_CREATED = "2026-03-26T01:57:49"

# All scored jobs extracted from the logs (title, company, country, score, url, source)
# Parsed from lines matching: "Job scored XX/100: Title @ Company"
# and cover letter lines matching: "Cover letter generated for Title @ Company (Country)"
# and manual apply lines matching: "[XX/100] Title @ Company (Country) → URL"

SCORED_JOBS = [
    # ── Canada ──
    {"title": "Sr Forward Deployed Engineer", "company": "Acceler8 Talent", "country": "Canada", "score": 42, "source": "linkedin"},
    {"title": "Platform Engineer / DevOps Engineer - Trading - $130,000-$250,000 CAD + Bonus", "company": "Hunter Bond", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "Senior DevOps Engineer", "company": "TELUS Digital AI Data Solutions", "country": "Canada", "score": 72, "source": "linkedin"},
    {"title": "Staff Site Reliability Engineer", "company": "Coalition, Inc.", "country": "Canada", "score": 78, "url": "https://www.linkedin.com/jobs/view/4388383477/", "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "Orion Innovation", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "Lead Software Engineer (Python and AWS)", "company": "Collabera", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "Senior Platform Engineer", "company": "Wagepoint", "country": "Canada", "score": 72, "source": "linkedin"},
    {"title": "Intr. Cloud Infrastructure Engineer", "company": "Akkodis", "country": "Canada", "score": 35, "source": "linkedin"},
    {"title": "Site Reliability Engineer", "company": "Atlantis IT Group", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "AI Automation Engineer", "company": "ESK Recruitment LTD", "country": "Canada", "score": 35, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "Top Hat", "country": "Canada", "score": 72, "source": "linkedin"},
    {"title": "AI Automation Engineer", "company": "Valsoft Corporation", "country": "Canada", "score": 45, "source": "linkedin"},
    {"title": "Staff Software Engineer - Grafana Cloud k6 | Canada | Remote", "company": "Grafana Labs", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "ZRG Careers", "country": "Canada", "score": 45, "source": "linkedin"},
    {"title": "Senior DevOps Engineer", "company": "Amyantek", "country": "Canada", "score": 45, "source": "linkedin"},
    {"title": "GenAI Developer -- DWIDC5657517", "company": "Compunnel Inc.", "country": "Canada", "score": 35, "source": "linkedin"},
    {"title": "Founding Software Engineer", "company": "Synapses Network", "country": "Canada", "score": 45, "source": "linkedin"},
    {"title": "Developer Level 3", "company": "Bevertec", "country": "Canada", "score": 35, "source": "linkedin"},
    {"title": "Senior Cloud Engineer", "company": "Manulife", "country": "Canada", "score": 72, "source": "linkedin"},
    {"title": "Senior Cloud Engineer", "company": "WELL Health Technologies Corp. (TSX: WELL)", "country": "Canada", "score": 68, "source": "linkedin"},
    {"title": "Senior Cloud Network Engineer", "company": "Telesat", "country": "Canada", "score": 45, "source": "linkedin"},
    {"title": "Sr Platform Engineer", "company": "Air Tek Inc", "country": "Canada", "score": 62, "source": "linkedin"},
    {"title": "Staff Solutions Engineer", "company": "Kong", "country": "Canada", "score": 68, "source": "linkedin"},
    # ── New Zealand ──
    {"title": "Senior DevOps Engineer", "company": "Socialite Recruitment Ltd.", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Technical Solutions Engineer - Payment / Web3 / PayFi", "company": "BetterPaymentNetwork", "country": "New Zealand", "score": 42, "source": "linkedin"},
    {"title": "AWS Cloud Engineer (9 months Fixed Term)", "company": "The Co-operative Bank", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Oracle Fusion Cloud Consultant", "company": "Infosys", "country": "New Zealand", "score": 28, "source": "linkedin"},
    {"title": "Full Stack Engineer(AI)", "company": "BNB Chain", "country": "New Zealand", "score": 32, "source": "linkedin"},
    {"title": "Senior Cloud Infrastructure Engineer", "company": "Jobgether", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Senior Cloud Engineer", "company": "Datacom", "country": "New Zealand", "score": 78, "url": "https://www.linkedin.com/jobs/view/4380302960/", "source": "linkedin"},
    {"title": "Senior Cloud & Automation Engineer", "company": "frankie", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Senior DevSecOps Engineer", "company": "Chiptech Ltd", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Team Manager - Fixed Term 12 months", "company": "Datacom", "country": "New Zealand", "score": 42, "source": "linkedin"},
    {"title": "Platform Engineer | Digital Engineering", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 78, "url": "https://www.seek.co.nz/job/91161687?type=standard&ref=search-standalone#sol=fe7880bfb454b31da3350d7af8e83b71934ae93e", "source": "seek"},
    {"title": "Technical Lead - Payments Switch", "company": "Paymark Ltd T/A Worldline NZ", "country": "New Zealand", "score": 42, "source": "linkedin"},
    {"title": "Senior Software Engineer | Payments", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 42, "source": "linkedin"},
    {"title": "Senior Engineer - Supersonic", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 32, "source": "linkedin"},
    {"title": "Senior Technical Lead, Hybrid Multi-Cloud", "company": "Health New Zealand - Te Whatu Ora", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "Potentia", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "Hays | Technology", "country": "New Zealand", "score": 72, "source": "linkedin"},
    {"title": "Infrastructure DevOps Engineer", "company": "Capgemini Australia Pty Ltd", "country": "New Zealand", "score": 78, "url": "https://www.seek.co.nz/job/91139558?type=standard&ref=search-standalone#sol=13bf936b2f0947b594205752f43f1303afe038d1", "source": "seek"},
    {"title": "Principal Developer - Full stack", "company": "Datacom", "country": "New Zealand", "score": 38, "source": "seek"},
    {"title": "Principal Developer - Full stack (dup)", "company": "Datacom", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Principal Engineer - Automation fixed term", "company": "Datacom", "country": "New Zealand", "score": 78, "url": "https://www.seek.co.nz/job/91132236?type=standard&ref=search-standalone#sol=a7bc0ee560c16e95d5e1a680c210d7d807215216", "source": "seek"},
    {"title": "Principal Engineer - Automation fixed term (dup)", "company": "Datacom", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "AWS Cloud Engineer (9 Month Fixed Term)", "company": "The Co-operative Bank", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior Full Stack Developer", "company": "Absolute IT Limited", "country": "New Zealand", "score": 35, "source": "seek"},
    {"title": "Senior DevOps Engineer", "company": "Kami Holdings Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Tech Lead (Integrations)", "company": "Talent Army", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Principal Product Engineer", "company": "Foster Moore International Ltd", "country": "New Zealand", "score": 48, "source": "seek"},
    {"title": "Back End Developer(Rust/Go)", "company": "BNB Chain", "country": "New Zealand", "score": 35, "source": "seek"},
    {"title": "Senior Site Reliability Engineer, ANZ", "company": "Partly", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior API and Integration Testing Engineer - Mulesoft & Java Stack", "company": "Walker Smith", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Senior Cloud & Automation Engineer (dup)", "company": "frankie", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Team Manager - Fixed Term 12 months (dup)", "company": "Datacom", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Software Developer", "company": "Private Advertiser", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Senior Software Engineer", "company": "Absolute IT Limited", "country": "New Zealand", "score": 45, "source": "seek"},
    {"title": "Senior Full Stack Developer (dup)", "company": "Younity", "country": "New Zealand", "score": 35, "source": "seek"},
    {"title": "Senior Software Engineer | Payments (dup)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Product Development Engineer", "company": "Fisher & Paykel Healthcare", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior Engineer - Supersonic (dup)", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 35, "source": "seek"},
    {"title": "Senior Data Engineer", "company": "Potentia", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "DevOps Engineer (dup)", "company": "Potentia", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior Software Engineer (dup)", "company": "Enable Global", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Infrastructure DevOps Engineer (dup2)", "company": "Capgemini Australia Pty Ltd", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Senior Systems Engineer", "company": "PODcom Limited", "country": "New Zealand", "score": 58, "source": "seek"},
    {"title": "Senior Test Engineer - Lending", "company": "Find Recruitment Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior QA Engineer", "company": "Cin7", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior Software Engineer (dup2)", "company": "Avanti Finance", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Full Stack Developer (dup2)", "company": "Absolute IT Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior DevOps Engineer (dup)", "company": "Kami Holdings Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior Mobile Engineer (iOS)", "company": "Air New Zealand", "country": "New Zealand", "score": 15, "source": "seek"},
    {"title": "Senior Software Developer C++", "company": "Windcave", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior Systems Engineer (dup)", "company": "Netsol", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Cloud Engineer - AWS", "company": "Datacom", "country": "New Zealand", "score": 78, "url": "https://www.linkedin.com/jobs/view/4380305864/", "source": "linkedin"},
    {"title": "Systems Engineer - Platforms & Integration", "company": "Westpac New Zealand", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Hybrid Cloud Engineer", "company": "Comrad", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Platform Engineer | Digital Engineering (dup2)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Technical Lead - Payments Switch (dup)", "company": "Paymark Ltd T/A Worldline NZ", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Software Engineer | Payments (dup2)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "IS Senior Infrastructure Engineer", "company": "Seeka Limited", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Environment Manager", "company": "Suncorp", "country": "New Zealand", "score": 48, "source": "seek"},
    {"title": "Senior Systems Engineer (dup2)", "company": "Reserve Bank of New Zealand", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Infrastructure DevOps Engineer (dup3)", "company": "Capgemini Australia Pty Ltd", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Associate Software Engineer", "company": "Starboard Maritime Intelligence", "country": "New Zealand", "score": 22, "source": "seek"},
    {"title": "Senior Systems Engineer (dup3)", "company": "RealNZ", "country": "New Zealand", "score": 58, "source": "seek"},
    {"title": "Systems Engineer - Platforms & Integration (dup)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "AWS Cloud Engineer (9 Month Fixed Term) (dup)", "company": "The Co-operative Bank", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior DevOps Engineer (dup2)", "company": "Kami Holdings Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Principal Product Engineer (dup)", "company": "Foster Moore International Ltd", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Automation Engineer", "company": "Tatua Co-operative Dairy Company Limited", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Senior Infrastructure Engineer - AIX | 2 Year Fixed Term", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Azure Platform Engineer", "company": "Randstad Digital", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Operations Engineer", "company": "Potentia", "country": "New Zealand", "score": 45, "source": "seek"},
    {"title": "Lead SRE Platform Engineer - Identity & Integration", "company": "ASB Bank Limited", "country": "New Zealand", "score": 78, "url": "https://www.seek.co.nz/job/91086906?type=standard&ref=search-standalone#sol=f73e151125bccfa31660d5ecf20859bf80919ed9", "source": "seek"},
    {"title": "Senior Civil Structural Engineer", "company": "Verbrec Ltd", "country": "New Zealand", "score": 5, "source": "seek"},
    {"title": "Office Administrator", "company": "SDL Group Ltd", "country": "New Zealand", "score": 5, "source": "seek"},
    {"title": "Team Manager - Fixed Term 12 months (dup2)", "company": "Datacom", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Software Developer (dup)", "company": "Private Advertiser", "country": "New Zealand", "score": 35, "source": "seek"},
    {"title": "Senior Project Manager", "company": "BNZ", "country": "New Zealand", "score": 15, "source": "seek"},
    {"title": "Data Engineer", "company": "AsureQuality Ltd", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Lead AI Engineer", "company": "Essential Bulk Liquids Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior Full Stack Developer (dup3)", "company": "Younity", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Platform Engineer | Digital Engineering (dup3)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Senior Software Engineer | Payments (dup3)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Engineer - Supersonic (dup2)", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Environment Manager (dup)", "company": "Suncorp", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Engineer - Supersonic (dup3)", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Mechanic & General rural engineer", "company": "AgFirst Engineering Ltd", "country": "New Zealand", "score": 5, "source": "seek"},
    {"title": "Cloud Infrastructure Engineer", "company": "Randstad New Zealand", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Hybrid Cloud Engineer (dup)", "company": "Comrad", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Head of Enterprise Application, Integration & Data", "company": "JOYN", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Team Manager - Fixed Term 12 months (dup3)", "company": "Datacom", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Data Engineer (dup)", "company": "AsureQuality Ltd", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Platform Engineer | Digital Engineering (dup4)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "IS Senior Infrastructure Engineer (dup)", "company": "Seeka Limited", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "DevOps Engineer (dup2)", "company": "Potentia", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Software Engineer", "company": "Turners Auto Retail Division", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Infrastructure DevOps Engineer (dup4)", "company": "Capgemini Australia Pty Ltd", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Senior Systems Engineer (dup4)", "company": "PODcom Limited", "country": "New Zealand", "score": 58, "source": "seek"},
    {"title": "Team Lead .Net", "company": "JOYN", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior Systems Engineer (dup5)", "company": "RealNZ", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Level 2 Support Engineer", "company": "Pure Logic Ltd", "country": "New Zealand", "score": 15, "source": "seek"},
    {"title": "AWS Cloud Engineer (9 Month Fixed Term) (dup2)", "company": "The Co-operative Bank", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior DevOps Engineer (dup3)", "company": "Kami Holdings Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Contract Test Engineer", "company": "Consult Recruitment - IT & Digital", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Level 2 Tech Support Engineer", "company": "connectnet", "country": "New Zealand", "score": 15, "source": "seek"},
    {"title": "HMC Engineer", "company": "Health New Zealand - Te Whatu Ora", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Software Engineer (dup)", "company": "ANZ Bank New Zealand Limited", "country": "New Zealand", "score": 62, "source": "seek"},
    {"title": "Software Engineer [Contract]", "company": "Talent Army", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Engineering Team Leader", "company": "Jobgether", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Director, Cloud Platform & Reliability Engineering", "company": "Visa", "country": "New Zealand", "score": 78, "url": "https://www.linkedin.com/jobs/view/4390826287/", "source": "linkedin"},
    {"title": "L2 Network Engineer – MSP, Cyber, Cloud & Infrastructure | NZ", "company": "Secure Agility Pty Ltd", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Senior Cloud & Automation Engineer (dup2)", "company": "frankie", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Senior Software Engineer (dup3)", "company": "Absolute IT Limited", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Full Stack Developer (dup4)", "company": "Younity", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "Platform Engineer | Digital Engineering (dup5)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Senior Software Engineer | Payments (dup4)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Engineer - Supersonic (dup4)", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Engineer - Supersonic (dup5)", "company": "Engage Recruitment Support", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "DevOps Engineer (dup3)", "company": "Potentia", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Software Engineer (dup2)", "company": "Turners Auto Retail Division", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Staff Engineer - Java", "company": "ANZ Bank New Zealand Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "DevOps Engineer (dup4)", "company": "Hays | Technology", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Infrastructure DevOps Engineer (dup5)", "company": "Capgemini Australia Pty Ltd", "country": "New Zealand", "score": 78, "source": "seek"},
    {"title": "Senior Frontend developer (Javascript, CSS, HTML, SSR, Golang)", "company": "salt", "country": "New Zealand", "score": 15, "source": "seek"},
    {"title": "Associate Software Engineer (dup)", "company": "Starboard Maritime Intelligence", "country": "New Zealand", "score": 28, "source": "seek"},
    {"title": "AWS Cloud Engineer (9 Month Fixed Term) (dup3)", "company": "The Co-operative Bank", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "AI Tech Lead", "company": "FundTap", "country": "New Zealand", "score": 32, "source": "seek"},
    {"title": "Senior DevOps Engineer (dup4)", "company": "Kami Holdings Limited", "country": "New Zealand", "score": 72, "source": "seek"},
    {"title": "Tech Lead (Integrations) (dup)", "company": "Talent Army", "country": "New Zealand", "score": 42, "source": "seek"},
    {"title": "Senior Infrastructure Engineer - AIX | 2 Year Fixed Term (dup)", "company": "Westpac New Zealand Limited", "country": "New Zealand", "score": 28, "source": "seek"},
    # ── Sweden ──
    {"title": "Staff Platform Engineer / Tech Lead (70% Hands-on)", "company": "Remote People", "country": "Sweden", "score": 62, "source": "linkedin"},
    {"title": "BackEnd Tech Lead", "company": "Mentor Talent Acquisition", "country": "Sweden", "score": 42, "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "Stott and May", "country": "Sweden", "score": 62, "source": "linkedin"},
    {"title": "Senior AWS Infrastructure & Security Engineer", "company": "REM Waste Management", "country": "Sweden", "score": 72, "source": "linkedin"},
    {"title": "Senior Python Engineer (Systems / Infrastructure)", "company": "Strativ Group", "country": "Sweden", "score": 42, "source": "linkedin"},
    {"title": "Senior DevOps Engineer", "company": "GlobalDots", "country": "Sweden", "score": 72, "source": "linkedin"},
    {"title": "Lead DevOps Engineer", "company": "Playnetic", "country": "Sweden", "score": 72, "source": "linkedin"},
    {"title": "Senior DevOps Engineer - Radian Arc", "company": "Submer", "country": "Sweden", "score": 72, "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer - Open Banking", "company": "Visa", "country": "Sweden", "score": 82, "url": "https://www.linkedin.com/jobs/view/4390170288/", "source": "linkedin"},
    {"title": "DevOps Engineer", "company": "Eccera Professionals AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "DevOps Engineer", "company": "Knightec Group AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30781324", "source": "arbetsformedlingen"},
    {"title": "DevOps Engineer/Architect", "company": "AFRY AB", "country": "Sweden", "score": 82, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30785700", "source": "arbetsformedlingen"},
    {"title": "DevOps Engineer", "company": "Mpya Sci & Tech AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "DevOps Engineer", "company": "Volvo Business Services AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30744277", "source": "arbetsformedlingen"},
    {"title": "DevOps Engineer", "company": "Nexer Telescope AB", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Senior DevOps Engineer", "company": "Explipro Group AB", "country": "Sweden", "score": 92, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30778528", "source": "arbetsformedlingen"},
    {"title": "Senior DevOps Engineer", "company": "Semicon Service Nordic AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Senior Devops Engineer", "company": "Knowit AB (Publ)", "country": "Sweden", "score": 82, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30699339", "source": "arbetsformedlingen"},
    {"title": "Senior Backend Developer / DevOps Engineer", "company": "Zpark Energy Systems AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30712821", "source": "arbetsformedlingen"},
    {"title": "Senior Azure Data Engineer", "company": "WeQube AB", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Senior Platform Engineer – OpenStack, Linux & Automation", "company": "Iver Accelerate AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30789997", "source": "arbetsformedlingen"},
    {"title": "Senior Observability Engineer", "company": "TEKsystems", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Senior Linux Infrastructure Engineer (Network & Virtualization)", "company": "XML International", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Founding AI Engineer - Up to 180k SEK per month", "company": "Few&Far", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Site Reliability Engineer", "company": "TEKEVER", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Principal Data Engineer", "company": "Nuitée", "country": "Sweden", "score": 32, "source": "arbetsformedlingen"},
    {"title": "Join Miss Group as a Site Reliability Engineer (SRE) – Remote", "company": "HOSTEK AB", "country": "Sweden", "score": 35, "source": "arbetsformedlingen"},
    {"title": "Join Miss Group as a Site Reliability Engineer (SRE) – Kungälv", "company": "HOSTEK AB", "country": "Sweden", "score": 35, "source": "arbetsformedlingen"},
    {"title": "Join Miss Group as a Site Reliability Engineer (SRE) – Karlskrona", "company": "HOSTEK AB", "country": "Sweden", "score": 35, "source": "arbetsformedlingen"},
    {"title": "Site Reliability Engineer/Cloud Engineer", "company": "Iver Accelerate AB", "country": "Sweden", "score": 92, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30758918", "source": "arbetsformedlingen"},
    {"title": "GTM Engineer", "company": "Oneflow AB", "country": "Sweden", "score": 25, "source": "arbetsformedlingen"},
    {"title": "AI Engineer", "company": "Epiminds AB", "country": "Sweden", "score": 28, "source": "arbetsformedlingen"},
    {"title": "Packaging Engineer", "company": "Incluso AB", "country": "Sweden", "score": 15, "source": "arbetsformedlingen"},
    {"title": "Software Engineer", "company": "Volvo Personvagnar Aktiebolag", "country": "Sweden", "score": 32, "source": "arbetsformedlingen"},
    {"title": "Cost Engineer", "company": "Coretura AB", "country": "Sweden", "score": 32, "source": "arbetsformedlingen"},
    {"title": "Process Engineer", "company": "AB Tetra Pak", "country": "Sweden", "score": 22, "source": "arbetsformedlingen"},
    {"title": "Data Engineer", "company": "Avaron AB", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Android Engineer", "company": "Svea Renewable Solar AB", "country": "Sweden", "score": 15, "source": "arbetsformedlingen"},
    {"title": "Maintenance Engineer", "company": "Nouryon Pulp and Performance Chemicals AB", "country": "Sweden", "score": 15, "source": "arbetsformedlingen"},
    {"title": "Data Engineer", "company": "Klarna Bank AB", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Senior Engineer - Financial Services Platform (London/Remote)", "company": "Flisher + Partners", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Senior Platform Engineer (Infrastructure)", "company": "Gelato", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Platform Engineer", "company": "Polismyndigheten", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30761050", "source": "arbetsformedlingen"},
    {"title": "Platform Engineer", "company": "Cambio Healthcare Systems AB", "country": "Sweden", "score": 45, "source": "arbetsformedlingen"},
    {"title": "Platform Engineer", "company": "Techrytera AB", "country": "Sweden", "score": 82, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30714805", "source": "arbetsformedlingen"},
    {"title": "CI/CD Platform Engineer", "company": "Avaron AB", "country": "Sweden", "score": 88, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30800936", "source": "arbetsformedlingen"},
    {"title": "Azure Platform Engineer", "company": "Luotea FM AB", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Platform Engineer – OpenShift", "company": "Svenska Kraftnät", "country": "Sweden", "score": 88, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30741222", "source": "arbetsformedlingen"},
    {"title": "Senior Infrastructure Domain Architect", "company": "H & M Hennes & Mauritz Gbc AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30748450", "source": "arbetsformedlingen"},
    {"title": "Senior Infrastructure Specialist – Azure Platform", "company": "Vitrolife Sweden AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30790558", "source": "arbetsformedlingen"},
    {"title": "IoT Engineer", "company": "Framtiden i Sverige AB", "country": "Sweden", "score": 42, "source": "arbetsformedlingen"},
    {"title": "Lead DevSecOps Engineer", "company": "Explore Group", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Solutions Architect / Technical Lead", "company": "Altenar", "country": "Sweden", "score": 48, "source": "arbetsformedlingen"},
    {"title": "Solutions Architect, Enterprise", "company": "Stripe", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Data & AI Platform Engineer – Python, Kubernetes, CI/CD", "company": "Friday Väst AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30725814", "source": "arbetsformedlingen"},
    {"title": "AI Cloud Engineer", "company": "Professional Galaxy AB", "country": "Sweden", "score": 78, "url": "https://arbetsformedlingen.se/platsbanken/annonser/30718503", "source": "arbetsformedlingen"},
    {"title": "Sr. DevOps Engineer (GCP) opening - AI Confidential Computing Startup", "company": "Skyrocket Ventures", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Senior Cloud Infrastructure Engineer", "company": "Jobgether", "country": "Sweden", "score": 68, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Engineer", "company": "Empiric", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Senior Cloud Security Engineer IAM & Cloud Infrastructure 16824", "company": "Veritaz AB", "country": "Sweden", "score": 62, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Solution Architect", "company": "Vattenfall AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Solution Architect (dup)", "company": "Vattenfall AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Solution Architect (dup2)", "company": "Vattenfall AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Solution Architect (dup3)", "company": "Vattenfall AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    {"title": "Infrastructure Specialist – Azure Platform", "company": "Vitrolife Sweden AB", "country": "Sweden", "score": 72, "source": "arbetsformedlingen"},
    # ── USA ──
    {"title": "Senior DevOps Engineer", "company": "Strativ Group", "country": "USA", "score": 58, "source": "linkedin"},
    {"title": "Infrastructure DevOps Enginner", "company": "PURVIEW", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Cloud Devops Engineer", "company": "Mondo", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Platform Engineer / DevOps Engineer - Trading - Elite FinTech - $150,000-$250,000 + Bonus", "company": "Hunter Bond", "country": "USA", "score": 68, "source": "linkedin"},
    {"title": "Lead DevOps Engineer", "company": "Resolve Tech Solutions", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Platform Engineer / DevOps Engineer – Trading - $130,000-$200,000 + Bonus", "company": "Hunter Bond", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Lead AWS DevSecOps / Platform Engineer", "company": "Hatch Pros", "country": "USA", "score": 68, "source": "linkedin"},
    {"title": "Sr. Site Reliability Engineer", "company": "RemoteHunter", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Staff Site Reliability Engineer (SRE)", "company": "The Cypress Group", "country": "USA", "score": 58, "source": "linkedin"},
    {"title": "Staff Engineer, Site Reliability", "company": "LinkedIn", "country": "USA", "score": 82, "url": "https://www.linkedin.com/jobs/view/4385497094/", "source": "linkedin"},
    {"title": "Site Reliability Engineer", "company": "Temu", "country": "USA", "score": 72, "source": "linkedin"},
    {"title": "SRE Team Lead - Trading - $150,000-$250,000 + Bonus", "company": "Hunter Bond", "country": "USA", "score": 72, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "Elios Talent", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "AAA Global", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Cloud Platform Engineer", "company": "BayOne Solutions", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "VAILEXA", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "Robert Half", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Platform Engineer – Cloud Infrastructure & Reliability", "company": "PacerPro", "country": "USA", "score": 58, "source": "linkedin"},
    {"title": "Software Engineer, Infrastructure Reliability", "company": "OpenAI", "country": "USA", "score": 78, "url": "https://www.linkedin.com/jobs/view/4385497094/", "source": "linkedin"},
    {"title": "Platform Engineer", "company": "RemoteHunter", "country": "USA", "score": 45, "source": "linkedin"},
    {"title": "Infrastructure Engineer – Quant Fund - Up to $220,000", "company": "Hunter Bond", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Cloud Engineer (AWS) – Data Platform - Public Sector Data Portal", "company": "CCI", "country": "USA", "score": 58, "source": "linkedin"},
    {"title": "Backend / Infrastructure Engineer", "company": "Tact", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Kubernetes Engineer", "company": "Centraprise", "country": "USA", "score": 72, "source": "linkedin"},
    {"title": "SRE / DevOps Manager", "company": "Upshop", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "Azure Kubernetes Services Engineer", "company": "VDart Digital", "country": "USA", "score": 62, "source": "linkedin"},
    {"title": "NVIDIA AI Infrastructure & Kubernetes Platform Engineer (DGX Systems)", "company": "Tech-Nique Partners", "country": "USA", "score": 72, "source": "linkedin"},
    {"title": "Kubernetes Platform Engineer – Control Plane & AI Infrastructure (hybrid)", "company": "Cisco", "country": "USA", "score": 82, "url": "https://www.linkedin.com/jobs/view/4390387481/", "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer", "company": "Zeta Global", "country": "USA", "score": 72, "source": "linkedin"},
    # ── Germany ──
    {"title": "Site Reliability Engineer (SRE) – Kubernetes / Platform | Berlin / Frankfurt | €110,000–120,000", "company": "Findr", "country": "Germany", "score": 78, "source": "linkedin"},
    {"title": "Founding Staff Engineer – Platform & Infrastructure (AI Voice)", "company": "CallPad", "country": "Germany", "score": 72, "source": "linkedin"},
    {"title": "Senior Cloud Infrastructure Engineer", "company": "Jobgether", "country": "Germany", "score": 72, "source": "linkedin"},
    {"title": "Senior Platform Engineer", "company": "Gigs", "country": "Germany", "score": 62, "source": "linkedin"},
    {"title": "Senior Platform Engineer (Infrastructure)", "company": "Gelato", "country": "Germany", "score": 72, "source": "linkedin"},
    {"title": "(Senior) Cloud Site Reliability Engineer (Scalability)", "company": "Scalable Capital", "country": "Germany", "score": 78, "source": "linkedin"},
    {"title": "Platform Architect", "company": "Cubiq Recruitment", "country": "Germany", "score": 42, "source": "linkedin"},
    # ── Poland ──
    {"title": "AWS DevOps Engineer", "company": "Remobi", "country": "Poland", "score": 78, "source": "linkedin"},
    {"title": "Senior Cloud Operations Engineer (L2/L3)", "company": "VBeyond Corporation", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "Senior / Staff Platform Engineer (AWS · Infrastructure · Distributed System)", "company": "Blue Language Labs", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "Senior Python Software Engineer", "company": "X4 Engineering", "country": "Poland", "score": 35, "source": "linkedin"},
    {"title": "Senior DevOps Engineer", "company": "Amaris Consulting", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "SRE Administrator and Infrastructure Automation", "company": "KBC Technologies Group", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "Infrastructure Automation Engineer", "company": "Infoplus Technologies UK Limited", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "Senior Software Engineer (Golang/Python) | Drug discovery Platform", "company": "Owen Thomas", "country": "Poland", "score": 42, "source": "linkedin"},
    {"title": "Lead BackEnd Engineer", "company": "Mentor Talent Acquisition", "country": "Poland", "score": 35, "source": "linkedin"},
    {"title": "Lead API/Platform Engineer", "company": "IDC", "country": "Poland", "score": 52, "source": "linkedin"},
    {"title": "Lead Platform Engineer (Cloud & MLOps)", "company": "Sigma IT Poland", "country": "Poland", "score": 72, "source": "linkedin"},
    {"title": "Senior Cloud Infrastructure Engineer", "company": "Jobgether", "country": "Poland", "score": 62, "source": "linkedin"},
    {"title": "Senior Data Engineer – RELOCATION TO MALTA", "company": "Archer", "country": "Poland", "score": 15, "source": "linkedin"},
    {"title": "Senior PHP Developer", "company": "Propel", "country": "Poland", "score": 15, "source": "linkedin"},
    {"title": "Infrastructure Engineer with Python", "company": "Sii Poland", "country": "Poland", "score": 62, "source": "linkedin"},
    # ── Mexico ──
    {"title": "Senior Site Reliability Engineer", "company": "Cloudbeds", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Lead Data DevOps Engineer", "company": "EPAM Systems", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Staff Engineer - Azure CloudOps Expert", "company": "Nagarro", "country": "Mexico", "score": 62, "source": "linkedin"},
    {"title": "Senior Cloud Developer (AWS/Java/Quarkus)", "company": "Qaracter México", "country": "Mexico", "score": 42, "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer, Observability", "company": "Chainlink Labs", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Principal Engineer, DevOps", "company": "ICIMS", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Senior AWS Platform Engineer", "company": "Cummins Latin America", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Lead Platform Engineer", "company": "Mastercard", "country": "Mexico", "score": 78, "url": "https://www.linkedin.com/jobs/view/4385758971/", "source": "linkedin"},
    {"title": "Java Support Engineer", "company": "New York Technology Partners", "country": "Mexico", "score": 28, "source": "linkedin"},
    {"title": "Senior Backend Engineer – Data Processing & Systems Integration", "company": "Enapsys", "country": "Mexico", "score": 42, "source": "linkedin"},
    {"title": "Desarrollador Java - OpenShift", "company": "Qaracter México", "country": "Mexico", "score": 32, "source": "linkedin"},
    {"title": "Data Engineer (Azure)", "company": "Interfell", "country": "Mexico", "score": 32, "source": "linkedin"},
    {"title": "Senior Software Engineer", "company": "Varicent", "country": "Mexico", "score": 45, "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer", "company": "SimCorp", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "DevOps Tech Lead (Serverless Platform & Engineering Enablement)", "company": "AstraZeneca", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer (dup)", "company": "Cloudbeds", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Platform Engineer", "company": "GeorgiaTEK Systems Inc.", "country": "Mexico", "score": 45, "source": "linkedin"},
    {"title": "Cloud Data Engineer", "company": "HCLTech", "country": "Mexico", "score": 42, "source": "linkedin"},
    {"title": "Lead Data DevOps Engineer (dup)", "company": "EPAM Systems", "country": "Mexico", "score": 72, "source": "linkedin"},
    {"title": "Platform Systems Engineer", "company": "Teradata", "country": "Mexico", "score": 62, "source": "linkedin"},
    {"title": "Infrastructure Engineer", "company": "Pyramid Consulting, Inc", "country": "Mexico", "score": 45, "source": "linkedin"},
    {"title": "Cloud Platform Engineer", "company": "Zurich Insurance", "country": "Mexico", "score": 68, "source": "linkedin"},
    {"title": "Lead Data DevOps Engineer (AWS)", "company": "EPAM Systems", "country": "Mexico", "score": 78, "source": "linkedin"},
    {"title": "Senior Site Reliability Engineer (dup2)", "company": "Thomson Reuters México", "country": "Mexico", "score": 72, "source": "linkedin"},
]


def generate_job_id(title: str, company: str, url: str) -> str:
    """Generate the same job_id as JobPosting.__post_init__"""
    return hashlib.md5(f"{title}{company}{url}".encode()).hexdigest()[:12]


def job_to_row(job: dict) -> list:
    """Convert a parsed job dict to a sheet-compatible row."""
    url = job.get("url", f"https://example.com/job/{job['title'][:20]}")
    job_id = generate_job_id(job["title"], job["company"], url)
    return [
        job_id,                          # Job ID
        job["title"],                    # Title
        job["company"],                  # Company
        "",                              # Location (not in logs)
        job["country"],                  # Country
        job.get("source", "linkedin"),   # Source
        job["score"],                    # Score
        "scored" if job["score"] >= 80 else "found",  # Status
        "False",                         # Easy Apply
        "N/A",                           # Salary
        "2026-03-26",                    # Posted Date
        "",                              # Applied Date
        url,                             # URL
        "",                              # Cover Letter Preview
    ]


def main():
    cache = {
        "runs": {
            RUN_ID: {
                "created_at": RUN_CREATED,
                "jobs": {}
            }
        }
    }

    run_jobs = cache["runs"][RUN_ID]["jobs"]

    for job in SCORED_JOBS:
        url = job.get("url", f"https://example.com/job/{job['title'][:20]}")
        job_id = generate_job_id(job["title"], job["company"], url)
        row = job_to_row(job)

        run_jobs[job_id] = {
            "synced": False,
            "synced_at": None,
            "row": row,
        }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total = len(run_jobs)
    print(f"✅ Generated {CACHE_PATH}")
    print(f"   Run ID:  {RUN_ID}")
    print(f"   Jobs:    {total}")
    print(f"   Pending: {total} (all unsynced)")
    print()
    print("To sync to Google Sheets, run:")
    print("   python agent.py --sync")


if __name__ == "__main__":
    main()
