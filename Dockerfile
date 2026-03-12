FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e .

# Environment variables (override at runtime)
ENV MEM0_USER_ID=user
ENV MEM0_TRANSPORT=stdio

CMD ["mem0-mcp-selfhosted"]
