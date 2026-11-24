-- =====================================================================
-- Banking Transaction and Fraud Detection System
-- Phase 1: Verification queries
-- =====================================================================
-- Read-only checks (A-F) plus constraint tests (section G) that run inside a
-- single transaction and are rolled back. Run schema.sql and master_data.sql
-- before this script.
--
-- Run it in a NEW connection/session: the helper procedure setup is DDL, and
-- DDL commits any work already pending in the session. If a run is
-- interrupted, the helper procedure zz_vt_run can remain until the next run
-- (which removes it; re-running in the same session also rolls back the
-- interrupted run's fixtures first).
--
-- Section G catches every expected error inside a helper procedure and
-- reports PASS/FAIL in a results table, so no error reaches the client. The
-- script runs unchanged in MySQL Workbench (primary route) and in the mysql
-- CLI without --force. From cmd.exe (not PowerShell, which rejects "<"):
--   "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p < database\verification.sql
-- Look for failed = 0 in the section G totals and PASS in the rollback check.
-- Note: on Windows (lower_case_table_names=1) information_schema shows table
-- names in lowercase, e.g. account, fraud_alert, transaction.
-- =====================================================================

USE banking_fraud_detection;

-- ---------------------------------------------------------------------
-- A. All eight tables exist
-- ---------------------------------------------------------------------
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'banking_fraud_detection'
ORDER BY TABLE_NAME;
-- Expect 8 rows: Account, AccountType, Customer, Fraud_Alert,
-- Investigation, Merchant, Transaction, TransactionType.

-- ---------------------------------------------------------------------
-- B. Inspect table structures
-- ---------------------------------------------------------------------
DESCRIBE Customer;
DESCRIBE AccountType;
DESCRIBE Account;
DESCRIBE TransactionType;
DESCRIBE Merchant;
DESCRIBE `Transaction`;
DESCRIBE Fraud_Alert;
DESCRIBE Investigation;

-- ---------------------------------------------------------------------
-- C. Verify foreign keys
-- ---------------------------------------------------------------------
SELECT
    TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'banking_fraud_detection'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, COLUMN_NAME;
-- Expect 8 foreign keys:
-- Account.CustomerID -> Customer.CustomerID
-- Account.AccountTypeID -> AccountType.AccountTypeID
-- Transaction.SenderAccountNumber -> Account.AccountNumber
-- Transaction.ReceiverAccountNumber -> Account.AccountNumber
-- Transaction.TransactionTypeID -> TransactionType.TransactionTypeID
-- Transaction.MerchantID -> Merchant.MerchantID
-- Fraud_Alert.TransactionID -> Transaction.TransactionID
-- Investigation.AlertID -> Fraud_Alert.AlertID

-- ---------------------------------------------------------------------
-- D. Verify CHECK constraints are registered
-- ---------------------------------------------------------------------
SELECT CONSTRAINT_NAME, CHECK_CLAUSE
FROM information_schema.CHECK_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'banking_fraud_detection'
ORDER BY CONSTRAINT_NAME;

-- ---------------------------------------------------------------------
-- E. Verify master data
-- ---------------------------------------------------------------------
SELECT * FROM AccountType ORDER BY AccountTypeID;
-- Expect: Savings, Current (2 rows)

SELECT * FROM TransactionType ORDER BY TransactionTypeID;
-- Expect: P2P_UPI, CNP_ECOM (2 rows)

-- ---------------------------------------------------------------------
-- F. Meaningful JOIN queries (demonstrate relationships end-to-end)
-- Phase 1 does not generate synthetic transactions, so F1-F5 return
-- 0 rows on a fresh database. That is expected: they are included to
-- demonstrate the relationships once Phase 2 data is loaded.
-- ---------------------------------------------------------------------

-- F1. Every account with its owning customer and account type
SELECT
    a.AccountNumber, c.CustomerID, c.FirstName, c.LastName,
    actype.TypeName AS AccountType, a.Balance, a.AccountStatus
FROM Account a
JOIN Customer c ON c.CustomerID = a.CustomerID
JOIN AccountType actype ON actype.AccountTypeID = a.AccountTypeID
ORDER BY a.AccountNumber;

-- F2. Every transaction with its type, sender, receiver and merchant
SELECT
    t.TransactionID, t.TransactionTimestamp, t.Amount, t.Status,
    tt.TypeName AS TransactionType,
    t.SenderAccountNumber,
    t.ReceiverAccountNumber,
    t.ReceiverUPIID,
    m.MerchantName,
    t.RiskStatus
FROM `Transaction` t
JOIN TransactionType tt ON tt.TransactionTypeID = t.TransactionTypeID
LEFT JOIN Merchant m ON m.MerchantID = t.MerchantID
ORDER BY t.TransactionID;

-- F3. Alerts with their transaction and current review status
SELECT
    fa.AlertID, fa.AlertDate, fa.ReviewStatus,
    t.TransactionID, t.Amount, t.RiskStatus, t.FraudScore
FROM Fraud_Alert fa
JOIN `Transaction` t ON t.TransactionID = fa.TransactionID
ORDER BY fa.AlertID;

-- F4. Alerts that do NOT yet have an investigation (allowed by design)
SELECT fa.AlertID, fa.TransactionID, fa.ReviewStatus
FROM Fraud_Alert fa
LEFT JOIN Investigation i ON i.AlertID = fa.AlertID
WHERE i.InvestigationID IS NULL
ORDER BY fa.AlertID;

-- F5. Full alert-to-investigation chain
SELECT
    fa.AlertID, t.TransactionID, t.Amount,
    i.InvestigationID, i.InvestigatorName, i.Outcome, i.ResolutionStatus
FROM Fraud_Alert fa
JOIN `Transaction` t ON t.TransactionID = fa.TransactionID
LEFT JOIN Investigation i ON i.AlertID = fa.AlertID
ORDER BY fa.AlertID;

-- ---------------------------------------------------------------------
-- G. Structure checks and constraint tests (positive and negative)
-- Every test runs through one helper procedure, zz_vt_run, which executes a
-- statement with PREPARE, catches any error with a handler, and records PASS
-- or FAIL by comparing the MySQL error number with the expected one
-- (0 = the statement must succeed). No error reaches the client, so this
-- section runs unchanged in Workbench and in the mysql CLI without --force.
-- All fixtures and tests run inside one transaction that is rolled back, and
-- the row counts of all 8 tables are compared before and after.
-- Expected errno: 1062 duplicate key, 1048 NULL in NOT NULL column,
-- 1265 invalid ENUM value, 1451 parent row referenced, 1452 missing parent
-- row, 1644 trigger SIGNAL (category rule), 3819 CHECK constraint violated.
-- Note: AUTO_INCREMENT counters are not transactional in InnoDB, so a gap in
-- generated IDs after this script is expected and harmless.
-- ---------------------------------------------------------------------

-- Setup before the transaction. DROP PROCEDURE below is DDL and commits any
-- open transaction, so first roll back the fixtures of an interrupted earlier
-- run in this same session (they exist only if that run did not reach its
-- ROLLBACK).
SET @vt_stale = (SELECT COUNT(*) FROM Customer WHERE Email = 'vt.a@example.invalid');
SET @vt_pre_sql = IF(@vt_stale > 0, 'ROLLBACK', 'DO 0');
PREPARE vt_pre FROM @vt_pre_sql;
EXECUTE vt_pre;
DEALLOCATE PREPARE vt_pre;

-- Strict mode must be set BEFORE the helper is created: a stored procedure
-- runs with the sql_mode it was created under. This makes the ENUM test
-- behave the same whatever the session's own mode is.
-- COALESCE keeps the ORIGINAL mode if an earlier run was interrupted after
-- switching to strict; the saved value is cleared again after the restore.
SET @vt_old_mode = COALESCE(@vt_old_mode, @@SESSION.sql_mode);
SET SESSION sql_mode = IF(@vt_old_mode = '', 'STRICT_TRANS_TABLES',
                          CONCAT(@vt_old_mode, ',STRICT_TRANS_TABLES'));

DROP PROCEDURE IF EXISTS zz_vt_run;
DROP TEMPORARY TABLE IF EXISTS vt_results;
CREATE TEMPORARY TABLE vt_results (
    n              INT AUTO_INCREMENT PRIMARY KEY,
    test_name      VARCHAR(120) NOT NULL,
    expected_errno INT NOT NULL,
    actual_errno   INT NOT NULL,
    actual_message VARCHAR(200) NULL,
    result         VARCHAR(4) NOT NULL
) ENGINE=MEMORY;  -- MEMORY is non-transactional, so ROLLBACK keeps the results

DELIMITER $$
CREATE PROCEDURE zz_vt_run(IN p_name VARCHAR(120), IN p_sql TEXT, IN p_expected INT)
BEGIN
    DECLARE v_errno INT DEFAULT 0;
    DECLARE v_msg TEXT DEFAULT NULL;
    -- 1265 (invalid ENUM value) is raised with SQLSTATE 01000, a warning
    -- class, so SQLEXCEPTION alone does not catch it.
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION, 1265
    BEGIN
        GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT;
    END;
    SET @vt_sql = p_sql;
    PREPARE vt_stmt FROM @vt_sql;
    EXECUTE vt_stmt;
    DEALLOCATE PREPARE vt_stmt;
    INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
    VALUES (p_name, p_expected, v_errno, LEFT(v_msg, 200),
            IF(v_errno = p_expected, 'PASS', 'FAIL'));
END$$
DELIMITER ;

SET @vt_before = CONCAT_WS(',',
    (SELECT COUNT(*) FROM Customer), (SELECT COUNT(*) FROM AccountType),
    (SELECT COUNT(*) FROM Account), (SELECT COUNT(*) FROM TransactionType),
    (SELECT COUNT(*) FROM Merchant), (SELECT COUNT(*) FROM `Transaction`),
    (SELECT COUNT(*) FROM Fraud_Alert), (SELECT COUNT(*) FROM Investigation));

-- Structure checks (actual_errno holds the number of violations, expected 0)
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'structure: all 8 FKs have DELETE_RULE RESTRICT', 0, bad, 'violations', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT ABS(8 - COUNT(*)) + COALESCE(SUM(DELETE_RULE <> 'RESTRICT'), 0) AS bad
      FROM information_schema.REFERENTIAL_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()) x;
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'structure: sender/receiver FKs have UPDATE_RULE RESTRICT', 0, bad, 'violations', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT ABS(2 - COUNT(*)) + COALESCE(SUM(UPDATE_RULE <> 'RESTRICT'), 0) AS bad
      FROM information_schema.REFERENTIAL_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND CONSTRAINT_NAME IN ('fk_txn_sender', 'fk_txn_receiver')) x;
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'structure: Amount and Balance are DECIMAL', 0, bad, 'violations', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT ABS(2 - COUNT(*)) + COALESCE(SUM(DATA_TYPE <> 'decimal'), 0) AS bad
      FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND ((LOWER(TABLE_NAME) = 'account' AND COLUMN_NAME = 'Balance')
          OR (LOWER(TABLE_NAME) = 'transaction' AND COLUMN_NAME = 'Amount'))) x;

INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'structure: all 10 idx_* indexes exist on the right tables', 0, 10 - COUNT(*), 'missing indexes', IF(COUNT(*) = 10, 'PASS', 'FAIL')
FROM (SELECT DISTINCT LOWER(TABLE_NAME) AS t, INDEX_NAME AS i
      FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND ((LOWER(TABLE_NAME) = 'account' AND INDEX_NAME IN ('idx_account_customer', 'idx_account_accounttype'))
          OR (LOWER(TABLE_NAME) = 'transaction' AND INDEX_NAME IN ('idx_txn_sender', 'idx_txn_receiver',
              'idx_txn_type', 'idx_txn_merchant', 'idx_txn_timestamp', 'idx_txn_riskstatus', 'idx_txn_status'))
          OR (LOWER(TABLE_NAME) = 'fraud_alert' AND INDEX_NAME = 'idx_alert_reviewstatus'))) x;

-- Row audits: stored rows (checked before any fixture exists) must obey the
-- rules, which matters for databases created from older definitions.
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'audit: stored Transaction rows obey P2P/CNP category rules', 0, bad, 'violating rows', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT COUNT(*) AS bad FROM `Transaction` t
      JOIN TransactionType y ON y.TransactionTypeID = t.TransactionTypeID
      WHERE (y.TypeName = 'P2P_UPI'
             AND ((t.ReceiverAccountNumber IS NULL AND NULLIF(TRIM(t.ReceiverUPIID), '') IS NULL)
                  OR t.MerchantID IS NOT NULL OR t.CardReferenceToken IS NOT NULL))
         OR (y.TypeName = 'CNP_ECOM' AND (t.ReceiverAccountNumber IS NOT NULL OR t.ReceiverUPIID IS NOT NULL))) x;
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'audit: stored Transaction scoring fields are consistent', 0, bad, 'violating rows', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT COUNT(*) AS bad FROM `Transaction`
      WHERE NOT ((FraudScore IS NULL AND FraudPrediction IS NULL AND RiskStatus = 'NOT_SCORED')
              OR (FraudScore IS NOT NULL AND FraudPrediction IS NOT NULL AND RiskStatus <> 'NOT_SCORED'))) x;
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'audit: no stored card-number-like CardReferenceToken', 0, bad, 'violating rows', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT COUNT(*) AS bad FROM `Transaction`
      WHERE CardReferenceToken IS NOT NULL
        AND REGEXP_REPLACE(CardReferenceToken, '[^[:alnum:]]', '') REGEXP '[[:digit:]]{12}') x;
