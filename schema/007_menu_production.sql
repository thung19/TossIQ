-- Kitchen production volume, so food waste can be expressed as a RATE.
--
-- Counting uneaten servings tells you a dish is being thrown away. It does
-- not tell you whether that is a problem: forty wraps in the bin is awful
-- if you made sixty and unremarkable if you made nine hundred. The number
-- that supports "make fewer of these" is the share that comes back, and
-- that needs the denominator.
--
-- SERVINGS_PER_WEEK is what the kitchen produces, which a dining operation
-- already knows and a waste system cannot observe. It is therefore an
-- INPUT, not a measurement, and the recommendation that uses it says so.
-- Only prepared dishes carry it; a paper cup has no production volume in
-- any meaningful sense.

ALTER TABLE products ADD (
    servings_per_week  NUMBER(8),
    menu_station       VARCHAR2(80)
)
/

CREATE INDEX idx_products_servings ON products (servings_per_week)
/
