FROM node:22-alpine

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

ARG NEXT_PUBLIC_AGENTQA_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_AGENTQA_API_URL=$NEXT_PUBLIC_AGENTQA_API_URL

COPY package.json pnpm-lock.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@10.12.2 --activate \
    && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
