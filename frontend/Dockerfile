FROM node:22-alpine
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build
EXPOSE 4173
CMD ["sh", "-c", "npm run dev -- --host 0.0.0.0 --port ${PORT:-4173}"]
