# Factory Control System Configuration Guide

This guide explains how to configure the Factory Control System using the centralized configuration management system.

## 📁 Configuration Files

### 1. Environment Template (`config/environment_template.env`)
Contains all available environment variables with descriptions and examples.

### 2. Agent Configuration (`config/agent_config.py`)
Centralized configuration management for all system components.

### 3. Agent Prompts (`src/agent/prompts.py`)
Centralized management of all AI agent system prompts.

## 🚀 Quick Setup

### Step 1: Create Environment File
```bash
# Copy the template
cp config/environment_template.env .env

# Edit with your values
nano .env
```

### Step 2: Set Required Variables
```bash
# Required: LLM API Key
MOONSHOT_API_KEY=your_api_key_here

# Optional: Custom topic root
TOPIC_ROOT=NLDF_YOUR_TEAM_NAME
```

### Step 3: Validate Configuration
```bash
# Test configuration
python -c "from config.agent_config import print_config, validate_environment; print_config(); validate_environment()"
```

## 🔧 Configuration Sections

### LLM Configuration
```python
from config.agent_config import get_llm_config

llm_config = get_llm_config()
print(f"Provider: {llm_config.provider}")
print(f"Model: {llm_config.model}")
print(f"API Key: {'***' if llm_config.api_key else 'Not set'}")
```

### MQTT Configuration
```python
from config.agent_config import get_mqtt_config

mqtt_config = get_mqtt_config()
print(f"Broker: {mqtt_config.host}:{mqtt_config.port}")
```

### Topic Configuration
```python
from config.agent_config import get_topic_config

topic_config = get_topic_config()
print(f"Root: {topic_config.root}")
print(f"Orders: {topic_config.orders_topic}")

# Line-specific topics
line_topics = topic_config.get_line_topics("line1")
print(f"AGV Status: {line_topics['agv_status']}")
```

### Factory Configuration
```python
from config.agent_config import get_factory_config

factory_config = get_factory_config()
print(f"MVP Lines: {factory_config.mvp_lines}")
print(f"MVP Products: {factory_config.mvp_products}")
print(f"Path Points: {factory_config.path_points}")
```

## 🤖 Agent Prompt Management

### Using Centralized Prompts
```python
from src.agent.prompts import AgentPrompts

# Get specific agent prompts
supervisor_prompt = AgentPrompts.SUPERVISOR
simple_agent_prompt = AgentPrompts.SIMPLE_AGENT

# Get line commander prompt with line ID
line1_prompt = AgentPrompts.get_line_commander_prompt("line1")

# Get prompt by role
quality_prompt = AgentPrompts.get_prompt_by_role("quality_inspector")
```

### Available Agent Roles
```python
from src.agent.prompts import AgentPrompts

roles = AgentPrompts.list_available_roles()
print("Available roles:", roles)
# Output: ['simple_agent', 'supervisor', 'line_commander', 'quality_inspector', 'maintenance_coordinator', 'energy_manager']
```

### Custom Prompt Modifications
```python
from src.agent.prompts import customize_prompt, AgentPrompts

# Add custom instructions
custom_prompt = customize_prompt(
    AgentPrompts.SUPERVISOR,
    {
        'additional_instructions': 'Focus on energy efficiency above all else.',
        'constraints': 'Never exceed 80% line capacity utilization.',
        'examples': 'Example: When efficiency drops below 70%, trigger optimization.'
    }
)
```

## ⚙️ Advanced Configuration

### Programmatic Configuration Updates
```python
from config.agent_config import get_config

config = get_config()

# Update MQTT settings
config.mqtt.host = "custom-broker.example.com"
config.mqtt.port = 1883

# Update factory settings
config.factory.mvp_lines = ["line1", "line2"]

# Update agent settings
config.agents["supervisor"].log_level = "DEBUG"
```

### Environment-Specific Configurations

#### Development Environment
```bash
# .env for development
TOPIC_ROOT=NLDF_DEV_YOURNAME
DEBUG=true
LOG_LEVEL=DEBUG
```

#### Testing Environment
```bash
# .env for testing
TOPIC_ROOT=NLDF_TEST_TEAM1
DEBUG=false
LOG_LEVEL=INFO
```

#### Production Environment
```bash
# .env for production
TOPIC_ROOT=NLDF_PROD_COMPANY
DEBUG=false
LOG_LEVEL=WARNING
```

## 🔍 Configuration Validation

### Built-in Validation
```python
from config.agent_config import validate_environment

# Validate entire configuration
is_valid = validate_environment()

if not is_valid:
    print("Configuration issues detected - check output above")
    exit(1)
```

### Manual Validation
```python
from config.agent_config import get_config

config = get_config()
issues = config.validate_config()

if issues:
    print("Configuration Issues:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("✅ Configuration is valid")
```

## 📊 Configuration Status

### Print Complete Configuration
```python
from config.agent_config import print_config

print_config()
```

Output example:
```
🔧 Factory Control System Configuration
==================================================
📡 MQTT Broker: supos-ce-instance4.supos.app:8083
🤖 LLM Provider: moonshot (kimi-k2-0711-preview)
📢 Topic Root: NLDF_YOUR_TEAM
🏭 Production Lines: ['line1']
📦 Supported Products: ['P1', 'P2']
🔍 Debug Mode: False
📊 Log Level: INFO
🤖 Enabled Agents: 2

✅ Configuration is valid
```

## 🛠️ Troubleshooting

### Common Issues

1. **Missing API Key**
   ```
   Error: LLM API key is not configured
   Solution: Set MOONSHOT_API_KEY in .env file
   ```

2. **Topic Conflicts**
   ```
   Error: Multiple agents using same topic
   Solution: Set unique TOPIC_ROOT for each deployment
   ```

3. **MQTT Connection Failed**
   ```
   Error: Connection to MQTT broker failed
   Solution: Check MQTT_HOST and MQTT_PORT settings
   ```

### Debug Mode
```bash
# Enable debug mode for detailed logging
DEBUG=true LOG_LEVEL=DEBUG python run_multi_agent.py
```

### Configuration Test Script
```bash
# Test all configuration components
python config/agent_config.py
```

## 🔄 Migration from Environment Variables

### Before (Old Way)
```python
import os
topic_root = os.getenv("TOPIC_ROOT") or "NLDF_DEFAULT"
mqtt_host = os.getenv("MQTT_HOST") or "localhost"
```

### After (New Way)
```python
from config.agent_config import get_topic_config, get_mqtt_config

topic_config = get_topic_config()
mqtt_config = get_mqtt_config()

topic_root = topic_config.root
mqtt_host = mqtt_config.host
```

## 📈 Benefits of Centralized Configuration

1. **Type Safety**: Configuration objects with proper typing
2. **Validation**: Built-in validation and error checking
3. **Documentation**: Self-documenting configuration structure
4. **Defaults**: Sensible defaults for all settings
5. **Environment Separation**: Easy switching between dev/test/prod
6. **Prompt Management**: Centralized AI agent prompt management

---

**Note**: This configuration system provides a robust foundation for managing complex factory control system deployments while maintaining flexibility and ease of use. 