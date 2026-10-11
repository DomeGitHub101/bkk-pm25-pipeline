-- Runs once on first Postgres start. The airflow DB (metadata) is created by POSTGRES_DB;
-- this adds a separate database for the PM2.5 warehouse.
CREATE USER pm25 WITH PASSWORD 'pm25';
CREATE DATABASE pm25 OWNER pm25;

-- Show timestamps in Thai time when querying
ALTER DATABASE pm25 SET timezone TO 'Asia/Bangkok';
