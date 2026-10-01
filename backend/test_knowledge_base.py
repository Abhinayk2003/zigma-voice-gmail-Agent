from app.agent.knowledge_base import knowledge_base_service


query = "What can the Zigma Gmail Agent do?"

text = knowledge_base_service.retrieve_text(
    query=query,
    number_of_results=5,
)

print("=" * 70)
print("KNOWLEDGE BASE RESULT")
print("=" * 70)
print(text)
