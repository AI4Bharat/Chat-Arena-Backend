# PostgreSQL Driver Migration Plan (Future Optimization)

## Current: psycopg2-binary (Sync Only)

**Version:** 2.9.10  
**Type:** Synchronous only  
**Status:** ✅ Works for current setup

### Limitations
- No native async support
- All ORM queries in async views require \sync_to_async\
- Connection pooling not optimized for async

---

## Future: psycopg3 (Async Native)

**Version:** 3.1+  
**Type:** Supports both sync and async  
**Status:** ⚠️ Optional upgrade for Phase 5+

### Benefits
- Native async database queries
- Better connection pooling
- Improved performance in async views
- No \sync_to_async\ overhead

### Migration Steps (Post-Hybrid Launch)

1. **Install psycopg3**
   \\\ash
   pip install 'psycopg[binary,pool]>=3.1'
   pip uninstall psycopg2-binary
   \\\

2. **Update settings.py**
   \\\python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'OPTIONS': {
               'pool': {
                   'min_size': 2,
                   'max_size': 10,
               },
           },
           # ... other settings
       }
   }
   \\\

3. **Use async ORM (Django 4.2+)**
   \\\python
   # Instead of sync_to_async
   async def get_messages(session_id):
       messages = await Message.objects.filter(session_id=session_id).aiterator()
       return [msg async for msg in messages]
   \\\

### Timeline
- **Phase 1-4:** Keep psycopg2-binary
- **Phase 5+:** Test psycopg3 in staging
- **Phase 6+:** Consider production migration

### Risk Assessment
- **Risk Level:** Low (both drivers supported by Django)
- **Rollback:** Easy (switch back to psycopg2-binary)
- **Impact:** Performance boost, cleaner async code

---

**Decision:** Defer to post-launch optimization

**Rationale:**
- Current setup works fine with \sync_to_async\
- Focus on hybrid architecture first
- Minimize migration scope and risk

---

**Status:** Documented for future consideration
