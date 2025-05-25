FROM python:3.11-slim

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies for mysqlclient and general build tools
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY ./scripts /scripts
COPY ./app /app

RUN chmod -R +x /scripts
# Expose port for Django
EXPOSE 8000

# Default command (can be overridden in docker-compose)
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

ENV PATH="/scripts:$PATH"
CMD ["/scripts/run.sh"]

