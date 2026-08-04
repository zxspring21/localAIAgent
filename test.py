# from transformers import AutoTokenizer, AutoModelForCausalLM

# model_id = "meta-llama/Llama-3.1-8B-Instruct"
# # model_id = "meta-llama/Llama-4-Scout-17B-16E-Instruct"

# # 載入 Token (也可以直接寫入 token="hf_...")
# tokenizer = AutoTokenizer.from_pretrained(model_id, token=True)
# model = AutoModelForCausalLM.from_pretrained(model_id, token=True, device_map="auto")

from mlx_lm import load, generate

model, tokenizer = load("mlx-community/Llama-3.2-3B-Instruct-4bit")

prompt = "hello"

if tokenizer.chat_template is not None:
    messages = [{"role": "user", "content": prompt}]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True
    )

response = generate(model, tokenizer, prompt=prompt, verbose=True)
