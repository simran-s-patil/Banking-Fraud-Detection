-- =====================================================================
-- Banking Transaction and Fraud Detection System
-- Phase 1: Core relational schema
-- RV College of Engineering - DBMS (CD252IA)
-- Target: MySQL 8.x, InnoDB, utf8mb4
-- =====================================================================
-- This script creates the database and all eight core tables with
-- primary keys, foreign keys, constraints and indexes.
-- Safe to re-run: uses CREATE DATABASE IF NOT EXISTS and
-- CREATE TABLE IF NOT EXISTS, and every index is declared inline inside its
-- CREATE TABLE (MySQL has no CREATE INDEX IF NOT EXISTS, so standalone
-- CREATE INDEX statements would collide on a second run). Does NOT drop
-- anything. Needs MySQL 8.0.29 or later. Note: IF NOT EXISTS skips a table that already exists, it does
-- not alter it; a table created from an older definition keeps that
-- definition (new CHECKs or indexes will not be added to it).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS banking_fraud_detection
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE banking_fraud_detection;

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- 1. Customer
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Customer (
    CustomerID      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    FirstName       VARCHAR(50)  NOT NULL,
    LastName        VARCHAR(50)  NOT NULL,
    DateOfBirth     DATE         NOT NULL,
    Email           VARCHAR(100) NOT NULL,
    Phone           VARCHAR(15)  NOT NULL,
    Address         VARCHAR(255) NULL,
    CreatedAt       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_email UNIQUE (Email),
    CONSTRAINT uq_customer_phone UNIQUE (Phone)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. AccountType (master table: Savings, Current)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS AccountType (
    AccountTypeID   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    TypeName        VARCHAR(30) NOT NULL,
    Description     VARCHAR(255) NULL,
    CONSTRAINT uq_accounttype_name UNIQUE (TypeName)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. Account
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Account (
    AccountNumber   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    CustomerID      INT UNSIGNED NOT NULL,
    AccountTypeID   INT UNSIGNED NOT NULL,
    Balance         DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    AccountStatus   ENUM('ACTIVE','DORMANT','FROZEN','CLOSED') NOT NULL DEFAULT 'ACTIVE',
    CreatedAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_account_customer
        FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_account_accounttype
        FOREIGN KEY (AccountTypeID) REFERENCES AccountType(AccountTypeID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_account_balance_nonnegative CHECK (Balance >= 0),
    INDEX idx_account_customer (CustomerID),
    INDEX idx_account_accounttype (AccountTypeID)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. TransactionType (master table: P2P/UPI, CNP/e-commerce)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS TransactionType (
    TransactionTypeID INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    TypeName           VARCHAR(30) NOT NULL,
    Description        VARCHAR(255) NULL,
    CONSTRAINT uq_transactiontype_name UNIQUE (TypeName)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. Merchant
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Merchant (
    MerchantID      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    MerchantName    VARCHAR(100) NOT NULL,
    Category        VARCHAR(50)  NULL,
    Location        VARCHAR(150) NULL,
    Website         VARCHAR(150) NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 6. Transaction (single common table for P2P/UPI and CNP/e-commerce)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `Transaction` (
    TransactionID        BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    TransactionTimestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Amount                DECIMAL(15,2) NOT NULL,
    Status                ENUM('PENDING','SUCCESS','FAILED','REVERSED') NOT NULL DEFAULT 'PENDING',

    SenderAccountNumber   BIGINT UNSIGNED NOT NULL,
    ReceiverAccountNumber BIGINT UNSIGNED NULL,
    ReceiverUPIID         VARCHAR(100) NULL,

    TransactionTypeID     INT UNSIGNED NOT NULL,
    MerchantID             INT UNSIGNED NULL,

    -- DeviceID, IPAddress and Location are general ML context metadata and
    -- are allowed for every transaction category. CardReferenceToken is
    -- CNP-only (enforced by the trigger below, never a real card number).
    DeviceID               VARCHAR(100) NULL,
    IPAddress               VARCHAR(45) NULL,
    Location                 VARCHAR(150) NULL,
    CardReferenceToken        VARCHAR(100) NULL,

    -- ML fraud-scoring fields: a transaction can exist before scoring
    FraudScore              DECIMAL(5,4) NULL,
    FraudPrediction          ENUM('LEGITIMATE','FRAUDULENT') NULL,
    RiskStatus                ENUM('NOT_SCORED','LOW','MEDIUM','HIGH') NOT NULL DEFAULT 'NOT_SCORED',

    CreatedAt                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- SenderAccountNumber/ReceiverAccountNumber must use RESTRICT (not
    -- CASCADE) on both ON UPDATE and ON DELETE: MySQL error 3823 forbids a
    -- column from being covered by a CHECK constraint (here,
    -- chk_txn_sender_receiver_distinct) while also carrying a foreign-key
    -- referential action other than RESTRICT/NO ACTION. RESTRICT also
    -- matches banking semantics on its own merits: an AccountNumber must
    -- never change or disappear out from under existing transaction
    -- history, since that history has to stay auditable (NFR-10).
    CONSTRAINT fk_txn_sender
        FOREIGN KEY (SenderAccountNumber) REFERENCES Account(AccountNumber)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_txn_receiver
        FOREIGN KEY (ReceiverAccountNumber) REFERENCES Account(AccountNumber)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_txn_type
        FOREIGN KEY (TransactionTypeID) REFERENCES TransactionType(TransactionTypeID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_txn_merchant
        FOREIGN KEY (MerchantID) REFERENCES Merchant(MerchantID)
        ON UPDATE CASCADE ON DELETE RESTRICT,

    CONSTRAINT chk_txn_amount_positive CHECK (Amount > 0),
    CONSTRAINT chk_txn_sender_receiver_distinct
        CHECK (ReceiverAccountNumber IS NULL OR ReceiverAccountNumber <> SenderAccountNumber),
    CONSTRAINT chk_txn_fraudscore_range
        CHECK (FraudScore IS NULL OR (FraudScore >= 0 AND FraudScore <= 1)),
    -- Scored rows carry score + prediction + a real RiskStatus; unscored rows
    -- carry none of them.
    CONSTRAINT chk_txn_scoring_consistent CHECK (
        (FraudScore IS NULL AND FraudPrediction IS NULL AND RiskStatus = 'NOT_SCORED')
        OR (FraudScore IS NOT NULL AND FraudPrediction IS NOT NULL AND RiskStatus <> 'NOT_SCORED')
    ),
    -- NFR-03: reject a token that contains a card-number-like run of digits.
    -- Every non-alphanumeric character is stripped first, so spaces, hyphens,
    -- dots, slashes, underscores, tabs, NBSP and prefixes such as tok_<PAN>
    -- cannot hide a PAN; any 12+ consecutive digits (including fullwidth
    -- digits) are rejected. Tradeoff: a legitimate token that happens to
    -- contain 12 or more digits in a row is also rejected. tok_4f9a2c passes.
    CONSTRAINT chk_txn_card_token_not_pan CHECK (
        CardReferenceToken IS NULL
        OR NOT (REGEXP_REPLACE(CardReferenceToken, '[^[:alnum:]]', '') REGEXP '[[:digit:]]{12}')
    ),

    INDEX idx_txn_sender (SenderAccountNumber),
    INDEX idx_txn_receiver (ReceiverAccountNumber),
    INDEX idx_txn_type (TransactionTypeID),
    INDEX idx_txn_merchant (MerchantID),
    INDEX idx_txn_timestamp (TransactionTimestamp),
    INDEX idx_txn_riskstatus (RiskStatus),
    INDEX idx_txn_status (Status)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. Fraud_Alert
-- At most one alert per transaction (UNIQUE TransactionID), per the
-- ER notes' recommended clarification. A transaction may have zero
-- alerts (1:0..1 cardinality from Transaction's side).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Fraud_Alert (
    AlertID        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    TransactionID  BIGINT UNSIGNED NOT NULL,
    AlertDate      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    RiskScoreAtAlert DECIMAL(5,4) NULL,
    AlertReason    VARCHAR(255) NULL,
    ReviewStatus   ENUM('OPEN','UNDER_REVIEW','FALSE_POSITIVE','CONFIRMED_FRAUD','CLOSED')
                   NOT NULL DEFAULT 'OPEN',
    CONSTRAINT uq_alert_transaction UNIQUE (TransactionID),
    CONSTRAINT fk_alert_transaction
        FOREIGN KEY (TransactionID) REFERENCES `Transaction`(TransactionID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_alert_riskscore_range
        CHECK (RiskScoreAtAlert IS NULL OR (RiskScoreAtAlert >= 0 AND RiskScoreAtAlert <= 1)),
    INDEX idx_alert_reviewstatus (ReviewStatus)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 8. Investigation
-- An alert is allowed to exist without an investigation: a row here
-- is created only once an investigation actually starts. AlertID is
-- UNIQUE to enforce the 1:1 cardinality drawn in the ER diagram.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Investigation (
    InvestigationID   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    AlertID            INT UNSIGNED NOT NULL,
    InvestigatorName   VARCHAR(100) NOT NULL,
    StartDate          DATE NOT NULL,
    ResolutionDate     DATE NULL,
    Notes              TEXT NULL,
    Outcome            ENUM('PENDING','CONFIRMED_FRAUD','FALSE_POSITIVE','INCONCLUSIVE')
                       NOT NULL DEFAULT 'PENDING',
    ResolutionStatus   ENUM('OPEN','IN_PROGRESS','RESOLVED') NOT NULL DEFAULT 'OPEN',
    CONSTRAINT uq_investigation_alert UNIQUE (AlertID),
    CONSTRAINT fk_investigation_alert
        FOREIGN KEY (AlertID) REFERENCES Fraud_Alert(AlertID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_investigation_dates
        CHECK (ResolutionDate IS NULL OR ResolutionDate >= StartDate),
    CONSTRAINT chk_investigation_resolution CHECK (
        (ResolutionStatus = 'RESOLVED' AND ResolutionDate IS NOT NULL AND Outcome <> 'PENDING')
        OR (ResolutionStatus <> 'RESOLVED' AND ResolutionDate IS NULL)
    )
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 9. Transaction category validation (FR-17), enforced by triggers.
-- P2P_UPI: needs ReceiverAccountNumber or ReceiverUPIID; MerchantID and
--          CardReferenceToken must be NULL.
-- CNP_ECOM: ReceiverAccountNumber and ReceiverUPIID must be NULL;
--           MerchantID is optional.
-- The type is looked up by TypeName, never by a hardcoded ID. An unknown
-- TransactionTypeID (no row) is not checked here; the foreign key raises 1452.
-- A type row with an unexpected TypeName raises the 45000 error.
-- Requires MySQL 8.0.29+ (CREATE PROCEDURE/TRIGGER IF NOT EXISTS). Like
-- CREATE TABLE IF NOT EXISTS, these do not replace an existing definition.
-- ---------------------------------------------------------------------
DELIMITER $$

CREATE PROCEDURE IF NOT EXISTS sp_validate_transaction_category(
    IN p_type_id  INT UNSIGNED,
    IN p_receiver_account BIGINT UNSIGNED,
    IN p_receiver_upi VARCHAR(100),
    IN p_merchant_id INT UNSIGNED,
    IN p_card_token VARCHAR(100))
BEGIN
    DECLARE v_type VARCHAR(30);
    DECLARE v_type_rows INT;
    SET v_type_rows = (SELECT COUNT(*) FROM TransactionType WHERE TransactionTypeID = p_type_id);
    SET v_type = (SELECT TypeName FROM TransactionType WHERE TransactionTypeID = p_type_id);

    -- A type row that exists under an unexpected TypeName must not silently
    -- skip the rules. A type ID with no row at all falls through to the
    -- foreign key, which raises 1452.
    IF v_type_rows > 0 AND (v_type IS NULL OR v_type NOT IN ('P2P_UPI', 'CNP_ECOM')) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transaction type has an unexpected TypeName; expected P2P_UPI or CNP_ECOM';
    END IF;

    IF v_type = 'P2P_UPI' THEN
        IF p_receiver_account IS NULL AND NULLIF(TRIM(p_receiver_upi), '') IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'P2P_UPI transaction requires ReceiverAccountNumber or a non-blank ReceiverUPIID';
        END IF;
        IF p_merchant_id IS NOT NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'P2P_UPI transaction must not have a MerchantID';
        END IF;
        IF p_card_token IS NOT NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'P2P_UPI transaction must not have a CardReferenceToken';
        END IF;
    ELSEIF v_type = 'CNP_ECOM' THEN
        IF p_receiver_account IS NOT NULL OR p_receiver_upi IS NOT NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'CNP_ECOM transaction must not have ReceiverAccountNumber or ReceiverUPIID';
        END IF;
    END IF;
END$$

CREATE TRIGGER IF NOT EXISTS trg_txn_category_bi
BEFORE INSERT ON `Transaction` FOR EACH ROW
BEGIN
    CALL sp_validate_transaction_category(NEW.TransactionTypeID, NEW.ReceiverAccountNumber,
        NEW.ReceiverUPIID, NEW.MerchantID, NEW.CardReferenceToken);
END$$

CREATE TRIGGER IF NOT EXISTS trg_txn_category_bu
BEFORE UPDATE ON `Transaction` FOR EACH ROW
BEGIN
    CALL sp_validate_transaction_category(NEW.TransactionTypeID, NEW.ReceiverAccountNumber,
        NEW.ReceiverUPIID, NEW.MerchantID, NEW.CardReferenceToken);
END$$

DELIMITER ;

-- Give AccountNumber a bank-like starting value instead of 1, but only while
-- Account is empty and its counter is still below that value, so a re-run
-- never lowers the counter of a populated or already-advanced table.
SET SESSION information_schema_stats_expiry = 0;
SET @bfd_alter_sql = IF(
    (SELECT COUNT(*) FROM Account) = 0
    AND (SELECT AUTO_INCREMENT FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'account') < 100000000001,
    'ALTER TABLE Account AUTO_INCREMENT = 100000000001',
    'DO 0');
PREPARE bfd_alter_stmt FROM @bfd_alter_sql;
EXECUTE bfd_alter_stmt;
DEALLOCATE PREPARE bfd_alter_stmt;
