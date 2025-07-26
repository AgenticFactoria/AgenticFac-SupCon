"""
Connection Health Monitor for MQTT and Network Stability

This module provides comprehensive connection monitoring and heartbeat functionality
to detect and handle network instability and server disconnections.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from .mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class ConnectionStatus(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ConnectionMetrics:
    """Track connection health metrics"""
    last_connect_time: float = 0
    last_disconnect_time: float = 0
    total_connections: int = 0
    total_disconnections: int = 0
    connection_attempts: int = 0
    successful_reconnections: int = 0
    failed_reconnections: int = 0
    average_connection_duration: float = 0
    total_downtime: float = 0


class ConnectionHealthMonitor:
    """
    Monitors connection health and provides heartbeat functionality
    """
    
    def __init__(self, mqtt_client: MQTTClient, heartbeat_interval: int = 30):
        self.mqtt_client = mqtt_client
        self.heartbeat_interval = heartbeat_interval
        self.metrics = ConnectionMetrics()
        self.status = ConnectionStatus.DISCONNECTED
        self.heartbeat_topic = "system/heartbeat"
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._status_callbacks: list[Callable] = []
        self._start_time = time.time()
        
    def add_status_callback(self, callback: Callable[[ConnectionStatus, Dict[str, Any]], None]):
        """Add a callback to be called when connection status changes"""
        self._status_callbacks.append(callback)
        
    def remove_status_callback(self, callback: Callable):
        """Remove a status callback"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
            
    def _notify_status_change(self, new_status: ConnectionStatus, details: Dict[str, Any] = None):
        """Notify all registered callbacks of status change"""
        self.status = new_status
        if details is None:
            details = {}
            
        details.update({
            'timestamp': time.time(),
            'uptime': time.time() - self._start_time,
            'metrics': self.metrics.__dict__
        })
        
        for callback in self._status_callbacks:
            try:
                callback(new_status, details)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")
                
    async def start_monitoring(self):
        """Start the connection monitoring and heartbeat tasks"""
        logger.info("Starting connection health monitoring...")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
    async def stop_monitoring(self):
        """Stop the connection monitoring and heartbeat tasks"""
        logger.info("Stopping connection health monitoring...")
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
                
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self.mqtt_client.is_connected():
                    heartbeat_data = {
                        'timestamp': time.time(),
                        'client_id': self.mqtt_client._client_id,
                        'status': self.status.value,
                        'uptime': time.time() - self._start_time,
                        'metrics': self.metrics.__dict__
                    }
                    
                    self.mqtt_client.publish(
                        self.heartbeat_topic,
                        json.dumps(heartbeat_data),
                        qos=0
                    )
                    logger.debug(f"Heartbeat sent: {heartbeat_data}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5)  # Brief delay on error
                
    async def _monitor_loop(self):
        """Monitor connection status and track metrics"""
        last_connected = False
        
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                is_now_connected = self.mqtt_client.is_connected()
                
                if is_now_connected != last_connected:
                    if is_now_connected:
                        # Just connected
                        self.metrics.total_connections += 1
                        self.metrics.last_connect_time = time.time()
                        
                        if self.metrics.last_disconnect_time > 0:
                            downtime = time.time() - self.metrics.last_disconnect_time
                            self.metrics.total_downtime += downtime
                            
                        self._notify_status_change(ConnectionStatus.CONNECTED)
                        logger.info("Connection established")
                    else:
                        # Just disconnected
                        self.metrics.total_disconnections += 1
                        self.metrics.last_disconnect_time = time.time()
                        
                        if self.metrics.last_connect_time > 0:
                            duration = time.time() - self.metrics.last_connect_time
                            if self.metrics.average_connection_duration == 0:
                                self.metrics.average_connection_duration = duration
                            else:
                                self.metrics.average_connection_duration = (
                                    (self.metrics.average_connection_duration * 
                                     (self.metrics.total_connections - 1) + duration) / 
                                    self.metrics.total_connections
                                )
                        
                        self._notify_status_change(ConnectionStatus.DISCONNECTED)
                        logger.warning("Connection lost")
                        
                last_connected = is_now_connected
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(1)  # Brief delay on error
                
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report"""
        current_time = time.time()
        
        report = {
            'status': self.status.value,
            'current_uptime': current_time - self._start_time,
            'is_connected': self.mqtt_client.is_connected(),
            'metrics': {
                'total_connections': self.metrics.total_connections,
                'total_disconnections': self.metrics.total_disconnections,
                'connection_attempts': self.metrics.connection_attempts,
                'successful_reconnections': self.metrics.successful_reconnections,
                'failed_reconnections': self.metrics.failed_reconnections,
                'average_connection_duration': self.metrics.average_connection_duration,
                'total_downtime': self.metrics.total_downtime,
                'uptime_percentage': self._calculate_uptime_percentage(),
                'last_connect_time': self.metrics.last_connect_time,
                'last_disconnect_time': self.metrics.last_disconnect_time,
            },
            'mqtt_client_status': self.mqtt_client.get_connection_status()
        }
        
        return report
        
    def _calculate_uptime_percentage(self) -> float:
        """Calculate uptime percentage since start"""
        total_time = time.time() - self._start_time
        if total_time == 0:
            return 0.0
            
        uptime = total_time - self.metrics.total_downtime
        return (uptime / total_time) * 100
        
    def reset_metrics(self):
        """Reset all connection metrics"""
        self.metrics = ConnectionMetrics()
        self._start_time = time.time()
        logger.info("Connection metrics reset")