-- =====================================================================
-- Banking Transaction and Fraud Detection System
-- Phase 1: Upgrade an existing schema (safe to run in every state)
-- =====================================================================
-- Run order: schema.sql, master_data.sql, upgrade_existing_schema.sql,
-- verification.sql. schema.sql must run first (it creates missing tables, the
-- category procedure and triggers). CREATE TABLE IF NOT EXISTS skips tables that
-- already exist, so a database created from an older definition may lack newer
-- CHECK constraints and indexes. This script adds exactly those, and nothing else.
--
-- Safety:
--  * It first counts stored rows that would violate the constraints it adds
--    (result set 1). If any exist it makes NO change and says so (result set 2).
--    It never deletes or edits rows; fix the listed rows yourself, then re-run.
--  * On an already-current schema it changes nothing and says so.
--  * An old chk_txn_card_token_not_pan is replaced in ONE ALTER TABLE (drop and
--    add together), so a failure leaves the old constraint in place.
--  * No table or database is ever dropped. The only DROP is its own temporary
--    helper procedure zz_upgrade_step.
-- Works unchanged in MySQL Workbench and the mysql CLI. Read the LAST result
-- set ("upgrade_status"); in Workbench open the final "Result" tab.
-- Requires MySQL 8.0.29+.
-- =====================================================================

USE banking_fraud_detection;
SET NAMES utf8mb4;

-- 1. Pre-check (read-only): rows that would violate the constraints to be added.
SET @zz_bad_scoring = (SELECT COUNT(*) FROM `Transaction`
    WHERE NOT ((FraudScore IS NULL AND FraudPrediction IS NULL AND RiskStatus = 'NOT_SCORED')
            OR (FraudScore IS NOT NULL AND FraudPrediction IS NOT NULL AND RiskStatus <> 'NOT_SCORED')));
SET @zz_bad_card_token = (SELECT COUNT(*) FROM `Transaction`
    WHERE CardReferenceToken IS NOT NULL
      AND REGEXP_REPLACE(CardReferenceToken, '[^[:alnum:]]', '') REGEXP '[[:digit:]]{12}');
SET @zz_bad_category = (SELECT COUNT(*) FROM `Transaction` t
    JOIN TransactionType y ON y.TransactionTypeID = t.TransactionTypeID
    WHERE (y.TypeName = 'P2P_UPI'
           AND ((t.ReceiverAccountNumber IS NULL AND NULLIF(TRIM(t.ReceiverUPIID), '') IS NULL)
                OR t.MerchantID IS NOT NULL OR t.CardReferenceToken IS NOT NULL))
       OR (y.TypeName = 'CNP_ECOM' AND (t.ReceiverAccountNumber IS NOT NULL OR t.ReceiverUPIID IS NOT NULL)));
SET @zz_bad_resolution = (SELECT COUNT(*) FROM Investigation
    WHERE NOT ((ResolutionStatus = 'RESOLVED' AND ResolutionDate IS NOT NULL AND Outcome <> 'PENDING')
            OR (ResolutionStatus <> 'RESOLVED' AND ResolutionDate IS NULL)));
SET @zz_bad = @zz_bad_scoring + @zz_bad_card_token + @zz_bad_category + @zz_bad_resolution;
SET @zz_changes = 0;

SELECT @zz_bad_scoring AS bad_scoring, @zz_bad_card_token AS bad_card_token,
       @zz_bad_category AS bad_category_rules, @zz_bad_resolution AS bad_resolution,
       @zz_bad AS total_violating_rows;

-- 2. Helper: runs one statement only when it is needed AND the pre-check is clean.
DROP PROCEDURE IF EXISTS zz_upgrade_step;
DELIMITER $$
CREATE PROCEDURE zz_upgrade_step(IN p_needed BOOLEAN, IN p_sql TEXT)
BEGIN
    IF p_needed AND @zz_bad = 0 THEN
        SET @zz_sql = p_sql;
        PREPARE zz_stmt FROM @zz_sql;
        EXECUTE zz_stmt;
        DEALLOCATE PREPARE zz_stmt;
        SET @zz_changes = @zz_changes + 1;
    END IF;
END$$
DELIMITER ;

-- 3. CHECK constraints
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_txn_scoring_consistent'),
 'ALTER TABLE `Transaction` ADD CONSTRAINT chk_txn_scoring_consistent CHECK ((FraudScore IS NULL AND FraudPrediction IS NULL AND RiskStatus = ''NOT_SCORED'') OR (FraudScore IS NOT NULL AND FraudPrediction IS NOT NULL AND RiskStatus <> ''NOT_SCORED''))');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_txn_card_token_not_pan'),
 'ALTER TABLE `Transaction` ADD CONSTRAINT chk_txn_card_token_not_pan CHECK (CardReferenceToken IS NULL OR NOT (REGEXP_REPLACE(CardReferenceToken, ''[^[:alnum:]]'', '''') REGEXP ''[[:digit:]]{12}''))');
-- Old PAN regex: replace in one atomic ALTER, so the column is never unguarded.
CALL zz_upgrade_step(EXISTS(SELECT 1 FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_txn_card_token_not_pan' AND CHECK_CLAUSE NOT LIKE '%regexp_replace%'),
 'ALTER TABLE `Transaction` DROP CHECK chk_txn_card_token_not_pan, ADD CONSTRAINT chk_txn_card_token_not_pan CHECK (CardReferenceToken IS NULL OR NOT (REGEXP_REPLACE(CardReferenceToken, ''[^[:alnum:]]'', '''') REGEXP ''[[:digit:]]{12}''))');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_investigation_resolution'),
 'ALTER TABLE Investigation ADD CONSTRAINT chk_investigation_resolution CHECK ((ResolutionStatus = ''RESOLVED'' AND ResolutionDate IS NOT NULL AND Outcome <> ''PENDING'') OR (ResolutionStatus <> ''RESOLVED'' AND ResolutionDate IS NULL))');

-- 4. Indexes (the same 10 names schema.sql creates inline)
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'account' AND INDEX_NAME = 'idx_account_customer'), 'ALTER TABLE Account ADD INDEX idx_account_customer (CustomerID)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'account' AND INDEX_NAME = 'idx_account_accounttype'), 'ALTER TABLE Account ADD INDEX idx_account_accounttype (AccountTypeID)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_sender'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_sender (SenderAccountNumber)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_receiver'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_receiver (ReceiverAccountNumber)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_type'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_type (TransactionTypeID)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_merchant'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_merchant (MerchantID)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_timestamp'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_timestamp (TransactionTimestamp)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_riskstatus'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_riskstatus (RiskStatus)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME = 'idx_txn_status'), 'ALTER TABLE `Transaction` ADD INDEX idx_txn_status (Status)');
CALL zz_upgrade_step(NOT EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'fraud_alert' AND INDEX_NAME = 'idx_alert_reviewstatus'), 'ALTER TABLE Fraud_Alert ADD INDEX idx_alert_reviewstatus (ReviewStatus)');

DROP PROCEDURE IF EXISTS zz_upgrade_step;

-- 5. Outcome (read this result)
SELECT CASE
         WHEN @zz_bad > 0 THEN CONCAT('STOPPED: ', @zz_bad, ' stored row(s) violate the new constraints (see the counts above). No change was made and no row was touched. Correct those rows yourself, then run this script again.')
         WHEN @zz_changes = 0 THEN 'Schema already current: nothing changed.'
         ELSE CONCAT('Upgrade complete: ', @zz_changes, ' change(s) applied. No rows were modified.')
       END AS upgrade_status;
