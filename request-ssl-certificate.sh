#!/bin/bash

# SSL Certificate Request Script
# Run this on your server after DNS is correctly configured

set -e  # Exit on error

echo "=========================================="
echo "SSL Certificate Request Script"
echo "=========================================="
echo ""

# Configuration
DOMAIN="backend.arena.ai4bharat.org"
EMAIL="your-email@ai4bharat.org"  # CHANGE THIS!

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Verifying DNS configuration${NC}"
echo "Checking if $DOMAIN points to this server..."
DNS_IP=$(nslookup $DOMAIN | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)
SERVER_IP=$(curl -s ifconfig.me)

echo "DNS resolves to: $DNS_IP"
echo "This server's IP: $SERVER_IP"

if [ "$DNS_IP" != "$SERVER_IP" ]; then
    echo -e "${RED}ERROR: DNS mismatch!${NC}"
    echo "DNS points to $DNS_IP but this server is $SERVER_IP"
    echo "Please update your DNS A record to point to $SERVER_IP"
    echo "Then wait 5-15 minutes and run this script again."
    exit 1
fi

echo -e "${GREEN}✓ DNS is correctly configured${NC}"
echo ""

echo -e "${YELLOW}Step 2: Checking Docker containers${NC}"
cd ~/Chat-Arena-Backend || cd /home/$(whoami)/Chat-Arena-Backend || { echo "Chat-Arena-Backend directory not found"; exit 1; }

if ! docker compose -f docker-compose.loadbalanced.yml ps | grep -q "Up"; then
    echo -e "${RED}ERROR: Containers are not running${NC}"
    echo "Starting containers..."
    docker compose -f docker-compose.loadbalanced.yml up -d
    echo "Waiting 30 seconds for containers to start..."
    sleep 30
fi

echo -e "${GREEN}✓ Containers are running${NC}"
echo ""

echo -e "${YELLOW}Step 3: Testing HTTP access (required for Let's Encrypt)${NC}"
if ! curl -f -s http://localhost/health/ > /dev/null; then
    echo -e "${RED}ERROR: Cannot reach http://localhost/health/${NC}"
    echo "Check nginx logs:"
    docker compose -f docker-compose.loadbalanced.yml logs nginx | tail -20
    exit 1
fi

echo -e "${GREEN}✓ HTTP endpoint accessible${NC}"
echo ""

echo -e "${YELLOW}Step 4: Requesting Let's Encrypt certificate${NC}"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# Check if certificate already exists
if [ -d "./certbot/conf/live/$DOMAIN" ]; then
    echo -e "${YELLOW}Certificate already exists. Renewing...${NC}"
    docker compose -f docker-compose.loadbalanced.yml run --rm certbot renew
else
    echo "Requesting new certificate..."
    docker compose -f docker-compose.loadbalanced.yml run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Certificate request failed${NC}"
    echo "Check certbot logs:"
    docker compose -f docker-compose.loadbalanced.yml logs certbot | tail -30
    exit 1
fi

echo -e "${GREEN}✓ Certificate obtained successfully${NC}"
echo ""

echo -e "${YELLOW}Step 5: Reloading Nginx${NC}"
docker compose -f docker-compose.loadbalanced.yml exec nginx nginx -s reload

echo -e "${GREEN}✓ Nginx reloaded${NC}"
echo ""

echo -e "${YELLOW}Step 6: Testing HTTPS${NC}"
sleep 2

if curl -f -s -I https://$DOMAIN/health/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ HTTPS is working!${NC}"
    echo ""
    echo "Testing full response:"
    curl -s https://$DOMAIN/health/ | python3 -m json.tool || curl -s https://$DOMAIN/health/
else
    echo -e "${YELLOW}Note: HTTPS test had issues. Checking details...${NC}"
    curl -I https://$DOMAIN/health/ 2>&1 | head -10
fi

echo ""
echo "=========================================="
echo -e "${GREEN}SSL Certificate Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Visit https://$DOMAIN/admin/ - should show no security warnings"
echo "2. Visit https://$DOMAIN/swagger/ - should work over HTTPS"
echo "3. Test with your frontend application"
echo ""
echo "Certificate will auto-renew. Check renewal status with:"
echo "  docker compose -f docker-compose.loadbalanced.yml run --rm certbot renew --dry-run"
