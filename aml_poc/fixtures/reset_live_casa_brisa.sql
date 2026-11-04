-- Rewind the live Casa Brisa episode only. Does not touch episodes 1-2 or Sunnyvale.
-- After this, the running app drops the live case on the next watch cycle.

DELETE FROM transactions WHERE transaction_id LIKE 'TXN-LIVE-%';
