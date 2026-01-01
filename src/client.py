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
MODEL_NAME = "gemini-1.5-pro"

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

    # 2. Construct Prompt
    # We want JSON output. The new SDK supports structured output natively.
    prompt = f"""
    Act as a Senior Release Manager.
    Analyze this CI/CD data for a Face Verification System.

    DATA:
    1. Unit Tests: {"PASSED" if test_data and test_data.failures == 0 else "FAILED"}
       Details: {test_data.model_dump() if test_data else "Missing"}
       Running {test_data.total if test_data else 0} tests.
       
    2. Coverage: {cov_data.line_rate if cov_data else "0.0"} (Min: {MIN_COVERAGE_THRESHOLD})
    
    3. Config: Face Threshold {sec_config.face_threshold} (Max Safe: {MAX_FACE_THRESHOLD})

    TASK:
    - If Test Failures > 0 => REJECT.
    - If Config Threshold > {MAX_FACE_THRESHOLD} => REJECT (Security Risk).
    - If Coverage < {MIN_COVERAGE_THRESHOLD} => WARNING or REJECT.
    
    Output JSON with fields: verdict (APPROVED/REJECTED), confidence_score (int), analysis_summary (string).
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
