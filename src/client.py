import os
import argparse
import json
import sys
import google.generativeai as genai
from src.tools.parsers import parse_junit_xml, parse_cobertura_xml, read_security_config

# --- Configuration ---
MIN_COVERAGE_THRESHOLD = 0.75
MAX_FACE_THRESHOLD = 0.55

def main():
    parser = argparse.ArgumentParser(description="AI Release Manager Agent")
    parser.add_argument("--artifacts", required=True, help="Path to artifacts directory containing test-results.xml and coverage.xml")
    parser.add_argument("--repo-root", required=True, help="Path to the root of the repository being checked")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')

    print("[INFO] Starting AI Release Manager...")
    
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

    # 2. Construct Prompt
    prompt = f"""
    You are the Senior Release Manager (SRE) for a Critical Face Verification System.
    Your task is to decide if this release is safe for Production.

    ## PIPELINE DATA
    
    1. Unit Tests:
       - Status: {"PASSED" if test_data and test_data.failures == 0 else "FAILED"}
       - Details: {test_data.model_dump() if test_data else "Data missing"}
       - RULE: If failures > 0, REJECT unless marked explicitly as safe (none are).

    2. Code Coverage:
       - Current Rate: {cov_data.line_rate if cov_data else "Unknown"}
       - Minimum Required: {MIN_COVERAGE_THRESHOLD}
       - RULE: If code coverage < {MIN_COVERAGE_THRESHOLD}, consider Rejecting or Warning based on severity.

    3. Security Configuration:
       - Detected Threshold: {sec_config.face_threshold}
       - Max Allowed: {MAX_FACE_THRESHOLD}
       - RULE: If Detected > Max, REJECT IMMEDIATELY (Security Risk).

    ## INSTRUCTIONS
    Analyze the data above.
    1. Determine verdict: APPROVED or REJECTED.
    2. Write a summary explaining the decision.

    ## OUTPUT FORMAT (JSON)
    {{
        "verdict": "APPROVED" | "REJECTED",
        "confidence_score": <0-100>,
        "analysis_summary": "<markdown text>"
    }}
    """

    # 3. Call LLM
    print("[INFO] Analyzing with Gemini...")
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
    except Exception as e:
        print(f"[FATAL] AI Analysis failed: {e}")
        sys.exit(1)

    # 4. Report and Exit
    print("-" * 40)
    print(f"VERDICT: {result['verdict']}")
    print("-" * 40)

    # Save artifacts
    with open(os.path.join(args.artifacts, "release_summary.md"), "w") as f:
        f.write(result["analysis_summary"])
    
    with open(os.path.join(args.artifacts, "release_decision.json"), "w") as f:
        json.dump(result, f, indent=2)

    if result["verdict"] == "APPROVED":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
