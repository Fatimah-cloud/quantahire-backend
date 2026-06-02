from openai import AsyncOpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

deepseek_client = AsyncOpenAI(
    api_key  = LLM_API_KEY,
    base_url = LLM_BASE_URL,
)

FORMAT_INSTRUCTION = (
    "IMPORTANT: You must follow the exact format with delimiters as shown in the prompt. "
    "Do not skip any fields. If a field is missing, write 'N/A'. "
    "Do not add extra explanations outside the format."
)

async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    sys_msg  = f"{system_prompt}\n\n{FORMAT_INSTRUCTION}" if system_prompt else FORMAT_INSTRUCTION
    messages = [{"role": "system", "content": sys_msg}]
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    try:
        resp = await deepseek_client.chat.completions.create(
            model       = LLM_MODEL,
            messages    = messages,
            temperature = 0,
            max_tokens  = kwargs.get("max_tokens", 1024),
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"⚠️  DeepSeek error: {e}")
        return ""

async def vision_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    return await llm_func(prompt, system_prompt, history_messages, **kwargs)
