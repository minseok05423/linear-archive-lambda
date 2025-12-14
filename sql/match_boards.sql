CREATE OR REPLACE FUNCTION match_boards(
  query_embedding VECTOR(1024),
  query_user_id uuid,
  match_threshold FLOAT DEFAULT 0.5,
  match_count INT DEFAULT 10
)
RETURNS TABLE (
  board_id uuid,
  user_id uuid,
  description text,
  date date,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    board.board_id,
    board.user_id,
    board.description,
    board.date,
    1 - (board.vector <=> query_embedding) AS similarity
  FROM board
  WHERE
    board.vector IS NOT NULL
    AND board.user_id = query_user_id
    AND board.vector::text != array_fill(0, ARRAY[1024])::vector(1024)::text
  ORDER BY board.vector <=> query_embedding
  LIMIT match_count;
END;
$$;
