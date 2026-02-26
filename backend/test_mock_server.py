"""
Simple Test - Verify Mock Server Works
Updated for claude-sonnet-4 model

Run: python test_mock_server.py
"""

import requests
import time

print("="*60)
print("TESTING MOCK SERVER - CLAUDE SONNET 4")
print("="*60)

# Test 1: Health check
print("\n1. Testing health check...")
try:
    response = requests.get("http://localhost:8002/health/")
    if response.status_code == 200:
        data = response.json()
        print(f"  ✅ Health check passed")
        print(f"     Mode: {data.get('mode', 'N/A')}")
        print(f"     Message: {data.get('message', 'N/A')}")
    else:
        print(f"  ❌ Health check failed: {response.status_code}")
except Exception as e:
    print(f"  ❌ Error: {e}")
    print("\n💡 Make sure mock server is running:")
    print("   python mock_server_realistic.py")
    exit(1)

# Test 2: Streaming
print("\n2. Testing streaming endpoint...")
try:
    payload = {
        "session_id": "test-123",
        "messages": [
            {"role": "user", "content": "Explain quantum computing"}
        ],
        "model": "claude-sonnet-4"
    }
    
    print("   Sending request...")
    start = time.time()
    response = requests.post(
        "http://localhost:8002/api/messages/stream/",
        json=payload,
        stream=True
    )
    
    if response.status_code == 200:
        print("   ✅ Connection established")
        print("   📡 Streaming response:")
        print("   ", end="")
        
        chunks_received = 0
        bytes_received = 0
        
        for line in response.iter_lines():
            if line:
                chunks_received += 1
                bytes_received += len(line)
                
                decoded = line.decode('utf-8')
                
                # Extract content from SSE data format
                if decoded.startswith('data: '):
                    data_content = decoded[6:]  # Remove 'data: ' prefix
                    
                    if data_content != '[DONE]':
                        try:
                            import json
                            content_json = json.loads(data_content)
                            if 'content' in content_json:
                                print(content_json['content'], end='', flush=True)
                        except json.JSONDecodeError:
                            pass
        
        duration = time.time() - start
        
        print(f"\n\n   ✅ Streaming complete ({duration:.2f}s)")
        print(f"   📊 Stats:")
        print(f"      Chunks: {chunks_received}")
        print(f"      Bytes: {bytes_received}")
        print(f"      Rate: {chunks_received/duration:.1f} chunks/sec")
        
        # Validate response quality
        if chunks_received >= 10 and bytes_received >= 1000:
            print(f"   ✅ Response quality: GOOD")
        else:
            print(f"   ⚠️  Response quality: Low (chunks: {chunks_received}, bytes: {bytes_received})")
    else:
        print(f"   ❌ Failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("✅ Mock server basic test complete!")
print("\nYou can now run the full stress test:")
print("  python stress_test_with_validation.py")
print()
print("This will test up to 3000 concurrent users!")
print("="*60)
