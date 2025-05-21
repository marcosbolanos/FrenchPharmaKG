FROM postgres:16.9-bookworm

RUN apt-get update && \
    apt-get install -y \
        git \
        build-essential \
        postgresql-server-dev-16 \
        flex \
        bison \
        libxml2-dev \
        python3 \
        pip \
        && rm -rf /var/lib/apt/lists/*

# Clone and build Apache AGE
RUN git clone https://github.com/apache/age.git /age && \
    cd /age && \
    make && \
    make install

# Enable AGE on container start
RUN echo "shared_preload_libraries='age'" >> /usr/share/postgresql/postgresql.conf.sample

# Set environment variables
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=fpkg0_1

# Copy initialization SQL (runs automatically at runtime)
COPY init.sql /docker-entrypoint-initdb.d/

# Copy the csv loader file and requirements + the data
COPY csv_loader.py /csv_loader.py
COPY requirements.txt /requirements.txt
COPY ./csv /csv

ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install the Python librairies
RUN pip install -r requirements.txt  
