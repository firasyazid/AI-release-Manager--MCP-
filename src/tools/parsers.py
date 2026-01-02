import os

import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

# --- Data Models ---

class TestSummary(BaseModel):
    total: int
    failures: int
    errors: int
    skipped: int
    time: float
    failed_test_names: List[str]

class CoverageSummary(BaseModel):
    line_rate: float
    total_lines: int
    covered_lines: int

class SecurityConfig(BaseModel):
    face_threshold: Optional[float]
    liveness_min_frames: Optional[int]

class LogAnalysis(BaseModel):
    error_count: int
    warning_count: int
    critical_errors: List[str]
    warnings: List[str]

# --- Logic Implementations ---

def parse_junit_xml(file_path: str) -> TestSummary:
    """
    Parses a JUnit XML file to extract test execution metrics.
    Raises FileNotFoundError or ValueError on parsing issues.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Test result file not found: {file_path}")

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        total = 0
        failures = 0
        errors = 0
        skipped = 0
        time = 0.0
        failed_tests = []

        def process_suite(suite):
            nonlocal total, failures, errors, skipped, time
            total += int(suite.get('tests', 0))
            failures += int(suite.get('failures', 0))
            errors += int(suite.get('errors', 0))
            skipped += int(suite.get('skipped', 0))
            time += float(suite.get('time', 0.0))
            
            for case in suite.findall('testcase'):
                if case.find('failure') is not None or case.find('error') is not None:
                     name = case.get('name', 'unknown')
                     classname = case.get('classname', '')
                     failed_tests.append(f"{classname}::{name}")

        if root.tag == 'testsuites':
            for suite in root.findall('testsuite'):
                process_suite(suite)
        elif root.tag == 'testsuite':
            process_suite(root)
            
        return TestSummary(
            total=total,
            failures=failures,
            errors=errors,
            skipped=skipped,
            time=time,
            failed_test_names=failed_tests
        )
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format in {file_path}: {e}")

def parse_cobertura_xml(file_path: str) -> CoverageSummary:
    """
    Parses a Cobertura XML file to extract coverage line rate.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Coverage file not found: {file_path}")

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        return CoverageSummary(
            line_rate=float(root.get('line-rate', 0.0)),
            # Cobertura often puts valid lines in the root or package elements
            # For this summary, rate is the primary metric.
            total_lines=0,
            covered_lines=0 
        )
    except ET.ParseError as e:
        raise ValueError(f"Invalid Cobertura XML format in {file_path}: {e}")

def read_security_config(config_path: str) -> SecurityConfig:
    """
    Reads a python config file to extract specific security constants using regex.
    Designed to work without importing the actual module (safer in CI).
    """
    if not os.path.exists(config_path):
        return SecurityConfig(face_threshold=None, liveness_min_frames=None)

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    face_match = re.search(r'face_detection_threshold.*=\s*([0-9.]+)', content)
    liveness_match = re.search(r'liveness_min_valid_frames.*=\s*(\d+)', content)

    return SecurityConfig(
        face_threshold=float(face_match.group(1)) if face_match else None,
        liveness_min_frames=int(liveness_match.group(1)) if liveness_match else None
    )

def analyze_logs(log_content: str, max_lines: int = 50) -> LogAnalysis:
    """
    Scans a text string for error/exception keywords.
    """
    lines = log_content.splitlines()
    errors = []
    warnings = []

    for line in lines:
        line_lower = line.lower()
        if "error" in line_lower or "exception" in line_lower:
            errors.append(line[:300]) # Truncate long lines
        elif "warning" in line_lower:
            warnings.append(line[:300])
            
    return LogAnalysis(
        error_count=len(errors),
        warning_count=len(warnings),
        critical_errors=errors[:max_lines],
        warnings=warnings[:max_lines]
    )
