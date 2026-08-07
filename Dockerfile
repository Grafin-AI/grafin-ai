FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
# Fall back to npm install because the project does not ship with a lockfile yet.
RUN npm install

COPY . .

RUN npm run build

FROM nginx:alpine AS production

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
