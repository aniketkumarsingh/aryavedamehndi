-- Run this once, as the postgres superuser, to create the app's database
-- role and database. Example:
--   psql -U postgres -h localhost -f setup_db.sql
-- (it will prompt for the postgres password interactively)

CREATE ROLE aryamehndi_app WITH LOGIN PASSWORD 'changeme';
CREATE DATABASE aryamehndi OWNER aryamehndi_app;