INSERT INTO vt_results (test_name, expected_errno, actual_errno, actual_message, result)
SELECT 'audit: stored Investigation rows have consistent resolution', 0, bad, 'violating rows', IF(bad = 0, 'PASS', 'FAIL')
FROM (SELECT COUNT(*) AS bad FROM Investigation
      WHERE NOT ((ResolutionStatus = 'RESOLVED' AND ResolutionDate IS NOT NULL AND Outcome <> 'PENDING')
              OR (ResolutionStatus <> 'RESOLVED' AND ResolutionDate IS NULL))) x;

-- Master IDs are looked up by name, never hardcoded.
SET @vt_savings = (SELECT AccountTypeID FROM AccountType WHERE TypeName = 'Savings');
SET @vt_p2p     = (SELECT TransactionTypeID FROM TransactionType WHERE TypeName = 'P2P_UPI');
SET @vt_cnp     = (SELECT TransactionTypeID FROM TransactionType WHERE TypeName = 'CNP_ECOM');

START TRANSACTION;

-- Fixtures: two customers with one account each, and one merchant.
CALL zz_vt_run('fixture: customer A', 'INSERT INTO Customer (FirstName, LastName, DateOfBirth, Email, Phone) VALUES (''VtA'', ''Test'', ''1990-01-01'', ''vt.a@example.invalid'', ''9990000001'')', 0);
CALL zz_vt_run('fixture: customer B', 'INSERT INTO Customer (FirstName, LastName, DateOfBirth, Email, Phone) VALUES (''VtB'', ''Test'', ''1991-02-02'', ''vt.b@example.invalid'', ''9990000002'')', 0);
SET @vt_ca = (SELECT CustomerID FROM Customer WHERE Email = 'vt.a@example.invalid');
SET @vt_cb = (SELECT CustomerID FROM Customer WHERE Email = 'vt.b@example.invalid');
CALL zz_vt_run('fixture: account A', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance) VALUES (@vt_ca, @vt_savings, 1000.00)', 0);
CALL zz_vt_run('fixture: account B', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance) VALUES (@vt_cb, @vt_savings, 1000.00)', 0);
SET @vt_a1 = (SELECT MIN(AccountNumber) FROM Account WHERE CustomerID = @vt_ca);
SET @vt_b1 = (SELECT MIN(AccountNumber) FROM Account WHERE CustomerID = @vt_cb);
CALL zz_vt_run('fixture: merchant', 'INSERT INTO Merchant (MerchantName, Category) VALUES (''VtShop'', ''Test'')', 0);
SET @vt_m = (SELECT MAX(MerchantID) FROM Merchant WHERE MerchantName = 'VtShop');

