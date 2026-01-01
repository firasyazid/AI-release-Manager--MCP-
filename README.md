# AI Release Manager (MCP-Powered Judge)

## Overview
The **AI Release Manager** is an intelligent quality gate agent designed to run within CI/CD pipelines (GitHub Actions). Unlike traditional scripts that fail on simple binary conditions (e.g., `exit 1` if coverage < 80%), this agent uses an **LLM (Large Language Model)** via the **Model Context Protocol (MCP)** to "reason" about the release.

It acts as a **Senior Site Reliability Engineer (SRE)** that reviews:
1.  Test Results (`test-results.xml`)
2.  Code Coverage (`coverage.xml`)
3.  Build Logs & Warnings
4.  Code Diffs

## Core Architecture

### 1. The "Judge" Agent
Use Google Gemini (or OpenAI) to analyze the artifacts. It produces:
*   **Release Score (0-100)**: A confidence metric.
*   **Decision**: `APPROVED`, `WARNING`, or `REJECTED`.
*   **Release Summary**: A Markdown report explaining the decision.

### 2. MCP Server (`ops/mcp_server.py`)
Provides the Agent with "Tools" to read the pipeline state:
*   `read_test_summary()`: Parses JUnit XML.
*   `read_coverage_report()`: Parses Cobertura/Jacoco XML.
*   `analyze_logs()`: Extracts errors and warnings from text logs.
*   `get_diff_impact()`: Analyzes the git diff.

## Directory Structure
```
AI Release Manager/
├── README.md           # This file
├── requirements.txt    # Dependencies (mcp, google-generativeai, pydantic)
├── main.py             # Entry point for the CI step
├── config.py           # Threshold configurations
└── mcp_server/         # The MCP Server implementation
    ├── server.py       # Server setup
    └── tools.py        # Tool definitions
```

## Workflow Integration
This project is designed to be called in a GitHub Actions workflow step between **Build** and **Deploy**.

```yaml
  - name: Run AI Release Manager
    env:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    run: |
      pip install -r ai_release_manager/requirements.txt
      python ai_release_manager/main.py --artifacts ./artifacts
```

## How it Decides
The agent follows a "Constitution":
1.  **Critical Failures**: Any failed test = Automatic REJECTION (unless override granted).
2.  **Coverage Drops**: >5% drop = REJECTION. <2% drop = WARNING.
3.  **Log anomalies**: "Exception" or "Error" in logs = WARNING.
4.  **Sentiment**: Does the changelog match the diff?

## Output
The script generates two files:
1.  `release_decision.json`: Machine-readable verdict (passed/failed).
2.  `release_summary.md`: Human-readable report to be posted to GitHub Checks/PRs.
