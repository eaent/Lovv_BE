-- Lovv Data Stack RDS reference queries
-- Source: docs/PRD/db_build_prd.md section 3.4
-- Replace :param placeholders with bound parameters in application code.

-- A. Social login identity lookup.
SELECT u.id, u.email, u.display_name, u.avatar_url
FROM social_accounts s
JOIN users u ON u.id = s.user_id
WHERE s.provider = :provider AND s.provider_user_id = :provider_user_id;

-- B. Saved itinerary list for my page.
SELECT id, title, summary, duration_label, intensity_label, saved_at
FROM itineraries
WHERE user_id = :user_id
ORDER BY saved_at DESC
LIMIT :limit OFFSET :offset;

-- C. Itinerary detail with ordered items.
SELECT i.id AS itinerary_id, i.title, i.summary, i.preference_snapshot,
       it.sort_order, it.time_slot, it.place_name, it.move_hint, it.recommendation_reason
FROM itineraries i
JOIN itinerary_items it ON it.itinerary_id = i.id
WHERE i.id = :itinerary_id AND i.user_id = :user_id
ORDER BY it.sort_order ASC;

-- D. Register itinerary reaction.
INSERT INTO plan_reactions (id, user_id, itinerary_id, reaction_type, created_at)
VALUES (:id, :user_id, :itinerary_id, :reaction_type, :now);

-- E. Aggregate reactions by itinerary.
SELECT reaction_type, COUNT(*) AS cnt
FROM plan_reactions
WHERE itinerary_id = :itinerary_id
GROUP BY reaction_type;

-- F. Delete saved itinerary. Child items and reactions are removed by FK cascade.
DELETE FROM itineraries WHERE id = :itinerary_id AND user_id = :user_id;