-- Positive cases (must succeed). IDs are looked up by query, not LAST_INSERT_ID(),
-- because the helper's own INSERT into vt_results would overwrite it.
CALL zz_vt_run('P2P with receiver account (unscored by default)', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverAccountNumber, TransactionTypeID) VALUES (100.00, @vt_a1, @vt_b1, @vt_p2p)', 0);
SET @vt_tx1 = (SELECT MAX(TransactionID) FROM `Transaction` WHERE SenderAccountNumber = @vt_a1 AND ReceiverAccountNumber = @vt_b1);
CALL zz_vt_run('P2P with UPI ID only', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (50.00, @vt_a1, ''vt.user@upi'', @vt_p2p)', 0);
SET @vt_tx2 = (SELECT MAX(TransactionID) FROM `Transaction` WHERE SenderAccountNumber = @vt_a1 AND ReceiverUPIID = 'vt.user@upi' AND Amount = 50.00);
CALL zz_vt_run('P2P with DeviceID, IPAddress, Location (allowed)', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, DeviceID, IPAddress, Location) VALUES (11.00, @vt_a1, ''vt.user@upi'', @vt_p2p, ''dev-2'', ''203.0.113.10'', ''Bengaluru'')', 0);
CALL zz_vt_run('CNP with merchant and token tok_4f9a2c', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID, MerchantID, CardReferenceToken, DeviceID, IPAddress) VALUES (75.00, @vt_a1, @vt_cnp, @vt_m, ''tok_4f9a2c'', ''dev-1'', ''203.0.113.9'')', 0);
SET @vt_tx3 = (SELECT MAX(TransactionID) FROM `Transaction` WHERE SenderAccountNumber = @vt_a1 AND CardReferenceToken = 'tok_4f9a2c');
CALL zz_vt_run('CNP without merchant (merchant is optional)', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID) VALUES (20.00, @vt_a1, @vt_cnp)', 0);
CALL zz_vt_run('CNP with token of 11 digits (below PAN length)', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID, CardReferenceToken) VALUES (21.00, @vt_a1, @vt_cnp, ''tok_12345678901'')', 0);
CALL zz_vt_run('explicitly unscored transaction', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, FraudPrediction, RiskStatus) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, NULL, NULL, ''NOT_SCORED'')', 0);
CALL zz_vt_run('scored transaction', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, FraudPrediction, RiskStatus) VALUES (900.00, @vt_a1, ''vt.user@upi'', @vt_p2p, 0.9100, ''FRAUDULENT'', ''HIGH'')', 0);
SET @vt_tx5 = (SELECT MAX(TransactionID) FROM `Transaction` WHERE SenderAccountNumber = @vt_a1 AND RiskStatus = 'HIGH');
CALL zz_vt_run('alert with no investigation', 'INSERT INTO Fraud_Alert (TransactionID, AlertReason) VALUES (@vt_tx1, ''vt alert 1'')', 0);
SET @vt_al1 = (SELECT AlertID FROM Fraud_Alert WHERE TransactionID = @vt_tx1);
CALL zz_vt_run('alert for the investigated case', 'INSERT INTO Fraud_Alert (TransactionID, RiskScoreAtAlert, AlertReason) VALUES (@vt_tx5, 0.9100, ''vt alert 2'')', 0);
SET @vt_al2 = (SELECT AlertID FROM Fraud_Alert WHERE TransactionID = @vt_tx5);
CALL zz_vt_run('alert with investigation (resolved)', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate, ResolutionDate, Outcome, ResolutionStatus) VALUES (@vt_al2, ''VtInv'', ''2026-01-01'', ''2026-01-05'', ''CONFIRMED_FRAUD'', ''RESOLVED'')', 0);

