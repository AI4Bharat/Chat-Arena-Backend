from asgiref.sync import sync_to_async

async def make_async_generator(sync_gen):
    """
    Wraps a synchronous generator into an asynchronous generator.
    This is required for Django ASGI (Daphne) because passing a synchronous
    generator directly to StreamingHttpResponse may cause the server to
    buffer the entire response instead of streaming chunks instantly.
    """
    iterator = iter(sync_gen)
    
    def get_next():
        try:
            return next(iterator)
        except StopIteration:
            return None

    while True:
        # Ask for the next chunk in a background thread so we don't block the async loop
        chunk = await sync_to_async(get_next, thread_sensitive=False)()
        if chunk is None:
            break
        yield chunk
