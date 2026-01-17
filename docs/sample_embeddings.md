```
import dashscope
from http import HTTPStatus
input_texts = "The quality of the clothes is excellent, very beautiful. It was worth the long wait. I like it and will come back to buy here again"

resp = dashscope.TextEmbedding.call(
model="text-embedding-v4",
input=input_texts
)
print(resp)
```