from sentence_transformers import SentenceTransformer
import os

model_name = os.getenv("EMBEDDING_MODEL", "multi-qa-MiniLM-L6-cos-v1")
print(f"Downloading model: {model_name}")
model = SentenceTransformer(model_name)
print("Model downloaded successfully.")
