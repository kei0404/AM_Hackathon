```
# The DashScope SDK must be version 1.23.1 or later
import os
import dashscope

text = "Let me recommend a T-shirt to you. This one is really super good-looking. The color is very elegant, and it is also a great item for matching. You can buy it without hesitation. It is really very good-looking and very forgiving for all body types. No matter what your body shape is, you will look great in it. I recommend you to place an order."
response = dashscope.audio.qwen_tts.SpeechSynthesizer.call(
    # Only qwen-tts models are supported. Do not use other models
    model="qwen3-tts-flash-2025-11-27",
    # If the environment variable is not set, replace it with your Model Studio API key: api_key="sk-xxx"
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    text=text,
    voice="Cherry",
)
print(response)
```