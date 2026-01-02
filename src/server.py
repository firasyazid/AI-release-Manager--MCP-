import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from src.tools.parsers import parse_junit_xml, parse_cobertura_xml, read_security_config, analyze_logs

# Configuration - Allowed base directories for security
ALLOWED_BASE_PATHS = [
    os.getcwd(),
    os.path.join(os.getcwd(), "artifacts"),
    os.path.expanduser("~"),  # Allow home directory
]

# Initialize Server
app = Server("ai-release-manager-tools")

def is_path_safe(file_path: str) -> bool:
    """
    Validates that the requested path is within allowed directories.
    Prevents path traversal attacks.
    """
    try:
        abs_path = Path(file_path).resolve()
        return any(
            str(abs_path).startswith(str(Path(base).resolve()))
            for base in ALLOWED_BASE_PATHS
        )
    except (ValueError, OSError):
        return False

@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    Register all available tools with proper schemas.
    This is called by MCP clients to discover capabilities.
    """
    return [
        Tool(
            name="get_test_results",
            description="Parses a JUnit XML file and returns test execution metrics including pass/fail counts, execution time, and failed test names.",
            inputSchema={
                "type": "object",
                "properties": {
                    "xml_path": {
                        "type": "string",
                        "description": "Absolute path to the JUnit XML test results file (e.g., test-results.xml)"
                    }
                },
                "required": ["xml_path"]
            }
        ),
        Tool(
            name="get_coverage_report",
            description="Parses a Cobertura XML file and returns code coverage statistics including line rate and coverage percentages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "xml_path": {
                        "type": "string",
                        "description": "Absolute path to the Cobertura XML coverage file (e.g., coverage.xml)"
                    }
                },
                "required": ["xml_path"]
            }
        ),
        Tool(
            name="check_security_constants",
            description="Reads a Python configuration file and extracts security-related constants like face detection thresholds and liveness parameters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "config_path": {
                        "type": "string",
                        "description": "Absolute path to the Python config file (e.g., app/config.py)"
                    }
                },
                "required": ["config_path"]
            }
        ),
        Tool(
            name="scan_build_logs",
            description="Analyzes build log text for errors, exceptions, and warnings, returning counts and extracted error messages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_text": {
                        "type": "string",
                        "description": "The raw text content of the build log to analyze"
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of error/warning lines to return (default: 50)",
                        "default": 50
                    }
                },
                "required": ["log_text"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """
    Route tool calls to appropriate handlers with validation and error handling.
    This is the MCP-compliant way to execute tools.
    Returns structured TextContent responses.
    """
    try:
        if name == "get_test_results":
            xml_path = arguments.get("xml_path")
            if not xml_path:
                raise ValueError("xml_path is required")
            
            if not is_path_safe(xml_path):
                raise PermissionError(f"Access denied: {xml_path} is outside allowed directories")
            
            data = parse_junit_xml(xml_path)
            return [TextContent(
                type="text",
                text=data.model_dump_json(indent=2)
            )]
        
        elif name == "get_coverage_report":
            xml_path = arguments.get("xml_path")
            if not xml_path:
                raise ValueError("xml_path is required")
            
            if not is_path_safe(xml_path):
                raise PermissionError(f"Access denied: {xml_path} is outside allowed directories")
            
            data = parse_cobertura_xml(xml_path)
            return [TextContent(
                type="text",
                text=data.model_dump_json(indent=2)
            )]
        
        elif name == "check_security_constants":
            config_path = arguments.get("config_path")
            if not config_path:
                raise ValueError("config_path is required")
            
            if not is_path_safe(config_path):
                raise PermissionError(f"Access denied: {config_path} is outside allowed directories")
            
            data = read_security_config(config_path)
            return [TextContent(
                type="text",
                text=data.model_dump_json(indent=2)
            )]
        
        elif name == "scan_build_logs":
            log_text = arguments.get("log_text")
            if not log_text:
                raise ValueError("log_text is required")
            
            if len(log_text) > 1_000_000:  # 1MB limit
                raise ValueError(f"Log text exceeds maximum size of 1MB")
            
            max_lines = arguments.get("max_lines", 50)
            data = analyze_logs(log_text, max_lines=max_lines)
            return [TextContent(
                type="text",
                text=data.model_dump_json(indent=2)
            )]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    except FileNotFoundError as e:
        return [TextContent(
            type="text",
            text=f"Error: File not found - {str(e)}"
        )]
    except PermissionError as e:
        return [TextContent(
            type="text",
            text=f"Error: Permission denied - {str(e)}"
        )]
    except ValueError as e:
        return [TextContent(
            type="text",
            text=f"Error: Invalid input - {str(e)}"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error processing {name}: {str(e)}"
        )]

async def main():
    """
    Start the MCP server over stdio transport.
    This allows external MCP clients (Claude Desktop, etc.) to connect.
    """
    print("[INFO] AI Release Manager MCP Server starting...", file=sys.stderr)
    print(f"[INFO] Allowed base paths: {ALLOWED_BASE_PATHS}", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
