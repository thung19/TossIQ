-- Substitution and reuse data: what the recommendations engine needs to say
-- "switch to this" rather than only "you throw away a lot of that".
--
-- SUBSTITUTE_SKU is declared per product rather than inferred. The obvious
-- inference -- pair up products sharing a DETECTED_AS and prefer the one
-- with the better disposal stream -- produces nonsense: a 12 oz paper HOT
-- cup and a 20 oz PET COLD cup share the vision label "cup" and are not
-- substitutes for each other in any kitchen. Which product actually replaces
-- which is a procurement judgement, so it is written down and reviewable
-- here instead of guessed at in SQL.
--
-- EXPECTED_USES is what makes a reusable recommendation arithmetic rather
-- than a slogan. A disposable is 1. A ceramic mug rated for 500 service
-- cycles is 500, and its cost per use is its price over that figure plus
-- washing -- which is how recommendations.py computes a payback instead of
-- asserting one.

ALTER TABLE products ADD (
    substitute_sku   VARCHAR2(100),
    substitute_note  VARCHAR2(400),
    expected_uses    NUMBER(8) DEFAULT 1
)
/

CREATE INDEX idx_products_substitute ON products (substitute_sku)
/
