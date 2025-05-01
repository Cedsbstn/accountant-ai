from typing import Annotated, Literal, TypedDict, Callable, Awaitable
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.graph.message import AnyMessage, add_messages
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from src.prompts.manager_prompt import TELEGRAM_ASSISTANT
from src.agents.email import invoke_email_agent
from src.agents.calendar import invoke_calendar_agent
from src.agents.notion import invoke_notion_agent
from src.tools.delegate import Delegate
from backend.models import Checkpoint
from backend.dependencies import get_db
import logging
import json  # Added for JSON serialization
from functools import partial
from typing import Any, Dict, List, Optional, AsyncGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MySQLSaver:
    """MySQL-compatible saver using the backend's database connection"""
    
    def __init__(self, db_generator):
        self.db_generator = db_generator
    
    async def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Retrieve checkpoint from MySQL database"""
        async for db in self.db_generator():
            try:
                checkpoint = await db.get(Checkpoint, config["thread_id"])
                if checkpoint:
                    return checkpoint.checkpoint
                return None
            except Exception as e:
                logger.error(f"Error retrieving checkpoint: {e}")
                return None
    
    async def list(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List checkpoints from MySQL database"""
        async for db in self.db_generator():
            try:
                result = await db.execute(
                    Checkpoint.select().order_by(Checkpoint.updated_at.desc()).limit(limit)
                )
                return [dict(r) for r in result]
            except Exception as e:
                logger.error(f"Error listing checkpoints: {e}")
                return []
    
    async def put(self, config: Dict[str, Any], checkpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Save checkpoint to MySQL database"""
        async for db in self.db_generator():
            try:
                # Use proper JSON serialization with default handler
                config_data = json.dumps(config, default=str)
                
                # Create or update checkpoint with JSON serialization
                checkpoint_data = {
                    "thread_id": config["thread_id"],
                    "checkpoint": json.dumps(checkpoint),  # Serialize checkpoint
                    "config_data": config_data
                }
                
                # Use upsert operation
                await db.merge(Checkpoint(**checkpoint_data))
                await db.commit()
                
                return checkpoint
            except Exception as e:
                logger.error(f"Error saving checkpoint: {e}")
                await db.rollback()
                raise  # Re-raise the exception after rollback

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

class ManagerAgent:
    def __init__(self, llm):
        self.tools = [Delegate()]
        self.model = llm.bind_tools(self.tools)
        self.checkpointer = MySQLSaver(partial(get_db))
        self.workflow = self.create_workflow()
    
    def create_workflow(self):
        workflow = StateGraph(State)
        
        workflow.add_node("telegram_agent", self.call_model)
        workflow.add_node("email_agent", self.call_email_agent)
        workflow.add_node("calendar_agent", self.call_calendar_agent)
        workflow.add_node("notion_agent", self.call_notion_agent)
        
        workflow.add_edge(START, "telegram_agent")
        
        workflow.add_conditional_edges(
            "telegram_agent",
            self.route_primary_assistant,
            {
                "email_agent": "email_agent",
                "calendar_agent": "calendar_agent",
                "notion_agent": "notion_agent",
                END: END,
            },
        )
        
        workflow.add_edge("email_agent", 'telegram_agent')
        workflow.add_edge("calendar_agent", 'telegram_agent')
        workflow.add_edge("notion_agent", 'telegram_agent')
        
        self.app = workflow.compile(self.checkpointer)
        
        return self.app
    
    def call_model(self, state: State):
        print("Calling Telegram agent")
        messages = state['messages']
        response = self.model.invoke(messages)
        return {"messages": [response]}

    def route_primary_assistant(self, state: State) -> Literal[
        "email_agent", "calendar_agent", "notion_agent", "__end__"
    ]:
        """Route to appropriate agent based on tool calls with validation"""
        if tools_condition(state) == END:
            return END
            
        tool_calls = state["messages"][-1].tool_calls
        if not tool_calls:
            raise ValueError("No tool calls found in state for routing")
            
        tool_call = tool_calls[0]
        if tool_call["name"] != Delegate.__name__:
            raise ValueError(f"Unexpected tool call name: {tool_call['name']}")
            
        agent_name = tool_call['args'].get("agent_name")
        if not agent_name or agent_name not in self.agent_map:
            raise ValueError(f"Invalid agent name: {agent_name} - valid options are {list(self.agent_map.keys())}")
            
        return self.agent_map[agent_name]

    def _create_agent_caller(self, agent_func: Callable[[str], str]) -> Callable[[State], Dict[str, Any]]:
        """Factory method to create agent caller functions"""
        def caller(state: State):
            logger.debug(f"Invoking agent via {agent_func.__name__}")
            tool_call = state["messages"][-1].tool_calls[0]
            task = tool_call['args']["task"]
            response = agent_func(task)
            return {"messages": [ToolMessage(
                content=response,
                name="Delegate",
                tool_call_id=tool_call['id']
            )]}
        return caller

    # Create agent-specific callers using the factory method
    call_email_agent = _create_agent_caller(invoke_email_agent)
    call_calendar_agent = _create_agent_caller(invoke_calendar_agent)
    call_notion_agent = _create_agent_caller(invoke_notion_agent)

    def call_notion_agent(self, state: State):
        print("Calling notion agent")
        last_manager_tool_calls = state["messages"][-1].tool_calls
        task = last_manager_tool_calls[0]['args']["task"]
        tool_call_id = last_manager_tool_calls[0]['id']
        response = invoke_notion_agent(task)
        
        return {"messages": [ToolMessage(content=response, name="Delegate", tool_call_id=tool_call_id)]}
    
    def invoke(self, message, config):
        """Process a message through the workflow with proper state initialization"""
        try:
            current_state = self.app.get_state(config=config).values
            if not current_state.get("messages"):
                self.app.update_state(
                    config,
                    {"messages": [SystemMessage(content=TELEGRAM_ASSISTANT)]}
                )
        except Exception as e:
            logger.error(f"Error initializing state: {e}", exc_info=True)
            raise
            
        try:
            sent_message = HumanMessage(content=message)
            final_state = self.app.invoke({"messages": [sent_message]}, config=config)
            return final_state["messages"][-1].content
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            raise
