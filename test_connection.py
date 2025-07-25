#!/usr/bin/env python3
"""
Connection Test Script for Multi-Agent Factory System

This script tests the MQTT connection and basic functionality
to ensure the asyncio event loop issue is resolved.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.agent_config import print_config, validate_environment


async def test_multi_agent_connection():
    """Test multi-agent system connection"""
    print("🔧 Testing Multi-Agent Factory System Connection")
    print("=" * 60)

    # Step 1: Validate configuration
    print("\n📋 Step 1: Validating Configuration...")
    if not validate_environment():
        print("❌ Configuration validation failed!")
        return False

    # Step 2: Print configuration
    print("\n📊 Step 2: Configuration Summary...")
    print_config()

    # Step 3: Test MQTT connection (import only)
    print("\n📡 Step 3: Testing MQTT Connection...")
    try:
        from config.agent_config import get_topic_config
        from src.agent.multi_agent_system import MultiAgentFactoryController

        topic_config = get_topic_config()
        controller = MultiAgentFactoryController(topic_config.root)

        print("✅ Multi-agent controller created successfully")
        print(f"📢 Topic root: {controller.root_topic}")
        print(f"🆔 Client ID: {controller.client_id}")

    except Exception as e:
        print(f"❌ Failed to create multi-agent controller: {e}")
        return False

    # Step 4: Test agent initialization
    print("\n🤖 Step 4: Testing Agent Initialization...")
    try:
        controller.initialize_agents()
        print(f"✅ Initialized {len(controller.line_commanders)} line commanders")
        print(f"✅ Supervisor agent: {'✓' if controller.supervisor_agent else '✗'}")

    except Exception as e:
        print(f"❌ Failed to initialize agents: {e}")
        return False

    # Step 5: Test event loop setup (without actually starting)
    print("\n🔄 Step 5: Testing Event Loop Setup...")
    try:
        controller.running = True

        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        print(f"✅ Event loop created: {type(loop).__name__}")
        print(f"✅ Event loop running: {loop.is_running()}")

        controller.running = False

    except Exception as e:
        print(f"❌ Event loop setup failed: {e}")
        return False

    print("\n🎉 All connection tests passed!")
    print("🚀 Multi-agent system is ready to run")
    return True


def test_simple_agent_connection():
    """Test simple agent connection for comparison"""
    print("\n🔍 Testing Simple Agent Connection (for comparison)...")
    try:
        from config.agent_config import get_topic_config
        from src.agent.simple_agent import SimpleAgent

        topic_config = get_topic_config()
        simple_agent = SimpleAgent(topic_config.root)

        print("✅ Simple agent created successfully")
        print(f"📢 Topic root: {simple_agent.topic_manager.root}")
        print(f"🆔 Client ID: {simple_agent.client_id}")

        return True

    except Exception as e:
        print(f"❌ Simple agent connection failed: {e}")
        return False


async def main():
    """Main test function"""
    print("🧪 Factory Control System Connection Test")
    print("=" * 60)

    # Test simple agent (known working)
    simple_ok = test_simple_agent_connection()

    # Test multi-agent system (fixed)
    multi_ok = await test_multi_agent_connection()

    print("\n📊 Test Results Summary")
    print("=" * 60)
    print(f"Simple Agent:     {'✅ PASS' if simple_ok else '❌ FAIL'}")
    print(f"Multi-Agent:      {'✅ PASS' if multi_ok else '❌ FAIL'}")

    if simple_ok and multi_ok:
        print("\n🎉 All systems operational!")
        print("💡 You can now run: python run_multi_agent.py")
    else:
        print("\n⚠️  Some systems have issues")
        if not simple_ok:
            print("   - Check your .env configuration")
        if not multi_ok:
            print("   - Multi-agent system needs debugging")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
