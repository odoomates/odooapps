FROM node:24-slim
WORKDIR /bridge
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src
ENV OM_WA_DATA=/data
VOLUME /data
USER node
CMD ["node", "src/server.js"]
