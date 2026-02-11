"""
Stress Test Configuration
CHOOSE YOUR MODE
"""

# ============================================================================
# CONFIGURATION: WHAT ARE YOU TESTING?
# ============================================================================

# Option 1: Test MOCK server (NO API calls)
TEST_MODE = "MOCK"
TARGET_URL = "http://localhost:8001"

# Option 2: Test REAL Django ASGI (WILL call APIs - costs money!)
# TEST_MODE = "REAL"
# TARGET_URL = "http://localhost:8001"

# ============================================================================

print("="*70)
print("STRESS TEST CONFIGURATION")
print("="*70)
print(f"Mode: {TEST_MODE}")
print(f"Target: {TARGET_URL}")

if TEST_MODE == "REAL":
    print()
    print("⚠️  WARNING: This will call REAL LLM APIs!")
    print("⚠️  This will cost money on your API accounts!")
    print()
    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborting...")
        exit(1)
else:
    print()
    print("✅ Using MOCK mode - No real API calls")
    print("✅ No costs incurred")
    print()

print("="*70)
print()
