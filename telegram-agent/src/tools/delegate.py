from typing import Optional, Type
# Fixed import path for CallbackManagerForToolRun
from langchain.callbacks import CallbackManagerForToolRun
# Fixed import path for traceable decorator
from langchain.smith import traceable
from pydantic import BaseModel, Field
# No changes needed - original import is correct
from langchain.tools import BaseTool

from src.agents.email import invoke_email_agent
from src.agents.calendar import invoke_calendar_agent
from src.agents.notion import invoke_notion_agent


class DelegateInput(BaseModel):
    agent_name: str = Field(description="Name of the subagent to delegate to")
    task: str = Field(description="Task to delegate to the subagent")

class Delegate(BaseTool):
    name: str = "Delegate"
    description: str = "Use this to delegate a task to one of your subagents"
    args_schema: Type[BaseModel] = DelegateInput
    
    def delegate(self, agent_name: str, task: str) -> str:
        """
        Simulates delegating a task to a subagent
        """
        print(f"Task '{task}' has been delegated to the {agent_name} agent.")
        if agent_name == "Email Agent":
            return invoke_email_agent(task)
        elif agent_name == "Calendar Agent":
            return invoke_calendar_agent(task)
        elif agent_name == "Notion Agent":
            return invoke_notion_agent(task)
        else:
            return "Invalid agent name"

    @traceable(run_type="tool", name="Delegate")
    def _run(
        self,
        agent_name: str,
        task: str,
    ) -> str:
        """Use the tool."""
        # Removed unused run_manager parameter
        """Use the tool."""
        return self.delegate(agent_name, task)