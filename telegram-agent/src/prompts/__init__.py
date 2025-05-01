"""
Prompts package initialization
"""
from .manager_prompt import TELEGRAM_ASSISTANT_MANAGER
from .email_prompt import EMAIL_AGENT
from .notion_prompt import NOTION_AGENT
from .calendar_prompt import CALENDAR_AGENT

__all__ = ['CALENDAR_AGENT', 'EMAIL_AGENT', 'NOTION_AGENT', 'TELEGRAM_ASSISTANT_MANAGER']