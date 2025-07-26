# config/settings.py

# MQTT Broker Configuration
# As specified in the user request.
MQTT_BROKER_HOST = "ec2-13-212-179-9.ap-southeast-1.compute.amazonaws.com"
MQTT_BROKER_PORT = 1883

# Simulation Settings
SIMULATION_SPEED = 1  # 1 = real-time, 10 = 10x speed
LOG_LEVEL = "INFO"

# Path to factory layout and game rules configurations
FACTORY_LAYOUT_PATH = "config/factory_layout.yml"
GAME_RULES_PATH = "config/game_rules.yml"
