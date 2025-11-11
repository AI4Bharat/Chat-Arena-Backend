FROM nginx:1.23-alpine

# Install curl for health checks
RUN apk add --no-cache openssl curl

# Create cache directory for proxy caching
RUN mkdir -p /var/cache/nginx && chown -R nginx:nginx /var/cache/nginx

# Copy log format definitions first (00- prefix ensures it loads before other configs)
COPY 00-log-formats.conf /etc/nginx/conf.d/

# Copy main configuration files
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
