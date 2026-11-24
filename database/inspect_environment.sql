-- =====================================================================
-- Banking Transaction and Fraud Detection System
-- Environment & Schema Diagnostics Script (100% READ-ONLY)
-- RV College of Engineering - DBMS (CD252IA)
-- =====================================================================
-- Purpose:
--   Executes a non-destructive inspection of your MySQL server to detect:
--   1. Server version compatibility (requires MySQL 8.0.29+).
--   2. Presence and status of 'banking_fraud_detection' and 'banking_fraud_db'.
--   3. Partial tables, row counts, indexes, foreign keys, triggers, and CHECKs.
--   4. Recommended safe deployment path.
--
-- Safe for MySQL Workbench:
--   - Does NOT create, alter, drop, insert, update, or truncate anything.
--   - Can be run safely at any time on any instance.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Server Version & Global Settings Pre-Check
-- ---------------------------------------------------------------------
SELECT 
    VERSION() AS mysql_version,
    CASE 
        WHEN (SUBSTRING_INDEX(VERSION(), '.', 1) > 8) OR
             (SUBSTRING_INDEX(VERSION(), '.', 1) = 8 AND SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 2), '.', -1) > 0) OR
             (SUBSTRING_INDEX(VERSION(), '.', 1) = 8 AND SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 2), '.', -1) = 0 
              AND CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '-', 1), '.', -1) AS UNSIGNED) >= 29)
        THEN 'COMPATIBLE (8.0.29+ supported)'
        ELSE 'WARNING: Version is below 8.0.29; IF NOT EXISTS on triggers/procedures may fail'
    END AS version_compatibility,
    @@session.sql_mode AS current_sql_mode,
    @@global.lower_case_table_names AS lower_case_table_names;

-- ---------------------------------------------------------------------
-- 2. Database Existence Check
-- ---------------------------------------------------------------------
SELECT 
    schema_name,
    default_character_set_name,
    default_collation_name
FROM information_schema.SCHEMATA
WHERE schema_name IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY schema_name;

-- ---------------------------------------------------------------------
-- 3. Table Overview & Row Counts (Both Target & Legacy Databases)
-- ---------------------------------------------------------------------
SELECT 
    table_schema AS `database`,
    table_name,
    table_rows AS approx_rows,
    engine,
    table_collation
FROM information_schema.TABLES
WHERE table_schema IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY table_schema, table_name;

-- ---------------------------------------------------------------------
-- 4. Foreign Key Inspection (Verifies RESTRICT vs CASCADE)
-- ---------------------------------------------------------------------
SELECT 
    constraint_schema AS `database`,
    table_name,
    constraint_name,
    update_rule,
    delete_rule
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE constraint_schema IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY constraint_schema, table_name, constraint_name;

-- ---------------------------------------------------------------------
-- 5. CHECK Constraints Inspection
-- ---------------------------------------------------------------------
SELECT 
    constraint_schema AS `database`,
    table_name,
    constraint_name,
    check_clause
FROM information_schema.CHECK_CONSTRAINTS
JOIN information_schema.TABLE_CONSTRAINTS USING (constraint_schema, constraint_name)
WHERE constraint_schema IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY constraint_schema, table_name, constraint_name;

-- ---------------------------------------------------------------------
-- 6. Secondary Indexes Inspection
-- ---------------------------------------------------------------------
SELECT 
    table_schema AS `database`,
    table_name,
    index_name,
    column_name,
    seq_in_index,
    non_unique
FROM information_schema.STATISTICS
WHERE table_schema IN ('banking_fraud_detection', 'banking_fraud_db')
  AND index_name NOT IN ('PRIMARY')
ORDER BY table_schema, table_name, index_name, seq_in_index;

-- ---------------------------------------------------------------------
-- 7. Triggers and Stored Routines Inspection
-- ---------------------------------------------------------------------
SELECT 
    trigger_schema AS `database`,
    event_object_table AS `table`,
    trigger_name,
    event_manipulation AS `event`,
    action_timing AS `timing`
FROM information_schema.TRIGGERS
WHERE trigger_schema IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY trigger_schema, event_object_table, trigger_name;

SELECT 
    routine_schema AS `database`,
    routine_name,
    routine_type
FROM information_schema.ROUTINES
WHERE routine_schema IN ('banking_fraud_detection', 'banking_fraud_db')
ORDER BY routine_schema, routine_name;

-- ---------------------------------------------------------------------
-- 8. Environment Diagnostics & Deployment Recommendation
-- ---------------------------------------------------------------------
SELECT 
    CASE
        -- Scenario 1: banking_fraud_detection does not exist
        WHEN NOT EXISTS (SELECT 1 FROM information_schema.SCHEMATA WHERE schema_name = 'banking_fraud_detection')
        THEN 'PATH A (Fresh Install): banking_fraud_detection does not exist. Run schema.sql -> master_data.sql -> upgrade_existing_schema.sql -> verification.sql.'

        -- Scenario 2: banking_fraud_detection exists with all 8 tables
        WHEN (SELECT COUNT(*) FROM information_schema.TABLES WHERE table_schema = 'banking_fraud_detection') = 8
        THEN 'PATH B1 (Full Schema Present): All 8 tables exist in banking_fraud_detection. Reconnect and run verification.sql to test integrity.'

        -- Scenario 3: banking_fraud_detection exists but has fewer than 8 tables (partial)
        WHEN (SELECT COUNT(*) FROM information_schema.TABLES WHERE table_schema = 'banking_fraud_detection') BETWEEN 1 AND 7
        THEN 'PATH B2 (Partial Schema Detected): Between 1 and 7 tables exist. Re-run schema.sql followed by upgrade_existing_schema.sql, then verification.sql.'

        -- Scenario 4: banking_fraud_detection exists and is empty (0 tables)
        WHEN (SELECT COUNT(*) FROM information_schema.TABLES WHERE table_schema = 'banking_fraud_detection') = 0
        THEN 'PATH A (Empty Database): Database exists but has 0 tables. Run schema.sql -> master_data.sql -> upgrade_existing_schema.sql -> verification.sql.'

        ELSE 'UNEXPECTED STATE: Review the previous result grids.'
    END AS target_db_recommendation,

    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.SCHEMATA WHERE schema_name = 'banking_fraud_db')
        THEN CONCAT('NOTE: Legacy database banking_fraud_db exists with ',
                    (SELECT COUNT(*) FROM information_schema.TABLES WHERE table_schema = 'banking_fraud_db'),
                    ' table(s). It will be ignored because scripts use banking_fraud_detection.')
        ELSE 'Legacy database banking_fraud_db does not exist.'
    END AS legacy_db_status;
