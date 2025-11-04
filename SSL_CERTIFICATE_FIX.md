# SSL Certificate Fix - Get HTTPS Working

## Issue
Backend shows "insecure" and uses HTTP instead of HTTPS because it's using dummy certificates.

## Solution: Get Let's Encrypt Certificates

### Step 1: Ensure DNS is configured

**Before requesting Let's Encrypt certificates, verify:**

```bash
# Check if your domain resolves to your server's IP
nslookup backend.arena.ai4bharat.org

# Or use dig
dig backend.arena.ai4bharat.org

# Should show your server's public IP address
```

**Important:** Let's Encrypt will try to verify your domain by accessing:
```
http://backend.arena.ai4bharat.org/.well-known/acme-challenge/
```

Your domain MUST point to your server's public IP!

### Step 2: Request Let's Encrypt Certificate

```bash
# Run certbot to request certificate
docker-compose -f docker-compose.loadbalanced.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d backend.arena.ai4bharat.org

# If successful, you'll see:
# "Congratulations! Your certificate and chain have been saved"
```

### Step 3: Reload Nginx

```bash
# Nginx will automatically detect new certificates and reload
# But you can force reload:
docker-compose -f docker-compose.loadbalanced.yml exec nginx nginx -s reload

# Check nginx logs
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep -i certificate
```

### Step 4: Verify HTTPS works

```bash
# Test HTTPS
curl -I https://backend.arena.ai4bharat.org/health/

# Should show:
# HTTP/2 200
# (no insecure warnings)

# Test redirect HTTP → HTTPS
curl -I http://backend.arena.ai4bharat.org/health/

# Should show:
# HTTP/1.1 301 Moved Permanently
# Location: https://backend.arena.ai4bharat.org/health/
```

## Troubleshooting

### Issue: DNS not propagated

```bash
# Check DNS from multiple locations
dig backend.arena.ai4bharat.org @8.8.8.8  # Google DNS
dig backend.arena.ai4bharat.org @1.1.1.1  # Cloudflare DNS

# If different results, DNS hasn't propagated yet
# Wait 30-60 minutes and try again
```

### Issue: Let's Encrypt validation failed

```bash
# Check certbot logs
docker-compose -f docker-compose.loadbalanced.yml logs certbot

# Common issues:
# 1. Port 80 not accessible from internet
# 2. Firewall blocking port 80
# 3. Domain doesn't point to your server

# Test if port 80 is accessible:
curl http://backend.arena.ai4bharat.org/.well-known/acme-challenge/test
```

### Issue: Certificate request rate limited

Let's Encrypt has rate limits:
- 5 failed validations per hour
- 50 certificates per domain per week

If you hit the limit:
1. Wait an hour and try again
2. Or use staging server for testing:

```bash
# Test with staging (won't give real certificate, but tests the process)
docker-compose -f docker-compose.loadbalanced.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --staging \
    -d backend.arena.ai4bharat.org
```

## Alternative: Manual Certificate

If Let's Encrypt doesn't work, you can use manual certificates:

```bash
# 1. Obtain certificate from your provider (e.g., Cloudflare, AWS Certificate Manager)

# 2. Copy certificate files to the server
# You'll need:
# - fullchain.pem (certificate + chain)
# - privkey.pem (private key)

# 3. Place them in letsencrypt_certs volume
docker volume inspect letsencrypt_certs
# Note the Mountpoint path

# 4. Copy files
sudo cp fullchain.pem /var/lib/docker/volumes/letsencrypt_certs/_data/live/backend.arena.ai4bharat.org/
sudo cp privkey.pem /var/lib/docker/volumes/letsencrypt_certs/_data/live/backend.arena.ai4bharat.org/

# 5. Reload nginx
docker-compose -f docker-compose.loadbalanced.yml exec nginx nginx -s reload
```

## Certificate Auto-Renewal

Certificates expire after 90 days. The cron service should auto-renew.

**Verify auto-renewal is configured:**

```bash
# Check cron service is running
docker-compose -f docker-compose.loadbalanced.yml ps cron

# Manual renewal test
docker-compose -f docker-compose.loadbalanced.yml run --rm certbot renew --dry-run
```

---

**Summary:**
1. Ensure DNS points to your server
2. Request certificate: `docker-compose run --rm certbot certonly ...`
3. Nginx automatically switches to real certificate
4. Test: `curl -I https://backend.arena.ai4bharat.org/health/`
