FROM nginx:1.25-alpine

RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/certs && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/server.key \
        -out    /etc/nginx/certs/server.crt \
        -subj "/C=IN/ST=Karnataka/L=Bangalore/O=FraudGuard/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:fraudguard.local,IP:127.0.0.1"

COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
