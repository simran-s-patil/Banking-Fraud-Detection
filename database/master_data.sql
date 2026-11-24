-- =====================================================================
-- Banking Transaction and Fraud Detection System
-- Phase 1: Master/reference data
-- =====================================================================
-- Seeds AccountType and TransactionType master records.
-- Uses INSERT ... SELECT ... WHERE NOT EXISTS on the UNIQUE TypeName, so a
-- re-run inserts nothing: no duplicates, no overwritten (edited) Descriptions,
-- no AUTO_INCREMENT movement and no warning 1287.
-- =====================================================================

USE banking_fraud_detection;

SET NAMES utf8mb4;

INSERT INTO AccountType (TypeName, Description)
SELECT v.TypeName, v.Description
FROM (
    SELECT 'Savings' AS TypeName, 'Interest-bearing account intended for personal savings' AS Description
    UNION ALL
    SELECT 'Current', 'Non-interest-bearing account intended for frequent transactions'
) AS v
WHERE NOT EXISTS (SELECT 1 FROM AccountType a WHERE a.TypeName = v.TypeName);

INSERT INTO TransactionType (TypeName, Description)
SELECT v.TypeName, v.Description
FROM (
    SELECT 'P2P_UPI' AS TypeName, 'Real-time peer-to-peer transfer via UPI' AS Description
    UNION ALL
    SELECT 'CNP_ECOM', 'Card-not-present e-commerce purchase'
) AS v
WHERE NOT EXISTS (SELECT 1 FROM TransactionType t WHERE t.TypeName = v.TypeName);
