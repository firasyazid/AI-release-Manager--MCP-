import os
import argparse
import json
import sys
from google import genai
from google.genai import types
from src.tools.parsers import parse_junit_xml, parse_cobertura_xml, read_security_config

# --- Configuration ---
MIN_COVERAGE_THRESHOLD = 0.75
MAX_FACE_THRESHOLD = 0.55
MODEL_NAME = "gemini-3-flash-preview"

def main():
    parser = argparse.ArgumentParser(description="AI Release Manager Agent")
    parser.add_argument("--artifacts", required=True, help="Path to artifacts directory")
    parser.add_argument("--repo-root", required=True, help="Path to repo root")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set.")
        sys.exit(1)

    # Initialize New Client
    client = genai.Client(api_key=api_key)

    print(f"[INFO] Starting AI Release Manager (Model: {MODEL_NAME})...")
    
    # Paths
    test_xml = os.path.join(args.artifacts, "test-results.xml")
    cov_xml = os.path.join(args.artifacts, "coverage.xml")
    config_path = os.path.join(args.repo_root, "Face_detection_back/app/config.py")

    # 1. Gather Intelligence
    print(f"[INFO] Reading Test Results from: {test_xml}")
    try:
        test_data = parse_junit_xml(test_xml)
        print(f"[INFO] Tests: {test_data.total} total, {test_data.failures} failed")
    except Exception as e:
        print(f"[WARN] Failed to parse tests: {e}")
        test_data = None

    print(f"[INFO] Reading Coverage from: {cov_xml}")
    try:
        cov_data = parse_cobertura_xml(cov_xml)
        print(f"[INFO] Coverage: {cov_data.line_rate:.2%}")
    except Exception as e:
        print(f"[WARN] Failed to parse coverage: {e}")
        cov_data = None

    print(f"[INFO] Reading Security Config from: {config_path}")
    sec_config = read_security_config(config_path)
    print(f"[INFO] Security Threshold: {sec_config.face_threshold}")

    # 2. Construct Enhanced Prompt
    prompt = f"""
    You are a Senior Release Manager and Site Reliability Engineer reviewing a production deployment for a critical Face Verification System.
    
    ## MISSION
    Analyze the CI/CD pipeline data and produce a comprehensive release decision report.
    
    ## PIPELINE DATA
    
    ### Test Results
    - Status: {"PASSED" if test_data and test_data.failures == 0 else "FAILED"}
    - Total Tests: {test_data.total if test_data else 0}
    - Failures: {test_data.failures if test_data else 0}
    - Errors: {test_data.errors if test_data else 0}
    - Skipped: {test_data.skipped if test_data else 0}
    - Execution Time: {test_data.time if test_data else 0}s
    - Failed Test Names: {test_data.failed_test_names if test_data else []}
    
    ### Code Coverage
    - Current Coverage: {cov_data.line_rate if cov_data else 0.0:.2%}
    - Required Minimum: {MIN_COVERAGE_THRESHOLD:.0%}
    - Gap: {(MIN_COVERAGE_THRESHOLD - (cov_data.line_rate if cov_data else 0.0)):.2%}
    
    ### Security Configuration
    - Face Detection Threshold: {sec_config.face_threshold}
    - Maximum Safe Threshold: {MAX_FACE_THRESHOLD}
    - Liveness Min Frames: {sec_config.liveness_min_frames}
    
    ## DECISION CRITERIA
    
    **CRITICAL (Auto-Reject):**
    - Any test failures (failures > 0)
    - Security threshold regression (threshold > {MAX_FACE_THRESHOLD})
    
    **HIGH PRIORITY (Strong Warning/Reject):**
    - Coverage below {MIN_COVERAGE_THRESHOLD:.0%}
    - Coverage drop > 5% from baseline
    
    **MEDIUM PRIORITY (Warning):**
    - Coverage drop 2-5%
    - Execution time increase > 20%
    
    ## OUTPUT REQUIREMENTS
    
    Generate a JSON response with these exact fields:
    
    1. **verdict**: "APPROVED" or "REJECTED"
    
    2. **confidence_score**: Integer 0-100 representing deployment confidence
    
    3. **analysis_summary**: A rich markdown string with these sections:
    
       # Release Decision: [APPROVED/REJECTED]
       
       ## Executive Summary
       [2-3 sentence overview of the decision and key factors]
       
       ## Test Analysis
       - **Status**: [Pass/Fail]
       - **Coverage**: [Current %] (Target: {MIN_COVERAGE_THRESHOLD:.0%})
       - **Test Count**: [X tests, Y failures]
       - **Key Findings**: [Bullet points of important test insights]
       
       ## Security Assessment
       - **Face Threshold**: [Value] (Max Safe: {MAX_FACE_THRESHOLD})
       - **Risk Level**: [Low/Medium/High]
       - **Compliance**: [Pass/Fail with reasoning]
       
       ## Quality Metrics
       | Metric | Current | Target | Status |
       |--------|---------|--------|--------|
       | Coverage | [X%] | {MIN_COVERAGE_THRESHOLD:.0%} | [PASS/FAIL] |
       | Tests Passing | [X/Y] | 100% | [PASS/FAIL] |
       | Security Config | [Value] | <={MAX_FACE_THRESHOLD} | [PASS/FAIL] |
       
       ## Issues Identified
       [Numbered list of problems found, or "None" if clean]
       
       ## Recommendations
       [Actionable steps to improve quality, numbered list]
       
       ## Deployment Risk
       - **Risk Level**: [Low/Medium/High/Critical]
       - **Justification**: [Why this risk level]
       - **Mitigation**: [What should be done before/after deploy]
       
       ## Detailed Breakdown
       [Any additional context, trends, or observations]
       
       ---
       *Generated by AI Release Manager | Model: {MODEL_NAME}*
    
    Be thorough, professional, and actionable. Do not use emojis.
    """

    # 3. Call LLM
    print("[INFO] Analyzing with Gemini...")
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"  # Native JSON mode
            )
        )
        
        result = json.loads(response.text)
        
    except Exception as e:
        print(f"[FATAL] AI Analysis failed: {e}")
        print("[DEBUG] Listing available models:")
        try:
            for model in client.models.list():
                print(f"  - {model.name}")
        except Exception as list_err:
            print(f"  [ERROR] Could not list models: {list_err}")
        sys.exit(1)

    # 4. Report
    print("-" * 40)
    print(f"VERDICT: {result.get('verdict', 'UNKNOWN')}")
    print("-" * 40)

    # Save artifacts
    with open(os.path.join(args.artifacts, "release_summary.md"), "w") as f:
        f.write(result.get("analysis_summary", "No summary provided."))
    
    with open(os.path.join(args.artifacts, "release_decision.json"), "w") as f:
        json.dump(result, f, indent=2)

    if result.get("verdict") == "APPROVED":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
