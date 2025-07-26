"""
Message Retry Queue for Reliable Communication

This module implements a retry queue system for messages that fail to send
due to network issues, with configurable retry policies and backoff strategies.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class RetryPolicy(Enum):
    EXPONENTIAL_BACKOFF = "exponential"
    LINEAR_BACKOFF = "linear"
    FIXED_DELAY = "fixed"
    IMMEDIATE = "immediate"


@dataclass
class QueuedMessage:
    """Represents a message waiting to be sent"""
    topic: str
    payload: str
    qos: int = 1
    retain: bool = False
    timestamp: float = 0
    retry_count: int = 0
    max_retries: int = 5
    retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL_BACKOFF
    next_retry_time: float = 0
    message_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.next_retry_time == 0:
            self.next_retry_time = self.timestamp
        if self.message_id is None:
            self.message_id = f"{self.topic}_{int(time.time() * 1000)}"


class MessageRetryQueue:
    """
    A message retry queue that handles failed message sends
    """
    
    def __init__(self, mqtt_client, max_queue_size: int = 1000):
        self.mqtt_client = mqtt_client
        self.max_queue_size = max_queue_size
        self._queue: List[QueuedMessage] = []
        self._processing_task: Optional[asyncio.Task] = None
        self._running = False
        self._retry_delays = {
            RetryPolicy.EXPONENTIAL_BACKOFF: [1, 2, 4, 8, 16, 32],
            RetryPolicy.LINEAR_BACKOFF: [1, 2, 3, 4, 5, 6],
            RetryPolicy.FIXED_DELAY: [5, 5, 5, 5, 5, 5],
            RetryPolicy.IMMEDIATE: [0, 0, 0, 0, 0, 0]
        }
        
    async def start(self):
        """Start the message retry queue processing"""
        if self._running:
            return
            
        self._running = True
        self._processing_task = asyncio.create_task(self._process_queue())
        logger.info("Message retry queue started")
        
    async def stop(self):
        """Stop the message retry queue processing"""
        if not self._running:
            return
            
        self._running = False
        
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Message retry queue stopped")
        
    def add_message(self, topic: str, payload: str, qos: int = 1, 
                   retain: bool = False, max_retries: int = 5,
                   retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL_BACKOFF) -> bool:
        """Add a message to the retry queue"""
        if len(self._queue) >= self.max_queue_size:
            logger.warning("Message retry queue is full, dropping message")
            return False
            
        message = QueuedMessage(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=retain,
            max_retries=max_retries,
            retry_policy=retry_policy
        )
        
        self._queue.append(message)
        logger.debug(f"Added message to retry queue: {message.message_id}")
        return True
        
    def remove_message(self, message_id: str) -> bool:
        """Remove a specific message from the queue"""
        initial_length = len(self._queue)
        self._queue = [msg for msg in self._queue if msg.message_id != message_id]
        removed = len(self._queue) < initial_length
        
        if removed:
            logger.debug(f"Removed message from retry queue: {message_id}")
            
        return removed
        
    def clear_queue(self):
        """Clear all messages from the retry queue"""
        count = len(self._queue)
        self._queue.clear()
        logger.info(f"Cleared {count} messages from retry queue")
        
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return {
            'queue_size': len(self._queue),
            'max_queue_size': self.max_queue_size,
            'running': self._running,
            'messages': [asdict(msg) for msg in self._queue]
        }
        
    def get_retry_delay(self, message: QueuedMessage) -> float:
        """Calculate retry delay based on retry policy and count"""
        delays = self._retry_delays.get(message.retry_policy, [1])
        
        if message.retry_count < len(delays):
            return delays[message.retry_count]
        else:
            # Use last delay for any retries beyond configured delays
            return delays[-1]
            
    async def _process_queue(self):
        """Process messages in the retry queue"""
        while self._running:
            try:
                current_time = time.time()
                messages_to_send = []
                messages_to_retry = []
                messages_to_remove = []
                
                # Process queue
                for message in self._queue:
                    if message.retry_count >= message.max_retries:
                        # Max retries reached, remove message
                        messages_to_remove.append(message)
                        logger.warning(f"Max retries reached for message {message.message_id}, removing from queue")
                        continue
                        
                    if current_time >= message.next_retry_time:
                        # Ready to send
                        messages_to_send.append(message)
                    else:
                        # Still waiting
                        messages_to_retry.append(message)
                
                # Remove failed messages
                for message in messages_to_remove:
                    self.remove_message(message.message_id)
                
                # Send ready messages
                for message in messages_to_send:
                    success = self.mqtt_client.publish(
                        message.topic,
                        message.payload,
                        message.qos,
                        message.retain
                    )
                    
                    if success:
                        # Message sent successfully, remove from queue
                        self.remove_message(message.message_id)
                        logger.debug(f"Successfully sent queued message: {message.message_id}")
                    else:
                        # Failed to send, schedule retry
                        message.retry_count += 1
                        delay = self.get_retry_delay(message)
                        message.next_retry_time = current_time + delay
                        messages_to_retry.append(message)
                        logger.debug(f"Scheduled message {message.message_id} for retry in {delay}s")
                
                # Update queue
                self._queue = messages_to_retry
                
                # Wait before next check
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message retry queue: {e}")
                await asyncio.sleep(5)  # Brief delay on error
                
    async def flush_queue(self):
        """Attempt to send all messages in the queue immediately"""
        if not self._running:
            logger.warning("Message retry queue is not running")
            return
            
        current_time = time.time()
        messages_to_remove = []
        
        for message in self._queue:
            if self.mqtt_client.is_connected():
                success = self.mqtt_client.publish(
                    message.topic,
                    message.payload,
                    message.qos,
                    message.retain
                )
                
                if success:
                    messages_to_remove.append(message.message_id)
                    logger.debug(f"Flushed message: {message.message_id}")
            else:
                logger.warning("Cannot flush queue - client not connected")
                break
                
        # Remove successfully sent messages
        for message_id in messages_to_remove:
            self.remove_message(message_id)
            
        logger.info(f"Flushed {len(messages_to_remove)} messages from queue")