-- SUBSTITUTE_KIND: what sort of change a substitution actually is.
--
-- The three are different recommendations with different thresholds, and
-- conflating them produced the worst card on the first version of the
-- recommendations page: "give everyone a ceramic mug" offered to a
-- grab-and-go counter, where nobody is carrying crockery back.
--
--   material        buy a different disposable. Realistic anywhere, because
--                   it changes the purchase order and nothing else.
--   reuse           run a reusable programme. Only plausible where service
--                   is dine-in and the item comes back.
--   infrastructure  remove the need to buy the item at all -- a refill
--                   station rather than a bottle. The largest wins, and the
--                   only ones with capital cost outside the catalog.
ALTER TABLE products ADD (substitute_kind VARCHAR2(20))
/
