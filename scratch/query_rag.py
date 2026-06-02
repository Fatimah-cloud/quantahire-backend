import asyncio
import os
import sys

# Add project root to sys.path so we can import db and services correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.matcher import rag

async def main():
    if len(sys.argv) < 2:
        print("Usage: python query_rag.py '<search_query>'")
        return
        
    query = sys.argv[1]
    print(f"🔍 Querying RAG/Knowledge Graph for: '{query}'...")
    
    try:
        response = await rag.aquery(query=query, mode="hybrid", top_k=5)
        print("\n📄 --- RAG Response ---")
        print(response)
        print("-----------------------")
    except Exception as e:
        print(f"❌ Query failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
