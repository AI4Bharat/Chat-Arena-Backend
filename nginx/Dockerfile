FROM nginx:1.23-alpine

# Install curl for health checks
RUN apk add --no-cache openssl curl

# Create cache directory for proxy caching
RUN mkdir -p /var/cache/nginx && chown -R nginx:nginx /var/cache/nginx

COPY default.conf /etc/nginx/conf.d/
COPY gzip.conf options-ssl-nginx.conf hsts.conf /etc/nginx/includes/
COPY site.conf.tpl /customization/
COPY nginx.sh /customization/

# Copy load balancer configurations
COPY load-balancer.conf /etc/nginx/conf.d/
COPY backend-loadbalanced.conf.tpl /customization/

RUN chmod +x /customization/nginx.sh

EXPOSE 80 443

CMD ["/customization/nginx.sh"]