-- Negative cases: uniqueness
CALL zz_vt_run('duplicate AccountType.TypeName', 'INSERT INTO AccountType (TypeName) VALUES (''Savings'')', 1062);
CALL zz_vt_run('duplicate TransactionType.TypeName', 'INSERT INTO TransactionType (TypeName) VALUES (''P2P_UPI'')', 1062);
CALL zz_vt_run('duplicate Customer.Email', 'INSERT INTO Customer (FirstName, LastName, DateOfBirth, Email, Phone) VALUES (''X'', ''Y'', ''1990-01-01'', ''vt.a@example.invalid'', ''9990000003'')', 1062);
CALL zz_vt_run('duplicate Customer.Phone', 'INSERT INTO Customer (FirstName, LastName, DateOfBirth, Email, Phone) VALUES (''X'', ''Y'', ''1990-01-01'', ''vt.c@example.invalid'', ''9990000001'')', 1062);
CALL zz_vt_run('second alert on one transaction', 'INSERT INTO Fraud_Alert (TransactionID) VALUES (@vt_tx1)', 1062);
CALL zz_vt_run('second investigation on one alert', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate) VALUES (@vt_al2, ''VtInv2'', ''2026-02-01'')', 1062);

-- Negative cases: CHECK constraints
CALL zz_vt_run('amount zero', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (0, @vt_a1, ''vt.user@upi'', @vt_p2p)', 3819);
CALL zz_vt_run('amount negative', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (-500.00, @vt_a1, ''vt.user@upi'', @vt_p2p)', 3819);
CALL zz_vt_run('UPDATE amount to zero', 'UPDATE `Transaction` SET Amount = 0 WHERE TransactionID = @vt_tx1', 3819);
CALL zz_vt_run('negative account balance', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance) VALUES (@vt_ca, @vt_savings, -1.00)', 3819);
CALL zz_vt_run('sender equals receiver', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverAccountNumber, TransactionTypeID) VALUES (10.00, @vt_a1, @vt_a1, @vt_p2p)', 3819);
CALL zz_vt_run('FraudScore above 1', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, FraudPrediction, RiskStatus) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, 1.5000, ''FRAUDULENT'', ''HIGH'')', 3819);
CALL zz_vt_run('FraudScore below 0', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, FraudPrediction, RiskStatus) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, -0.1000, ''LEGITIMATE'', ''LOW'')', 3819);
CALL zz_vt_run('RiskScoreAtAlert above 1', 'INSERT INTO Fraud_Alert (TransactionID, RiskScoreAtAlert) VALUES (@vt_tx2, 1.5000)', 3819);
CALL zz_vt_run('RiskScoreAtAlert below 0', 'INSERT INTO Fraud_Alert (TransactionID, RiskScoreAtAlert) VALUES (@vt_tx2, -0.1000)', 3819);
CALL zz_vt_run('inconsistent scoring: score but NOT_SCORED', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, FraudPrediction) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, 0.5000, ''LEGITIMATE'')', 3819);
CALL zz_vt_run('inconsistent scoring: RiskStatus HIGH without score', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, RiskStatus) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, ''HIGH'')', 3819);
CALL zz_vt_run('inconsistent scoring: score without prediction', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, FraudScore, RiskStatus) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, 0.5000, ''LOW'')', 3819);

