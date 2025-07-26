#!/usr/bin/env python3
"""
Example of using the resilient connection manager

This example demonstrates how to use the new connection management system
with automatic reconnection, health monitoring, and message retry queues.
"""
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.connection_manager import ConnectionManager, ConnectionConfig
from config.agent_config import get_mqtt_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResilientConnectionExample:
    """Example class demonstrating resilient connection usage"""
    
    def __init__(self):
        self.connection_manager = None
        self.running = False
        
    async def setup_connection(self):
        """Set up the resilient connection manager"""
        mqtt_config = get_mqtt_config()
        
        config = ConnectionConfig(
            host=mqtt_config.host,
            port=mqtt_config.port,
            client_id="resilient_example_client",
            heartbeat_interval=10,  # Send heartbeat every 10 seconds
            max_retry_queue_size=100,
            auto_reconnect=True,
            connection_timeout=30.0,
            max_message_retries=5
        )
        
        self.connection_manager = ConnectionManager(config)
        
        # Add connection status callback
        self.connection_manager.add_connection_callback(
            "example", self._on_connection_status_change
        )
        
    async def _on_connection_status_change(self, status, details):
        """Handle connection status changes"""
        logger.info(f"Connection status changed: {status.value}")
        logger.info(f"Details: {details}")
        
    async def start(self):
        """Start the example"""
        logger.info("Starting resilient connection example...")
        
        try:
            await self.setup_connection()
            await self.connection_manager.start()
            
            if not await self.connection_manager.wait_for_connection(timeout=10):
                logger.error("Failed to establish connection")
                return
                
            self.running = True
            logger.info("Connection established successfully")
            
            # Start periodic tasks
            tasks = [
                asyncio.create_task(self._publish_messages()),
                asyncio.create_task(self._monitor_health()),
                asyncio.create_task(self._handle_messages())
            ]
            
            # Wait for tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Error in example: {e}")
        finally:
            await self.stop()
            
    async def stop(self):
        """Stop the example"""
        logger.info("Stopping example...")
        self.running = False
        
        if self.connection_manager:
            await self.connection_manager.stop()
            
    async def _publish_messages(self):
        """Publish test messages"""
        message_count = 0
        
        while self.running:
            try:
                # Publish a test message
                message = {
                    'id': message_count,
                    'timestamp': asyncio.get_event_loop().time(),
                    'type': 'test_message',
                    'data': f'This is message {message_count}'
                }
                
                success = await self.connection_manager.publish(
                    topic="example/test_messages",
                    payload=json.dumps(message),
                    qos=1
                )
                
                if success:
                    logger.info(f"Published message {message_count}")
                else:
                    logger.warning(f"Failed to publish message {message_count}, added to retry queue")
                
                message_count += 1
                await asyncio.sleep(5)  # Publish every 5 seconds
                
            except Exception as e:
                logger.error(f"Error publishing message: {e}")
                await asyncio.sleep(1)
                
    async def _monitor_health(self):
        """Monitor connection health"""
        while self.running:
            try:
                # Get health report
                health = self.connection_manager.get_health_report()
                
                logger.info("=== Health Report ===")
                logger.info(f"Status: {health['connection']['status']}")
                logger.info(f"Connected: {health['connection']['connected']}")
                logger.info(f"Uptime: {health['health']['current_uptime']:.1f}s")
                logger.info(f"Queue size: {health['retry_queue']['queue_size']}")
                
                # Check if healthy
                is_healthy = await self.connection_manager.health_check()
                logger.info(f"Health check: {'PASS' if is_healthy else 'FAIL'}")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring health: {e}")
                await asyncio.sleep(5)
                
    async def _handle_messages(self):
        """Handle incoming messages"""
        def on_message(topic, payload):
            try:
                message = json.loads(payload.decode())
                logger.info(f"Received message on {topic}: {message}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                
        # Subscribe to relevant topics
        self.connection_manager.subscribe("example/+/responses", on_message)
        
        # Keep running
        while self.running:
            await asyncio.sleep(1)


async def main():
    """Main function"""
    example = ResilientConnectionExample()
    
    # Handle shutdown signals
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(example.stop())
        
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda s, f: signal_handler())
    
    try:
        await example.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await example.stop()


if __name__ == "__main__":
    asyncio.run(main())