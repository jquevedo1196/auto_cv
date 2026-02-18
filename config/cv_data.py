"""
Job Hunter Agent - CV Data
Your parsed CV as a structured dict, used by the AI engine to
generate personalized cover letters.
"""

CV_DATA = {
    "name": "Jesús Enrique Quevedo Torres",
    "title": "Principal DevOps Engineer / SRE",
    "email": "jenriqueqt@gmail.com",
    "phone": "+525587972475",
    "location": "Mexico City, Mexico",
    "open_to_relocation": True,
    "target_countries": ["Canada", "New Zealand", "Sweden", "Germany", "Poland", "US"],
    "languages": ["Spanish (native)", "English (professional)"],

    "summary": (
        "DevOps/SRE Principal Engineer with 9+ years of experience building scalable, "
        "secure, and reliable cloud platforms across AWS and OCI. Expert in Kubernetes, "
        "Docker, CI/CD automation, observability, incident response, and large-scale cloud "
        "migrations. Proven impact reducing deployment times, improving system reliability, "
        "and leading mission-critical DevOps transformations."
    ),

    "skills": {
        "programming":    ["Python", "NodeJS", "Java", "Shell"],
        "cloud":          ["AWS (ECR, EKS, ECS, S3, RDS, Lambda)", "OCI DevOps", "IaC"],
        "devops_sre":     ["GitHub Actions", "Jenkins", "Docker", "Kubernetes",
                           "Terraform", "Artifactory", "SonarQube", "Snyk", "Ansible"],
        "observability":  ["Dynatrace", "Grafana", "CloudWatch", "Kibana"],
        "mobile_cicd":    ["Fastlane"],
        "certifications": ["Oracle DevOps Certified"],
        "additional":     ["Flutter", "Dart", "Flet", "APEX"],
    },

    "experience": [
        {
            "title":    "Principal DevOps Engineer",
            "company":  "Oracle",
            "start":    "Apr 2025",
            "end":      "Present",
            "bullets": [
                "Designed and automated secure CI/CD pipelines using Jenkins, Ansible, Python, PL/SQL, and Shell.",
                "Led major migration initiatives from on-prem environments to Oracle Cloud Infrastructure (OCI).",
                "Implemented repository governance, branch strategy, and workflow automation using Visual Builder Studio.",
                "Developed automation tooling in Python to reduce manual deployment effort.",
                "Reduced CI/CD execution times by 35% through pipeline architecture redesign.",
            ],
        },
        {
            "title":    "DevOps & L2 Support Engineer",
            "company":  "Santander Bank USA (TCS & Cervantes Group)",
            "start":    "Feb 2024",
            "end":      "Apr 2025",
            "bullets": [
                "Ensured high system stability across AWS and on-prem platforms through incident response.",
                "Utilized Dynatrace, Grafana, Kibana, CloudWatch, and Lambda for performance analysis.",
                "Improved application reliability through root-cause diagnostics and Python automation workflows.",
            ],
        },
        {
            "title":    "Senior DevOps Engineer",
            "company":  "ALBO",
            "start":    "Oct 2023",
            "end":      "Jan 2024",
            "bullets": [
                "Implemented high-availability infrastructure using Kubernetes, Docker, EKS, ECS, and ECR.",
                "Automated deployments with Jenkins and Python, improving consistency and reducing human error.",
                "Migrated CI/CD operations from Bitbucket to Jenkins to standardize engineering workflows.",
                "Integrated Terraform IaC and GitHub Actions into multi-service deployment processes.",
            ],
        },
        {
            "title":    "Head of DevOps",
            "company":  "MACROPAY",
            "start":    "Jun 2022",
            "end":      "Oct 2023",
            "bullets": [
                "Defined and scaled DevOps workflows across mobile, serverless, MVC, and middleware systems.",
                "Managed AWS releases using Lambda, EKS, ECS, EC2, S3, RDS, and DynamoDB.",
                "Automated pipelines with Jenkins and Terraform, reducing release time from hours to minutes.",
                "Oversaw platform administration including Firebase, Apple Connect, and Google Play Console.",
            ],
        },
        {
            "title":    "DevOps Lead",
            "company":  "TV Azteca Digital",
            "start":    "Oct 2021",
            "end":      "Jun 2022",
            "bullets": [
                "Built CI/CD workflows for iOS and Android apps using Fastlane, AWS, GitHub Actions, and SonarQube.",
                "Automated multi-pipeline deployments using Jenkins, controlled via SmartSheet triggers.",
                "Increased mobile release frequency from weekly to daily.",
            ],
        },
        {
            "title":    "DevOps Area Founder & Developer Lead",
            "company":  "AIONTECH",
            "start":    "Jan 2018",
            "end":      "Oct 2021",
            "bullets": [
                "Established and led DevOps processes using Docker, Jenkins, Artifactory, and SonarQube in AWS.",
                "Developed backend services using Java EE, SpringBoot, Camel, Hibernate, and JPA.",
                "Built full-stack platforms for BFSI, retail, and government clients.",
            ],
        },
        {
            "title":    "Tester & Deployer",
            "company":  "AIONTECH",
            "start":    "Jul 2015",
            "end":      "Jan 2018",
            "bullets": [
                "Performed testing and deployments for financial institutions including HSBC and InvestaBank.",
                "Built Selenium automation frameworks for QA workflows.",
            ],
        },
    ],

    "education": [
        {
            "degree":  "Master's in Artificial Intelligence",
            "school":  "UNIR – Universidad Internacional de La Rioja",
            "status":  "In Progress",
        },
        {
            "degree":  "B.S. Computer Engineering",
            "school":  "IPN – ESIME Culhuacán",
            "year":    "2020",
        },
        {
            "degree":  "Digital Systems Technician",
            "school":  "IPN – CECyT 9",
            "year":    "2015",
        },
    ],

    # Key achievements to highlight in cover letters
    "key_achievements": [
        "Reduced CI/CD execution times by 35% at Oracle through pipeline architecture redesign",
        "Reduced release cycles from hours to minutes at MACROPAY using Jenkins + Terraform",
        "Scaled mobile release frequency from weekly to daily at TV Azteca",
        "Led entire DevOps area foundation at AIONTECH from scratch",
        "9+ years of hands-on experience with AWS, Kubernetes, and cloud-native architectures",
        "Currently working at Oracle on OCI cloud migrations",
    ],
}
