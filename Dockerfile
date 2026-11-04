# Use the official Python 3.12 slim image as the base
FROM python:3.12-slim-bookworm

# Install cron and essential tools for interactive terminal access
RUN apt-get update && apt-get install -y \
    cron \
    bash \
    curl \
    wget \
    vim \
    nano \
    htop \
    procps \
    tree \
    less \
    grep \
    findutils \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# coppy the requirements file to the container
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy the application code from the host /app to the container /app
COPY app/ .
                          

# Expose port 5000 for the Flask app
EXPOSE 5000

# Set environment variable to ensure Flask runs in production mode
ENV FLASK_ENV=production

# Command to run the Flask application
#CMD ["python", "app.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

# Change app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/marcdurbach/Development/python/ComEner-data-management/database/commEnergy.db'
# to point to the folder on the host machine where the database is stored
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/database/commEnergy.db'
# Execute the following commands :
# docker build -t comener_member_management .
# docker save -o commenergy_member_management.tar commenergy_member_management:latest
# docker run -d -p 8094:5000 -v $(pwd)/database:/database --name flask-container comener-data-management