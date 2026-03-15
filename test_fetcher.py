import asyncio
from src.nodes.veracity_node import information_fetcher

async def test_fetcher():
    print("Testing information_fetcher node...")
    test_state = {
        "messages": [],
        "brand": "TestBrand",
        "category": "TestCategory",
        "query": "TestQuery",
        "competitors": [],
        "urls": ["https://example.com"],
        "pdf_paths": [],
        "txt_paths": [],
        "fetched_content": [],
        "adjacent_analysis": {},
        "competitor_analysis": {},
        "market_trend_analysis": {},
        "pricing_analysis": {},
        "user_voice_analysis": {},
        "win_loss_analysis": {},
        "compiled_report": {},
        "storage_status": "",
        "sse_queue": None
    }
    
    try:
        result = information_fetcher(test_state)
        print("Success! Return value keys:", result.keys())
        if "fetched_content" in result:
            amount = len(result["fetched_content"])
            print(f"Fetched {amount} items.")
            if amount > 0:
                print(f"First item preview: {result['fetched_content'][0][:100]}...")
        else:
            print("Warning: fetched_content key not in return value.")
    except Exception as e:
        print("Error encountered:", getattr(type(e), "__name__", str(type(e))), str(e))

if __name__ == "__main__":
    asyncio.run(test_fetcher())