-- Negative cases: card-number-like tokens (NFR-03). Digits hidden by any
-- separator, prefix or fullwidth form must be rejected.
SET @vt_tok_sql = 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID, CardReferenceToken) VALUES (10.00, @vt_a1, @vt_cnp, @vt_tok)';
SET @vt_tok = '4111111111111111';
CALL zz_vt_run('card token: 16 bare digits', @vt_tok_sql, 3819);
SET @vt_tok = '4111111111111111111';
CALL zz_vt_run('card token: 19 bare digits', @vt_tok_sql, 3819);
SET @vt_tok = '4111 1111 1111 1111';
CALL zz_vt_run('card token: spaces', @vt_tok_sql, 3819);
SET @vt_tok = '4111-1111-1111-1111';
CALL zz_vt_run('card token: hyphens', @vt_tok_sql, 3819);
SET @vt_tok = '4111.1111.1111.1111';
CALL zz_vt_run('card token: dots', @vt_tok_sql, 3819);
SET @vt_tok = '4111/1111/1111/1111';
CALL zz_vt_run('card token: slashes', @vt_tok_sql, 3819);
SET @vt_tok = '4111_1111_1111_1111';
CALL zz_vt_run('card token: underscores', @vt_tok_sql, 3819);
SET @vt_tok = '4111  1111--1111..1111';
CALL zz_vt_run('card token: double separators', @vt_tok_sql, 3819);
SET @vt_tok = CONCAT('4111', CHAR(9 USING utf8mb4), '1111', CHAR(9 USING utf8mb4), '1111', CHAR(9 USING utf8mb4), '1111');
CALL zz_vt_run('card token: tabs', @vt_tok_sql, 3819);
SET @vt_tok = CONCAT('4111', CONVERT(UNHEX('C2A0') USING utf8mb4), '1111', CONVERT(UNHEX('C2A0') USING utf8mb4), '1111', CONVERT(UNHEX('C2A0') USING utf8mb4), '1111');
CALL zz_vt_run('card token: non-breaking spaces', @vt_tok_sql, 3819);
SET @vt_tok = ' 4111111111111111 ';
CALL zz_vt_run('card token: leading and trailing spaces', @vt_tok_sql, 3819);
SET @vt_tok = 'tok_4111111111111111';
CALL zz_vt_run('card token: tok_ prefix plus PAN', @vt_tok_sql, 3819);
SET @vt_tok = REPEAT(CONVERT(UNHEX('EFBC91') USING utf8mb4), 16);
CALL zz_vt_run('card token: fullwidth digits', @vt_tok_sql, 3819);

