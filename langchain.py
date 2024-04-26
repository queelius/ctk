from langchain_community.document_loaders.chatgpt import ChatGPTLoader

loader = ChatGPTLoader(log_file="./example_data/fake_conversations.json", num_logs=1)
