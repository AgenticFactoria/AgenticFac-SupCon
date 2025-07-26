# config/settings.py
import os

# MQTT Broker Configuration
# Use environment variables with fallback to default values
MQTT_BROKER_HOST = os.getenv("MQTT_HOST", "supos-ce-instance4.supos.app")
MQTT_BROKER_PORT = int(os.getenv("MQTT_PORT", "8083"))

# Simulation Settings
SIMULATION_SPEED = 1  # 1 = real-time, 10 = 10x speed
LOG_LEVEL = "INFO"

# Path to factory layout and game rules configurations
FACTORY_LAYOUT_PATH = "config/factory_layout.yml"
GAME_RULES_PATH = "config/game_rules.yml"