-- Negative cases: investigation resolution rules
CALL zz_vt_run('resolution date before start date', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate, ResolutionDate, Outcome, ResolutionStatus) VALUES (@vt_al1, ''VtInv'', ''2026-03-10'', ''2026-03-01'', ''FALSE_POSITIVE'', ''RESOLVED'')', 3819);
CALL zz_vt_run('inconsistent resolution: RESOLVED without date', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate, Outcome, ResolutionStatus) VALUES (@vt_al1, ''VtInv'', ''2026-03-01'', ''FALSE_POSITIVE'', ''RESOLVED'')', 3819);
CALL zz_vt_run('inconsistent resolution: RESOLVED with PENDING outcome', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate, ResolutionDate, Outcome, ResolutionStatus) VALUES (@vt_al1, ''VtInv'', ''2026-03-01'', ''2026-03-02'', ''PENDING'', ''RESOLVED'')', 3819);
CALL zz_vt_run('inconsistent resolution: OPEN with resolution date', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate, ResolutionDate, ResolutionStatus) VALUES (@vt_al1, ''VtInv'', ''2026-03-01'', ''2026-03-02'', ''OPEN'')', 3819);

-- Negative cases: transaction category triggers (FR-17), INSERT
CALL zz_vt_run('trigger INSERT: P2P without any receiver', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID) VALUES (10.00, @vt_a1, @vt_p2p)', 1644);
CALL zz_vt_run('trigger INSERT: P2P with MerchantID', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, MerchantID) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, @vt_m)', 1644);
CALL zz_vt_run('trigger INSERT: P2P with CardReferenceToken', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID, CardReferenceToken) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_p2p, ''tok_ab12'')', 1644);
CALL zz_vt_run('trigger INSERT: CNP with ReceiverAccountNumber', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverAccountNumber, TransactionTypeID) VALUES (10.00, @vt_a1, @vt_b1, @vt_cnp)', 1644);
CALL zz_vt_run('trigger INSERT: CNP with ReceiverUPIID', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_cnp)', 1644);

