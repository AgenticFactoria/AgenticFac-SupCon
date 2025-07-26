"""
Comprehensive Connection Manager for Robust Network Communication

This module provides a high-level interface for managing network connections
with automatic reconnection, health monitoring, message retry queues, and
graceful error handling.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from .resilient_mqtt_client import ResilientMQTTClient
from .message_retry_queue import MessageRetryQueue, RetryPolicy
from .connection_monitor import ConnectionHealthMonitor, ConnectionStatus

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    """Configuration for connection management"""
    host: str
    port: int
    client_id: str
    username: Optional[str] = None
    password: Optional[str] = None
    heartbeat_interval: int = 30
    max_retry_queue_size: int = 1000
    auto_reconnect: bool = True
    connection_timeout: float = 30.0
    message_retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL_BACKOFF
    max_message_retries: int = 5


class ConnectionManager:
    """
    High-level connection manager that provides robust network communication
    """
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.client = ResilientMQTTClient(
            host=config.host,
            port=config.port,
            client_id=config.client_id,
            heartbeat_interval=config.heartbeat_interval,
            auto_reconnect=config.auto_reconnect
        )
        
        self.retry_queue = MessageRetryQueue(
            self.client.mqtt_client,
            max_queue_size=config.max_retry_queue_size
        )
        
        self._running = False
        self._connection_callbacks: Dict[str, Callable] = {}
        
        # Set up connection status callback
        self.client.on_connection_status_change = self._handle_connection_status
        
    async def start(self):
        """Start the connection manager"""
        if self._running:
            logger.warning("Connection manager is already running")
            return
            
        logger.info("Starting connection manager...")
        
        try:
            # Start the retry queue
            await self.retry_queue.start()
            
            # Connect to MQTT broker
            await self.client.connect()
            
            self._running = True
            logger.info("Connection manager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start connection manager: {e}")
            raise
            
    async def stop(self):
        """Stop the connection manager gracefully"""
        if not self._running:
            return
            
        logger.info("Stopping connection manager...")
        
        try:
            self._running = False
            
            # Flush retry queue before stopping
            await self.retry_queue.flush_queue()
            
            # Stop retry queue
            await self.retry_queue.stop()
            
            # Disconnect client
            await self.client.disconnect()
            
            logger.info("Connection manager stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping connection manager: {e}")
            
    async def publish(self, topic: str, payload: str, qos: int = 1, 
                     retain: bool = False, use_retry_queue: bool = True) -> bool:
        """Publish a message with automatic retry handling"""
        if not self._running:
            logger.error("Connection manager is not running")
            return False
            
        try:
            # Try to send immediately
            success = self.client.publish(topic, payload, qos, retain)
            
            if success:
                return True
                
            # Failed to send, add to retry queue if enabled
            if use_retry_queue:
                logger.debug("Adding message to retry queue")
                return self.retry_queue.add_message(
                    topic=topic,
                    payload=payload,
                    qos=qos,
                    retain=retain,
                    max_retries=self.config.max_message_retries,
                    retry_policy=self.config.message_retry_policy
                )
            else:
                logger.warning("Message send failed and retry queue disabled")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False
            
    def subscribe(self, topic: str, callback, qos: int = 0) -> bool:
        """Subscribe to a topic"""
        if not self._running:
            logger.error("Connection manager is not running")
            return False
            
        return self.client.subscribe(topic, callback, qos)
        
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.client.is_connected()
        
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status report"""
        return {
            'running': self._running,
            'connection': self.client.get_connection_status(),
            'health': self.client.get_health_report(),
            'retry_queue': self.retry_queue.get_queue_status()
        }
        
    def get_status_string(self) -> str:
        """Get human-readable status"""
        return self.client.get_status_string()
        
    async def wait_for_connection(self, timeout: float = None) -> bool:
        """Wait for connection to be established"""
        timeout = timeout or self.config.connection_timeout
        return await self.client.wait_for_connection(timeout)
        
    def add_connection_callback(self, name: str, callback: Callable):
        """Add a callback for connection status changes"""
        self._connection_callbacks[name] = callback
        
    def remove_connection_callback(self, name: str):
        """Remove a connection callback"""
        self._connection_callbacks.pop(name, None)
        
    def _handle_connection_status(self, status: ConnectionStatus, details: Dict[str, Any]):
        """Handle connection status changes"""
        logger.info(f"Connection status: {status.value}")
        
        # Notify all registered callbacks
        for name, callback in self._connection_callbacks.items():
            try:
                callback(status, details)
            except Exception as e:
                logger.error(f"Error in connection callback '{name}': {e}")
                
    def flush_retry_queue(self):
        """Flush all pending messages in retry queue"""
        return self.retry_queue.flush_queue()
        
    def clear_retry_queue(self):
        """Clear all messages from retry queue"""
        self.retry_queue.clear_queue()
        
    def get_retry_queue_status(self) -> Dict[str, Any]:
        """Get retry queue status"""
        return self.retry_queue.get_queue_status()
        
    def reset_metrics(self):
        """Reset connection metrics"""
        self.client.reset_metrics()
        
    async def health_check(self) -> bool:
        """Perform a health check on the connection"""
        if not self._running:
            return False
            
        # Check if connected
        if not self.is_connected():
            logger.warning("Connection health check failed: not connected")
            return False
            
        # Check retry queue size
        queue_status = self.get_retry_queue_status()
        if queue_status['queue_size'] > self.config.max_retry_queue_size * 0.8:
            logger.warning(f"High retry queue usage: {queue_status['queue_size']}/{self.config.max_retry_queue_size}")
            
        return True
        
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        health = self.client.get_health_report()
        
        return {
            'uptime_percentage': health['metrics']['uptime_percentage'],
            'total_connections': health['metrics']['total_connections'],
            'total_disconnections': health['metrics']['total_disconnections'],
            'average_connection_duration': health['metrics']['average_connection_duration'],
            'retry_queue_size': len(self.retry_queue._queue),
            'is_connected': self.is_connected(),
            'last_health_check': time.time()
        }