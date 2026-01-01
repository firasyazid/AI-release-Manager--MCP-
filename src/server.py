import asyncio
import os
import sys
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from src.tools.parsers import parse_junit_xml, parse_cobertura_xml, read_security_config, analyze_logs

# Initialize Server
app = Server("ai-release-manager-tools")

@app.call_tool()
async def get_test_results(xml_path: str) -> str:
    """
    Parses a JUnit XML file and returns a summary JSON string.
    Input: Absolute path to the test-results.xml file.
    """
    try:
        data = parse_junit_xml(xml_path)
        return data.json()
    except Exception as e:
        return f"Error parsing test results: {str(e)}"

@app.call_tool()
async def get_coverage_report(xml_path: str) -> str:
    """
    Parses a Cobertura XML file and returns coverage stats JSON string.
    Input: Absolute path to the coverage.xml file.
    """
    try:
        data = parse_cobertura_xml(xml_path)
        return data.json()
    except Exception as e:
        return f"Error parsing coverage: {str(e)}"

@app.call_tool()
async def check_security_constants(config_path: str) -> str:
    """
    Reads the project config.py and extracts security thresholds.
    Input: Absolute path to the config.py file.
    """
    try:
        data = read_security_config(config_path)
        return data.json()
    except Exception as e:
        return f"Error reading config: {str(e)}"

@app.call_tool()
async def scan_build_logs(log_text: str) -> str:
    """
    Analyzes a build log string for errors and warnings.
    Input: The raw text of the build log.
    """
    try:
        data = analyze_logs(log_text)
        return data.json()
    except Exception as e:
        return f"Error scanning logs: {str(e)}"

async def main():
    # Run the server over stdio
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
