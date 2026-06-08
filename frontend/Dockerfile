# TrustIQ frontend image - serves the static CDN-based React app via nginx.
FROM nginx:alpine

# Copy the static frontend (index.html + *.jsx) into the nginx web root.
COPY . /usr/share/nginx/html

# Custom nginx config to allow the SPA + correct JSX mime handling.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
