from langchain_community.document_loaders.chatgpt import ChatGPTLoader

loader = ChatGPTLoader(log_file="./chatgpt-data/conversations.json", num_logs=1)
loader.load()
