# Phase 3 Implementation Plan - Step by Step

## Priority Order

### 🔴 CRITICAL PATH (Must complete first)
These enable everything else to work:

**Step 1: Provider Clients (Task 3.7)** - 12-15 hours
├─ Convert OpenAI provider to async
├─ Convert Anthropic provider to async  
├─ Convert Google provider to async
└─ Add httpx dependency

**Step 2: Database Wrappers (Task 3.8)** - 4-6 hours
├─ Create async wrapper utilities
├─ Wrap Message CRUD operations
├─ Wrap Session CRUD operations
└─ Wrap User authentication queries

**Step 3: Message Streaming (Task 3.1)** - 8-10 hours
├─ Create views_async.py
├─ Implement stream() method
├─ Handle direct mode streaming
├─ Handle compare mode streaming
└─ Test with real API calls

---

### 🟡 HIGH PRIORITY (Complete next)
Core features that users frequently use:

**Step 4: Message Regeneration (Task 3.2)** - 2-3 hours
└─ Convert regenerate endpoint to async

**Step 5: Model Comparison (Task 3.3)** - 3-4 hours
└─ Concurrent model API calls

---

### 🟢 MEDIUM PRIORITY (Nice to have)
Features that can stay sync temporarily:

**Step 6: ASR (Task 3.4)** - 1-2 hours
**Step 7: TTS (Task 3.5)** - 1-2 hours
**Step 8: Session Title (Task 3.6)** - 1 hour

---

### 🔵 LOW PRIORITY (Later)
**Step 9: Testing (Task 3.9)** - 6-8 hours

---

## Total Time Estimate
- Critical Path: 24-31 hours
- High Priority: 5-7 hours
- Medium Priority: 3-5 hours
- Testing: 6-8 hours

**TOTAL: 38-51 hours**

---

## Today's Plan (Day 1)

Let's start with **Step 1.1: OpenAI Provider Conversion**

This will take approximately **3-4 hours** and is the foundation for streaming.

