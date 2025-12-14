CREATE OR REPLACE FUNCTION increment_board_counter(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO user_analysis (user_id, boards_since_last_compression, compressed_data)
  VALUES (p_user_id, 1, '')
  ON CONFLICT (user_id)
  DO UPDATE SET boards_since_last_compression = user_analysis.boards_since_last_compression + 1;
END;
$$;
