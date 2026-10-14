# Frontend image for Labor Evidence Organizer (Next.js 14).
#
# Authored to spec; validated by static review only (no Docker in this
# environment) — see docs/17 §13 (9-D-4).
#
# NEXT_PUBLIC_* vars are inlined by Next at BUILD time, so the API base URL
# must be provided as a build arg (compose maps environment → build args).
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked into the client bundle at build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# next.config.js has no `output: "standalone"`, so keep the full node_modules
# and use `next start`.
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/next.config.js ./
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
