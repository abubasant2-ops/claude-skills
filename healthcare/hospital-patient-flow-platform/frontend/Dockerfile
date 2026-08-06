FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund || npm install --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The API base is baked in at build time because Next inlines
# NEXT_PUBLIC_* values; override it per environment at build.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm install --no-audit --no-fund && npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S hpf && adduser -S hpf -G hpf

COPY --from=builder --chown=hpf:hpf /app/.next ./.next
COPY --from=builder --chown=hpf:hpf /app/public ./public
COPY --from=builder --chown=hpf:hpf /app/node_modules ./node_modules
COPY --from=builder --chown=hpf:hpf /app/package.json ./package.json

USER hpf
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
