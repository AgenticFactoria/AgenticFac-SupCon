# utils/mqtt_client.py
import logging
import paho.mqtt.client as mqtt
from typing import Callable
from pydantic import BaseModel

# Configure logger
logger = logging.getLogger(__name__)


class MQTTClient:
    """
    A robust wrapper for the paho-mqtt client providing easy-to-use
    methods for connecting, publishing, and subscribing.
    """

    def __init__(self, host: str, port: int, client_id: str = ""):
        self._host = host
        self._port = port
        # NOTE: The client_id is passed as the first argument for compatibility.
        self._client = mqtt.Client(client_id=client_id)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._message_callbacks = {}

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info(
                f"Successfully connected to MQTT Broker at {self._host}:{self._port}"
            )
        else:
            logger.error(
                f"Failed to connect to MQTT Broker, reason code: {reason_code}"
            )

    def _on_disconnect(self, client, userdata, reason_code, properties=None):
        logger.warning(
            f"Disconnected from MQTT Broker with reason code: {reason_code}. Reconnecting..."
        )

    def _on_message(self, client, userdata, msg):
        """
        Internal callback to route messages to the appropriate topic-specific callback.
        """
        logger.debug(f"Received message on topic {msg.topic}")
        # Iterate over subscribed topics and check for a match
        for topic_filter, callback in self._message_callbacks.items():
            if mqtt.topic_matches_sub(topic_filter, msg.topic):
                callback(msg.topic, msg.payload)
                break
        else:
            logger.warning(f"No callback registered for message on topic {msg.topic}")

    def connect(self):
        """
        Connects to the MQTT broker and starts the network loop in a separate thread.
        """
        try:
            logger.info(f"Connecting to MQTT Broker at {self._host}:{self._port}...")
            self._client.connect(self._host, self._port, 60)
            self._client.loop_start()
        except Exception as e:
            logger.error(f"Error connecting to MQTT Broker: {e}")
            raise

    def disconnect(self):
        """
        Stops the network loop and disconnects from the MQTT broker.
        """
        logger.info("Disconnecting from MQTT Broker.")
        self._client.loop_stop()
        self._client.disconnect()

    def subscribe(
        self, topic: str, callback: Callable[[str, bytes], None], qos: int = 0
    ):
        """
        Subscribes to a topic and registers a callback for incoming messages.

        Args:
            topic (str): The topic to subscribe to (can include wildcards).
            callback (Callable): A function to call when a message is received.
                                 The callback should accept (topic, payload).
            qos (int): The Quality of Service level for the subscription.
        """
        if not callable(callback):
            raise TypeError("Callback must be a callable function")

        logger.info(f"Subscribing to topic: {topic}")
        self._message_callbacks[topic] = callback
        self._client.subscribe(topic, qos)

    def publish(
        self, topic: str, payload: str | BaseModel, qos: int = 1, retain: bool = False
    ):
        """
        Publishes a message to a topic.

        Args:
            topic (str): The topic to publish to.
            payload (str | BaseModel): The message payload. If it's a Pydantic BaseModel,
                                       it will be automatically converted to a JSON string.
            qos (int): The Quality of Service level for the message.
            retain (bool): Whether the message should be retained by the broker.
        """
        if isinstance(payload, BaseModel):
            message = payload.model_dump_json()
        elif isinstance(payload, str):
            message = payload
        else:
            message = str(payload)
            # raise TypeError("Payload must be a string or a Pydantic BaseModel")

        logger.debug(f"Publishing to topic '{topic}': {message}")
        result = self._client.publish(topic, message, qos, retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(
                f"Failed to publish to topic {topic}: {mqtt.error_string(result.rc)}"
            )

    def is_connected(self):
        return self._client.is_connected()
