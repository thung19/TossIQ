-- Hazard classification and the acknowledgement trail behind the hazards
-- page.
--
-- WASTE_EVENTS already carried HAZARD_FLAG and HAZARD_REASON: the advanced
-- vision model sets them when it sees a battery compartment, a warning
-- symbol or sharps. What it could not do was say what KIND of hazard, how
-- urgent it is, or whether anybody has dealt with it -- so a flagged battery
-- and a flagged syringe were the same row to every query in the system.
--
-- HAZARD_STATUS predates this file and defaults to 'open' on every row,
-- including the 1,090 that are not hazards at all, so it carries no
-- information on its own. Every query here is scoped to HAZARD_FLAG = 1,
-- which is the column that actually means something.
--
-- Acknowledgement is two columns rather than a table. A hazard is
-- acknowledged once, by one person, and the history of who looked at it
-- before they did is not something anybody has asked to keep; a join table
-- for that would be structure without a question behind it.

ALTER TABLE waste_events ADD (
    hazard_class      VARCHAR2(40),
    hazard_severity   VARCHAR2(20),
    acknowledged_at   TIMESTAMP,
    acknowledged_by   VARCHAR2(120),
    hazard_note       VARCHAR2(600)
)
/

-- The hazards page opens on "what is outstanding, worst first", which is a
-- scan of flagged rows ordered by time. Without this it is a full table
-- scan of every disposal ever logged to find the handful that are hazards.
CREATE INDEX idx_waste_events_hazard ON waste_events (hazard_flag, created_at DESC)
/
