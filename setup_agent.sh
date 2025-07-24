#!/bin/bash

# SUPCON Factory Agent Setup Script

echo "🏭 Setting up SUPCON Factory Agent..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if uv is available (preferred)
if command -v uv &> /dev/null; then
    echo "📦 Using uv for dependency management..."
    
    # Add agent dependencies to uv
    uv add langchain langchain-core langgraph langchain-openai python-dotenv
    
    echo "✅ Dependencies added to uv environment"
    
else
    echo "📦 Using pip for dependency management..."
    
    # Install with pip
    pip install langchain langchain-core langgraph langchain-openai python-dotenv
    
    echo "✅ Dependencies installed with pip"
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📄 Creating .env file..."
    cp agent.env.example .env
    echo "⚠️  Please edit .env and add your OpenAI API key"
else
    echo "📄 .env file already exists"
fi

# Create agent directory if it doesn't exist
mkdir -p src/agent

echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OpenAI API key"
echo "2. Start the simulation: uv run run_multi_line_simulation.py --menu"
echo "3. Test simple agent: python src/agent/simple_agent.py"
echo "4. Run LangGraph agent: python src/agent/supcon_factory_agent.py"
echo ""
echo "📖 See AGENT_GUIDE.md for detailed instructions"
