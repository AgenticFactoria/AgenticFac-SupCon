"""
Resilient MQTT Client Wrapper with Built-in Health Monitoring

This module provides a resilient MQTT client that automatically handles
reconnections, health monitoring, and graceful error recovery.
"""
import asyncio
import logging
import time
from typing import Optional, Callable, Dict, Any

from .mqtt_client import MQTTClient
from .connection_monitor import ConnectionHealthMonitor, ConnectionStatus

logger = logging.getLogger(__name__)


class ResilientMQTTClient:
    """
    A resilient MQTT client with automatic reconnection and health monitoring
    """
    
    def __init__(self, host: str, port: int, client_id: str, 
                 heartbeat_interval: int = 30, auto_reconnect: bool = True):
        self.host = host
        self.port = port
        self.client_id = client_id
        
        # Initialize the underlying MQTT client
        self.mqtt_client = MQTTClient(host, port, client_id)
        
        # Initialize connection health monitor
        self.health_monitor = ConnectionHealthMonitor(
            self.mqtt_client, 
            heartbeat_interval=heartbeat_interval
        )
        
        # Configuration
        self.auto_reconnect = auto_reconnect
        self._monitoring_started = False
        
        # Callbacks
        self.on_connection_status_change: Optional[Callable] = None
        
        # Add health monitor callback
        self.health_monitor.add_status_callback(self._handle_status_change)
        
    async def connect(self):
        """Connect to MQTT broker and start health monitoring"""
        try:
            logger.info(f"Connecting resilient MQTT client to {self.host}:{self.port}")
            
            # Connect the underlying client
            self.mqtt_client.connect()
            
            # Start health monitoring
            if not self._monitoring_started:
                await self.health_monitor.start_monitoring()
                self._monitoring_started = True
                
            logger.info("Resilient MQTT client connected successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect resilient MQTT client: {e}")
            if self.auto_reconnect:
                logger.info("Auto-reconnect enabled - will attempt reconnection")
            raise
            
    async def disconnect(self):
        """Disconnect from MQTT broker and stop health monitoring"""
        try:
            logger.info("Disconnecting resilient MQTT client")
            
            # Stop health monitoring
            if self._monitoring_started:
                await self.health_monitor.stop_monitoring()
                self._monitoring_started = False
                
            # Disconnect the underlying client
            self.mqtt_client.disconnect()
            
            logger.info("Resilient MQTT client disconnected")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            
    def _handle_status_change(self, status: ConnectionStatus, details: Dict[str, Any]):
        """Handle connection status changes"""
        logger.info(f"Connection status changed to: {status.value}")
        
        if self.on_connection_status_change:
            try:
                self.on_connection_status_change(status, details)
            except Exception as e:
                logger.error(f"Error in connection status callback: {e}")
                
    def subscribe(self, topic: str, callback, qos: int = 0):
        """Subscribe to a topic with automatic retry on disconnection"""
        return self.mqtt_client.subscribe(topic, callback, qos)
        
    def publish(self, topic: str, payload, qos: int = 1, retain: bool = False):
        """Publish a message with connection status checking"""
        return self.mqtt_client.publish(topic, payload, qos, retain)
        
    def is_connected(self):
        """Check if the client is currently connected"""
        return self.mqtt_client.is_connected()
        
    def get_health_report(self):
        """Get comprehensive health report"""
        return self.health_monitor.get_health_report()
        
    def get_connection_status(self):
        """Get current connection status"""
        return {
            'connected': self.is_connected(),
            'status': self.health_monitor.status.value,
            'host': self.host,
            'port': self.port,
            'client_id': self.client_id
        }
        
    def set_heartbeat_interval(self, interval: int):
        """Change the heartbeat interval"""
        self.health_monitor.heartbeat_interval = interval
        logger.info(f"Heartbeat interval updated to {interval} seconds")
        
    def reset_metrics(self):
        """Reset connection health metrics"""
        self.health_monitor.reset_metrics()
        
    async def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for connection to be established"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_connected():
                return True
            await asyncio.sleep(1)
            
        return False
        
    def get_status_string(self) -> str:
        """Get a human-readable status string"""
        report = self.get_health_report()
        if report['is_connected']:
            return f"Connected to {self.host}:{self.port} (uptime: {report['current_uptime']:.1f}s)"
        else:
            return f"Disconnected from {self.host}:{self.port} (downtime: {report['metrics']['total_downtime']:.1f}s)"