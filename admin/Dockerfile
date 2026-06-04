FROM nginx:1.27-alpine

ARG GIT_COMMIT_HASH=unknown
ENV GIT_COMMIT_HASH=$GIT_COMMIT_HASH

RUN rm /etc/nginx/conf.d/default.conf

COPY admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY admin/src/ /usr/share/nginx/html/

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
