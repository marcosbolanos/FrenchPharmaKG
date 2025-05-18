FROM postgres:16-bookworm

# Install dependencies
RUN apt-get update && \
    apt-get install -y git build-essential postgresql-server-dev-16

# Clone and build Apache AGE
RUN git clone https://github.com/apache/age.git /age && \
    cd /age && \
    make && \
    make install

# Enable AGE on container start
RUN echo "shared_preload_libraries='age'" >> /usr/share/postgresql/postgresql.conf.sample

# Copy your initialization script
COPY init.sql /docker-entrypoint-initdb.d/

# Set environment variables
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=fpkg0_1