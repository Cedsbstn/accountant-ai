import logging
import os
from langgraph.prebuilt import create_react_agent
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
from langsmith import traceable
from src.tools.email import SendEmail, FindContactEmail, ReadEmails
from src.prompts import EMAIL_AGENT
from src.utils import print_agent_output
from dotenv import load_dotenv

# --- Configuration & Initialization ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

# --- Configure Gemini ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    logger.error("GOOGLE_API_KEY not found in environment variables.")
else:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        logger.info("Google Generative AI SDK configured.")
    except Exception as e:
        logger.error(f"Failed to configure Google Generative AI SDK: {e}", exc_info=True)

# --- Define Generation Configuration ---
# These settings control the behavior of the Gemini model during generation.
# Adjust these values based on desired output creativity, consistency, and safety.
generation_config = genai.GenerationConfig(
    # Accuracy first. Lower values (e.g., 0.1-0.25) make the output more accurate and focused, which is generally better for data extraction tasks.
    temperature=0.1,

    # Maximum number of tokens to generate in the response. Adjust based on the
    # expected size of the JSON output for complex invoices. Too low might truncate JSON.
    max_output_tokens=16384, # Increased slightly for potentially complex invoices/JSON

    # Top-p sampling: Nucleus sampling. Considers only the most probable tokens
    # with cumulative probability p. Lower values make it more focused. Often used as an
    # alternative or complement to temperature. 0.95 is a common value.
    top_p=0.95,
)

# --- Define Safety Settings ---
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# Initialize LLM model
model = genai.GenerativeModel('gemini-2.0-flash')
        # For high-load applications, consider running this in a thread pool:
        # response = await asyncio.to_thread(model.generate_content, prompt)
response = model.generate_content(
            EMAIL_AGENT,
            generation_config=generation_config,
            safety_settings=safety_settings
        )

# Initialize the tools
tools = [SendEmail(), FindContactEmail(), ReadEmails()]

# Create the react agent with the specified LLM, tools, system prompt
email_agent = create_react_agent(model, tools, state_modifier=response)


@traceable(run_type="llm", name="Email Agent")
def invoke_email_agent(task: str) -> str:
    inputs = {"messages": [("user", task)]}
    output = email_agent.invoke(inputs)
    print_agent_output(output)
    return output["messages"][-1].content