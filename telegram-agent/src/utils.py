import os, requests
import aiohttp
import logging
from telegram import File as TelegramFile
from datetime import datetime

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    'https://www.googleapis.com/auth/contacts',
    "https://www.googleapis.com/auth/contacts.readonly",
    'https://www.googleapis.com/auth/gmail.readonly'
]

def print_agent_output(output):
    for message in output["messages"]:
        message.pretty_print()

# Maximum file size allowed (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB in bytes

async def download_telegram_file(file: TelegramFile, file_path: str) -> bool:
    """
    Downloads a file from Telegram to the specified path.
    
    Args:
        file: The Telegram File object to download
        file_path: The local path where the file should be saved
    
    Returns:
        bool: True if download was successful, False otherwise
    """
    try:
        logger.info(f"Downloading file {file.file_id} to {file_path}")
        await file.download_to_drive(file_path)
        return True
    except Exception as e:
        logger.error(f"Failed to download Telegram file: {e}")
        return False

async def validate_file(file_path: str) -> tuple[bool, str]:
    """
    Validates a file meets size and type requirements.
    
    Args:
        file_path: Path to the file to validate
    
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # Check file size
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        return (False, f"File size {file_size/1024/1024:.2f}MB exceeds limit of 10MB")
    
    # Check file type (basic check based on extension)
    _, file_ext = os.path.splitext(file_path.lower())
    if file_ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
        return (False, f"Unsupported file type {file_ext}. Supported types: PDF, JPG, PNG")
    
    return (True, "")

async def process_invoice_file(file_path: str) -> dict:
    """
    Processes an invoice file by sending it to the backend API.
    
    Args:
        file_path: Path to the file to process
    
    Returns:
        dict: Response from the backend API
    """
    try:
        logger.info(f"Processing invoice file: {file_path}")
        
        # Get the filename from the path
        filename = os.path.basename(file_path)
        
        # Read file content
        with open(file_path, "rb") as file:
            file_data = file.read()
        
        # Create form data
        form_data = aiohttp.FormData()
        form_data.add_field('file', file_data, filename=filename, content_type='application/octet-stream')
        
        # Send to backend
        async with aiohttp.ClientSession() as session:
            async with session.post('http://localhost:5001/process', data=form_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Successfully processed invoice: {result}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to process invoice. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Backend returned status {response.status}: {error_text}"}
    
    except Exception as e:
        logger.error(f"Error processing invoice file: {e}")
        return {"error": f"Error processing invoice: {str(e)}"}

async def send_telegram_message(text: str) -> str:
    """
    Sends a message to Telegram chat.
    
    Args:
        text: The text message to send
    
    Returns:
        str: Status message indicating success or failure
    """
    try:
        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        CHAT_ID = os.getenv("CHAT_ID")
        
        if not TELEGRAM_TOKEN or not CHAT_ID:
            logger.error("Telegram credentials not found in environment variables")
            return "Failed to send message: Missing credentials"
            
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "MarkdownV2"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                result = await response.json()
                if not result.get("ok"):
                    logger.error(f"Failed to send Telegram message: {result.get('description', 'Unknown error')}")
                    return f"Failed to send message: {result.get('description', 'Unknown error')}"
                
                logger.info("Successfully sent message via Telegram")
                return "Message sent successfully on Telegram"
                
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return f"Failed to send message: {str(e)}"

async def receive_telegram_message(after_timestamp: float) -> list:
    """
    Receives new Telegram messages since a specific timestamp.
    
    Args:
        after_timestamp: Unix timestamp to filter messages after
    
    Returns:
        list: List of new messages with text and formatted date
    """
    try:
        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        if not TELEGRAM_TOKEN:
            logger.error("Telegram token not found in environment variables")
            return []
            
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                result = await response.json()
                
                if not result.get("ok"):
                    logger.error(f"Failed to get Telegram updates: {result.get('description', 'Unknown error')}")
                    return []
                
                if not result.get("result"):
                    return []
                
                new_messages = []
                for update in result["result"]:
                    if "message" in update:
                        message = update["message"]
                        message_date = message["date"]
                        
                        if message_date > after_timestamp:
                            new_messages.append({
                                "text": message.get("text", "[No text content]"),
                                "date": datetime.fromtimestamp(message_date).strftime("%Y-%m-%d %H:%M")
                            })
                
                logger.info(f"Received {len(new_messages)} new Telegram messages")
                return new_messages
                
    except Exception as e:
        logger.error(f"Error receiving Telegram messages: {e}")
        return []