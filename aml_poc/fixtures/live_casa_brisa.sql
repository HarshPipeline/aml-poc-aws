-- Live Casa Brisa episode 3. Run in CloudShell on aml-kyc-db / aml_demo after \c aml_demo
-- Payments sit 20 days after the last Casa row so they form a new funnel cluster.
-- The AML app watches TXN-LIVE-C002-* and opens one new case when this cluster is complete.
-- If these IDs already exist, run reset_live_casa_brisa.sql first.

WITH origin AS (
    SELECT coalesce(
        max(txn_ts) FILTER (
            WHERE customer_id = 'C002' AND transaction_id NOT LIKE 'TXN-LIVE-C002-%'
        ),
        timezone('utc', now())
    ) + interval '20 days' AS base_ts
    FROM transactions
)
INSERT INTO transactions (
    transaction_id, account_id, customer_id, txn_ts, txn_type, direction, amount, currency,
    cash_flag, channel, branch_id, branch_state, counterparty_id, counterparty_country,
    depositor_id, depositor_is_customer, originator_name, originator_country, beneficiary_name,
    purpose_field, invoice_id, check_number, is_round_amount, description
)
SELECT * FROM (
    SELECT
        'TXN-LIVE-C002-01', 'ACC-C002-01', 'C002', origin.base_ts + interval '1 minute',
        'cash_deposit', 'INCOMING', 4200.00, 'USD', TRUE, 'BRANCH_TELLER',
        'SYNTH-BR-TX-053', 'TX', NULL::text, NULL::text, 'DEP-LIVE-01', FALSE,
        NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, FALSE, 'Cash deposit'
    FROM origin
    UNION ALL
    SELECT
        'TXN-LIVE-C002-02', 'ACC-C002-01', 'C002', origin.base_ts + interval '2 minutes',
        'cash_deposit', 'INCOMING', 3800.00, 'USD', TRUE, 'BRANCH_TELLER',
        'SYNTH-BR-NV-011', 'NV', NULL::text, NULL::text, 'DEP-LIVE-02', FALSE,
        NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, FALSE, 'Cash deposit'
    FROM origin
    UNION ALL
    SELECT
        'TXN-LIVE-C002-03', 'ACC-C002-01', 'C002', origin.base_ts + interval '3 minutes',
        'cash_deposit', 'INCOMING', 3500.00, 'USD', TRUE, 'BRANCH_TELLER',
        'SYNTH-BR-TX-053', 'TX', NULL::text, NULL::text, 'DEP-LIVE-03', FALSE,
        NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, FALSE, 'Cash deposit'
    FROM origin
    UNION ALL
    SELECT
        'TXN-LIVE-C002-04', 'ACC-C002-01', 'C002', origin.base_ts + interval '4 minutes',
        'check', 'OUTGOING', 4000.00, 'USD', FALSE, 'CHECK',
        NULL::text, NULL::text, 'CP-C002-002', 'US', NULL::text, FALSE,
        'Casa Brisa Kitchen Inc.', 'US', 'Capitol City Meat and Seafood',
        'Supplier payment', 'INV-C002-LIVE-01', '3991', FALSE, 'Supplier payment'
    FROM origin
    UNION ALL
    SELECT
        'TXN-LIVE-C002-05', 'ACC-C002-01', 'C002', origin.base_ts + interval '5 minutes',
        'wire_out', 'OUTGOING', 3800.00, 'USD', FALSE, 'WIRE',
        NULL::text, NULL::text, 'CP-C002-002', 'US', NULL::text, FALSE,
        'Casa Brisa Kitchen Inc.', 'US', 'Capitol City Meat and Seafood',
        'Supplier payment', NULL::text, NULL::text, FALSE, 'Wire transfer'
    FROM origin
    UNION ALL
    SELECT
        'TXN-LIVE-C002-06', 'ACC-C002-01', 'C002', origin.base_ts + interval '6 minutes',
        'check', 'OUTGOING', 2900.00, 'USD', FALSE, 'CHECK',
        NULL::text, NULL::text, 'CP-C002-001', 'US', NULL::text, FALSE,
        'Casa Brisa Kitchen Inc.', 'US', 'Delta Fresh Produce Co.',
        'Supplier payment', 'INV-C002-LIVE-02', '3992', FALSE, 'Supplier payment'
    FROM origin
) live
ON CONFLICT (transaction_id) DO NOTHING;
