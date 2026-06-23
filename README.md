# stocks-serverless-pipeline
Serverless AWS stock-mover pipeline built for Pennymac TRE: Terraform-managed Lambda, DynamoDB, API Gateway, and S3 app that automates daily watchlist analysis, stores the biggest mover, and serves a 7-day dashboard with secure, documented cloud architecture.

# Stocks Serverless Pipeline
A serverless AWS stock-mover dashboard that automates daily watchlist analysis, stores the biggest mover, and serves a 7-day dashboard with secure, documented cloud architecture.

Live frontend:
http://stock-movers-dashboard-556183271380.s3-website-us-east-1.amazonaws.com

Live API:
https://86sc0f21kk.execute-api.us-east-1.amazonaws.com/movers

Example:
curl https://86sc0f21kk.execute-api.us-east-1.amazonaws.com/movers

# project goal
Project Goal

The goal of this project was to design, deploy, and document a serverless stock data pipeline using AWS Free Tier resources.

The watchlist is:

AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA

For each trading day, the ingestion Lambda checks the daily open and close prices for each ticker, calculates the percentage change, chooses the stock with the largest absolute movement, and saves that result.

Percentage change formula:

((close - open) / open) * 100

Example:

AAPL: +1.20%
TSLA: -4.10%
NVDA: +2.70%

Winner: TSLA, because |-4.10| is the largest absolute move.

Architecture
Amazon EventBridge
        |
        v
Ingestion Lambda
        |
        v
Massive Stock API
        |
        v
DynamoDB stock-movers table
        |
        v
API Lambda
        |
        v
API Gateway GET /movers
        |
        v
S3 Static Website Frontend

This separates the project into two main backend responsibilities:

Ingestion logic: runs on a schedule, fetches stock data, calculates the winner, and stores the result.
Retrieval logic: serves stored results to the frontend through a REST API.

That separation keeps the daily data-processing job independent from the API used by the website.

# AWS Services Used
Service	Purpose
AWS Lambda:	Runs the ingestion and API backend logic
Amazon EventBridge:	Triggers the ingestion Lambda on a schedule
Amazon DynamoDB:	Stores daily stock mover results
Amazon API Gateway:	Exposes the GET /movers endpoint
Amazon S3:	Hosts the static frontend website
AWS IAM:	Controls permissions between services
Amazon CloudWatch: Logs	Provides logging and debugging visibility
Terraform:	Defines and deploys AWS infrastructure as code

# How the Pipeline Works
EventBridge triggers the ingestion Lambda on a schedule.
The ingestion Lambda loops through the watchlist.
For each ticker, it requests daily stock data from the Massive API.
The Lambda calculates percentage change using open and close prices.
The stock with the largest absolute percentage move is selected.
The result is stored in DynamoDB with the date, ticker, percent change, and closing price.
API Gateway exposes GET /movers.
The API Lambda reads recent records from DynamoDB.
The frontend calls the API and displays the recent winners in a chart and table.


# API Design
GET /movers

Returns recent stock mover records.

Example response:

{
  "count": 2,
  "limit": 7,
  "movers": [
    {
      "date": "2026-06-22",
      "ticker": "AMZN",
      "percent_change": -3.04,
      "closing_price": 232.79
    },
    {
      "date": "2026-06-18",
      "ticker": "AMZN",
      "percent_change": 1.78,
      "closing_price": 244.39
    }
  ]
}
GET /movers?limit=3

The API supports an optional limit query parameter.

The default limit is 7 records, and the maximum allowed limit is capped at 30 records so the API cannot be asked for an unreasonable amount of data.

Example:

curl "https://86sc0f21kk.execute-api.us-east-1.amazonaws.com/movers?limit=3"

The response includes:

count   = number of records returned
limit   = requested or default record limit
movers  = actual stock mover data

The API also includes response headers for CORS, JSON formatting, short caching, and debugging.

# Frontend

The frontend is a static HTML, CSS, and JavaScript dashboard hosted on S3.

It displays:

the biggest recent mover
a bar chart of daily percentage changes
a table of recent winner records
green/red color coding for gains and losses
a visible data source label showing when the dashboard is using the live API

I kept the frontend lightweight on purpose. A full React or Next.js app would work, but for this challenge a static page is easier to deploy, cheaper to host, and still shows the full pipeline clearly.


#Repository Structure
stocks-serverless-pipeline/
├── frontend/
│   └── index.html
│
├── lambdas/
│   ├── api/
│   │   └── lambda_function.py
│   │
│   └── ingestion/
│       └── lambda_function.py
│
├── scripts/
│
├── terraform/
│   ├── api_gateway.tf
│   ├── dynamodb.tf
│   ├── frontend.tf
│   ├── lambda_api.tf
│   ├── lambda_ingestion.tf
│   ├── outputs.tf
│   └── provider.tf
│
├── .gitignore
├── README.md
└── requirements.txt


# IaC

All AWS resources are managed with Terraform.

The project avoids manual AWS Console setup for the deployed infrastructure. Terraform defines the S3 frontend hosting, Lambda functions, DynamoDB table, API Gateway route, EventBridge schedule, IAM permissions, and outputs.

Basic deployment flow:

cd terraform
terraform init
terraform fmt
terraform plan
terraform apply

After deployment, Terraform outputs the live API URL and frontend URL.

# Security Notes

I kept secrets out of the public repository.

The stock API key is stored locally and passed into the deployed environment through Terraform configuration, not hardcoded into Lambda source files or committed to GitHub.

Files such as .env, .tfvars, .auto.tfvars, Terraform state files, and Lambda zip artifacts are ignored so private credentials and local build files do not end up in the repo.

# Security-related decisions:

no API keys committed to GitHub
IAM permissions are scoped to the resources the Lambdas need
API Gateway only exposes the read endpoint needed by the frontend
CORS is enabled for frontend access
Terraform manages infrastructure changes instead of manual clicking

# Error Handling and Robustness

The API Lambda includes safeguards for common API issues:

supports a default record limit
validates malformed limit query parameters
caps large limit requests
converts DynamoDB Decimal values into JSON-safe numbers
returns a clear error message if the API cannot retrieve data
includes CORS headers so the frontend can call the API safely

For the current project scale, the API Lambda scans the DynamoDB table and sorts records in memory. That is acceptable here because the table stores only one winner per day, so the dataset remains small.

If this grew into a production system with years of stock records, I would redesign the table access pattern around a date-based query or a secondary index instead of scanning.

# Design Trade-Offs
Static frontend instead of React

I used a plain static frontend because the challenge is mainly about the serverless data pipeline, not frontend complexity. This keeps the app easy to deploy and easy to review.

DynamoDB scan for retrieval

The table stores one record per day, so a scan is simple and inexpensive at this scale. For a larger production dataset, I would use a query-first table design.

One daily winner per date

The project stores the single largest mover per day instead of storing every stock’s full raw response. This keeps the table small and focused on the dashboard requirement.

API returns up to 7 records by default

The challenge asks for recent history, so the API defaults to 7 records. I added a limit parameter to make the endpoint more flexible without changing the frontend.

# Local Development Notes

To work on the project locally:

git clone https://github.com/Brundachagari/stocks-serverless-pipeline.git
cd stocks-serverless-pipeline

Install Python dependencies if testing scripts locally:

pip install -r requirements.txt

For local stock API testing, create a local .env file:

STOCK_API_KEY=your_key_here

Do not commit .env.#