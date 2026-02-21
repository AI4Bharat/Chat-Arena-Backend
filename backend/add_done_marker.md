Update mock_server_realistic.py to send [DONE] marker:

Find this section in mock_server_realistic.py (around line 60-70):

    # Stream the response
    for i, word in enumerate(words):
        chunk_data = {
            "content": word + " ",
            "chunk_index": i
        }
        yield f"data: {json.dumps(chunk_data)}\n\n"
        await asyncio.sleep(WORD_DELAY)

Add [DONE] marker at the end:

    # Stream the response
    for i, word in enumerate(words):
        chunk_data = {
            "content": word + " ",
            "chunk_index": i
        }
        yield f"data: {json.dumps(chunk_data)}\n\n"
        await asyncio.sleep(WORD_DELAY)
    
    # Send completion marker
    yield f"data: [DONE]\n\n"  # ← ADD THIS LINE