CALL zz_vt_run('trigger INSERT: P2P with blank ReceiverUPIID', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, @vt_a1, ''   '', @vt_p2p)', 1644);
CALL zz_vt_run('trigger INSERT: P2P with empty ReceiverUPIID', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, @vt_a1, '''', @vt_p2p)', 1644);
CALL zz_vt_run('fixture: transaction type with unexpected TypeName', 'INSERT INTO TransactionType (TypeName) VALUES (''VT_OTHER'')', 0);
SET @vt_other = (SELECT MAX(TransactionTypeID) FROM TransactionType WHERE TypeName = 'VT_OTHER');
CALL zz_vt_run('trigger INSERT: existing type with unexpected TypeName', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, @vt_a1, ''vt.user@upi'', @vt_other)', 1644);

-- Negative cases: transaction category triggers (FR-17), UPDATE
CALL zz_vt_run('trigger UPDATE: P2P gets blank ReceiverUPIID and loses receiver account', 'UPDATE `Transaction` SET ReceiverAccountNumber = NULL, ReceiverUPIID = ''  '' WHERE TransactionID = @vt_tx1', 1644);
CALL zz_vt_run('trigger UPDATE: P2P loses its only receiver', 'UPDATE `Transaction` SET ReceiverAccountNumber = NULL WHERE TransactionID = @vt_tx1', 1644);
CALL zz_vt_run('trigger UPDATE: P2P gets MerchantID', 'UPDATE `Transaction` SET MerchantID = @vt_m WHERE TransactionID = @vt_tx1', 1644);
CALL zz_vt_run('trigger UPDATE: P2P gets CardReferenceToken', 'UPDATE `Transaction` SET CardReferenceToken = ''tok_ab12'' WHERE TransactionID = @vt_tx1', 1644);
CALL zz_vt_run('trigger UPDATE: CNP gets ReceiverUPIID', 'UPDATE `Transaction` SET ReceiverUPIID = ''vt.user@upi'' WHERE TransactionID = @vt_tx3', 1644);
CALL zz_vt_run('trigger UPDATE: CNP gets ReceiverAccountNumber', 'UPDATE `Transaction` SET ReceiverAccountNumber = @vt_b1 WHERE TransactionID = @vt_tx3', 1644);
CALL zz_vt_run('trigger UPDATE: P2P changed to CNP keeps receiver', 'UPDATE `Transaction` SET TransactionTypeID = @vt_cnp WHERE TransactionID = @vt_tx1', 1644);
CALL zz_vt_run('trigger UPDATE: CNP changed to P2P keeps merchant', 'UPDATE `Transaction` SET TransactionTypeID = @vt_p2p WHERE TransactionID = @vt_tx3', 1644);

-- Positive UPDATE cases (the triggers must allow valid changes)
CALL zz_vt_run('UPDATE P2P: add a UPI ID as well', 'UPDATE `Transaction` SET ReceiverUPIID = ''vt.user@upi'' WHERE TransactionID = @vt_tx1', 0);
CALL zz_vt_run('UPDATE P2P: drop receiver account, keep UPI ID', 'UPDATE `Transaction` SET ReceiverAccountNumber = NULL WHERE TransactionID = @vt_tx1', 0);
CALL zz_vt_run('UPDATE CNP: remove merchant', 'UPDATE `Transaction` SET MerchantID = NULL WHERE TransactionID = @vt_tx3', 0);

-- Negative cases: foreign keys (one per FK, 8 in total)
CALL zz_vt_run('FK Account.CustomerID', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance) VALUES (999999999, @vt_savings, 1.00)', 1452);
CALL zz_vt_run('FK Account.AccountTypeID', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance) VALUES (@vt_ca, 999999999, 1.00)', 1452);
CALL zz_vt_run('FK Transaction.SenderAccountNumber', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, 999999999999, ''vt.user@upi'', @vt_p2p)', 1452);
CALL zz_vt_run('FK Transaction.ReceiverAccountNumber', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverAccountNumber, TransactionTypeID) VALUES (10.00, @vt_a1, 999999999999, @vt_p2p)', 1452);
CALL zz_vt_run('FK Transaction.TransactionTypeID (unknown type, trigger defers)', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (10.00, @vt_a1, ''vt.user@upi'', 999999999)', 1452);
CALL zz_vt_run('FK Transaction.MerchantID', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, TransactionTypeID, MerchantID) VALUES (10.00, @vt_a1, @vt_cnp, 999999999)', 1452);
CALL zz_vt_run('FK Fraud_Alert.TransactionID', 'INSERT INTO Fraud_Alert (TransactionID) VALUES (999999999999)', 1452);
CALL zz_vt_run('FK Investigation.AlertID', 'INSERT INTO Investigation (AlertID, InvestigatorName, StartDate) VALUES (999999999, ''VtInv'', ''2026-03-01'')', 1452);

-- Negative cases: NULL, ENUM, and protection of referenced accounts
CALL zz_vt_run('NULL in required column Customer.FirstName', 'INSERT INTO Customer (FirstName, LastName, DateOfBirth, Email, Phone) VALUES (NULL, ''Y'', ''1990-01-01'', ''vt.d@example.invalid'', ''9990000004'')', 1048);
CALL zz_vt_run('NULL in required column Transaction.Amount', 'INSERT INTO `Transaction` (Amount, SenderAccountNumber, ReceiverUPIID, TransactionTypeID) VALUES (NULL, @vt_a1, ''vt.user@upi'', @vt_p2p)', 1048);
CALL zz_vt_run('invalid ENUM Account.AccountStatus', 'INSERT INTO Account (CustomerID, AccountTypeID, Balance, AccountStatus) VALUES (@vt_ca, @vt_savings, 1.00, ''BOGUS'')', 1265);
CALL zz_vt_run('DELETE Account referenced by a transaction', 'DELETE FROM Account WHERE AccountNumber = @vt_a1', 1451);
CALL zz_vt_run('UPDATE referenced AccountNumber', 'UPDATE Account SET AccountNumber = AccountNumber + 900000 WHERE AccountNumber = @vt_a1', 1451);

ROLLBACK;
SET SESSION sql_mode = @vt_old_mode;
SET @vt_old_mode = NULL;

-- Results (one row per test) and total
SELECT n, test_name, expected_errno, actual_errno, result, actual_message
FROM vt_results ORDER BY n;

SELECT COUNT(*) AS total_tests,
       SUM(result = 'PASS') AS passed,
       SUM(result = 'FAIL') AS failed
FROM vt_results;

-- Proof that nothing persisted: row counts of all 8 tables before vs after
SET @vt_after = CONCAT_WS(',',
    (SELECT COUNT(*) FROM Customer), (SELECT COUNT(*) FROM AccountType),
    (SELECT COUNT(*) FROM Account), (SELECT COUNT(*) FROM TransactionType),
    (SELECT COUNT(*) FROM Merchant), (SELECT COUNT(*) FROM `Transaction`),
    (SELECT COUNT(*) FROM Fraud_Alert), (SELECT COUNT(*) FROM Investigation));
SELECT @vt_before AS counts_before, @vt_after AS counts_after,
       IF(@vt_before = @vt_after, 'PASS: nothing persisted', 'FAIL: rows were left behind') AS rollback_check;

DROP PROCEDURE IF EXISTS zz_vt_run;
