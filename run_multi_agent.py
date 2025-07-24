#!/usr/bin/env python3
"""
Multi-Agent Factory Control System Launcher

This script starts the hierarchical multi-agent factory control system:
- Supervisor Agent: Global order allocation and KPI monitoring
- Line Commander Agents: Individual production line control

Usage:
    python run_multi_agent.py [--debug] [--line-count N]

Options:
    --debug: Enable debug logging
    --line-count N: Number of production lines to activate (default: 1 for MVP)
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.agent.multi_agent_system import main


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Factory Control System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_multi_agent.py                    # Start with default settings (line1 only)
    python run_multi_agent.py --debug            # Start with debug logging
    python run_multi_agent.py --line-count 3     # Start with all 3 production lines
        """,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for detailed operation tracking",
    )

    parser.add_argument(
        "--line-count",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="Number of production lines to activate (1-3, default: 1 for MVP)",
    )

    return parser.parse_args()


def setup_logging(debug: bool):
    """Setup logging configuration"""
    import logging

    level = logging.DEBUG if debug else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("multi_agent_factory.log", mode="a"),
        ],
    )

    # Reduce noise from some libraries
    logging.getLogger("paho.mqtt").setLevel(logging.WARNING)
    if not debug:
        logging.getLogger("agents").setLevel(logging.WARNING)


def print_startup_banner():
    """Print startup banner"""
    banner = """
🏭 ========================================================
   SUPCON Multi-Agent Factory Control System
🏭 ========================================================

🤖 Architecture:
   ├── Supervisor Agent (Global Coordinator)
   │   ├── Order allocation & scheduling
   │   ├── KPI monitoring & optimization
   │   └── Cross-line coordination
   └── Line Commander Agents (Line Control)
       ├── AGV management & routing
       ├── Local production optimization
       └── Equipment monitoring

🚀 Starting system...
"""
    print(banner)


if __name__ == "__main__":
    try:
        args = parse_arguments()

        print_startup_banner()
        setup_logging(args.debug)

        if args.debug:
            print("🔍 Debug mode enabled - detailed logging active")

        if args.line_count > 1:
            print(f"⚠️  Multi-line mode requested ({args.line_count} lines)")
            print("   Note: Current MVP version focuses on line1 only")
            print("   Full multi-line support coming in future releases")

        # Start the multi-agent system
        print("🔧 Initializing multi-agent factory control system...")
        main()

    except KeyboardInterrupt:
        print("\n🛑 Multi-Agent Factory System stopped by user")
    except Exception as e:
        print(f"\n❌ Failed to start Multi-Agent Factory System: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)
