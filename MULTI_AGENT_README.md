# Multi-Agent Factory Control System

This document describes the **Multi-Agent Factory Control System** - a hierarchical AI-driven factory management solution built with modern agent frameworks.

## 🏗️ Architecture Overview

The system implements a **hierarchical multi-agent architecture** with clear separation of responsibilities:

### 🤖 Agent Hierarchy

1. **Supervisor Agent** (Global Level)
   - 📋 **Order Allocation**: Assigns incoming orders to production lines
   - 📊 **KPI Monitoring**: Tracks factory-wide performance metrics
   - 🔄 **Load Balancing**: Distributes workload across production lines
   - 🎯 **Strategic Optimization**: Makes high-level efficiency decisions

2. **Line Commander Agents** (Line Level)  
   - 🚛 **AGV Control**: Manages 2 AGVs per production line
   - ⚙️ **Local Optimization**: Optimizes line-specific operations
   - 🔧 **Equipment Monitoring**: Tracks station and conveyor status
   - 📦 **Order Execution**: Implements assigned production orders

## 🚀 Quick Start

### Prerequisites

Ensure you have the required environment setup:

```bash
# Install dependencies
uv sync

# Set environment variables
export MOONSHOT_API_KEY="your_api_key_here"
export TOPIC_ROOT="your_unique_topic"  # Optional, defaults based on username
```

### Running the Multi-Agent System

```bash
# Basic startup (MVP - line1 only)
python run_multi_agent.py

# With debug logging
python run_multi_agent.py --debug

# Future: Multi-line support
python run_multi_agent.py --line-count 3
```

### Expected Output

```
🏭 ========================================================
   SUPCON Multi-Agent Factory Control System
🏭 ========================================================

🤖 Architecture:
   ├── Supervisor Agent (Global Coordinator)
   │   ├── Order allocation & scheduling
   │   ├── KPI monitoring & optimization
   │   └── Cross-line coordination
   └── Line Commander Agents (Line Control)
       ├── AGV management & routing
       ├── Local production optimization
       └── Equipment monitoring

🚀 Starting system...
🏭 Multi-Agent Factory System Started
📡 Root Topic: NLDF_YOUR_USERNAME
🤖 Agents: 1 Supervisor + 1 Line Commanders
🚀 System is running... Press Ctrl+C to stop
```

## 📡 MQTT Communication

The agents communicate via MQTT topics with clear responsibility boundaries:

### Global Topics (Supervisor Agent)
- `{ROOT}/orders/status` - New order notifications
- `{ROOT}/kpi/status` - Factory-wide KPI updates  
- `{ROOT}/warehouse/+/status` - Warehouse status
- `{ROOT}/result/status` - Final results

### Line-Specific Topics (Line Commander Agents)
- `{ROOT}/{line_id}/agv/+/status` - AGV status updates
- `{ROOT}/{line_id}/station/+/status` - Station status
- `{ROOT}/{line_id}/conveyor/+/status` - Conveyor status
- `{ROOT}/{line_id}/alerts` - Equipment alerts
- `{ROOT}/command/{line_id}` - AGV commands (publish)
- `{ROOT}/response/{line_id}` - Command responses

## 🎯 Agent Decision Making

### Supervisor Agent Logic

```python
# Example decision flow:
if new_order_received:
    analyze_order_requirements()
    evaluate_line_capacities() 
    consider_current_kpi_metrics()
    assign_to_optimal_line(priority_level)
    
if kpi_threshold_breached:
    analyze_performance_bottlenecks()
    suggest_optimization_actions()
```

### Line Commander Agent Logic

```python
# Example AGV coordination:
if agv_becomes_idle:
    check_pending_tasks()
    evaluate_battery_level()
    coordinate_with_other_agvs()
    make_ai_assisted_decision()
    
if order_assigned:
    plan_product_workflow()
    assign_optimal_agv()
    execute_task_sequence()
```

## 🔧 Extensibility

The system is designed for easy expansion:

### Adding More Production Lines

```python
# In multi_agent_system.py
for line_id in ["line1", "line2", "line3"]:  # Extend here
    self.line_commanders[line_id] = LineCommanderAgent(...)
```

### Adding New Agent Types

1. Create new agent class inheriting base patterns
2. Define specific responsibilities and prompts
3. Register in the MultiAgentFactoryController
4. Configure MQTT subscriptions

### Product Type Support

Currently supports **P1 and P2** products (MVP). To add **P3** support:

1. Update product workflows in agent prompts
2. Extend line commander logic for P3 routing
3. Add P3-specific optimization rules

## 🐛 Debugging

### Debug Mode
```bash
python run_multi_agent.py --debug
```

### Log Files
- `multi_agent_factory.log` - Detailed operation logs
- Console output - Real-time status updates

### Common Issues

1. **Agent Import Errors**: Ensure `openai-agents` package is installed
2. **MQTT Connection**: Check broker settings in `config/settings.py`
3. **API Key**: Verify `MOONSHOT_API_KEY` environment variable
