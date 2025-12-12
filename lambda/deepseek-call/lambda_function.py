import json
import os
import requests
import voyageai
from supabase import create_client, Client

def lambda_handler(event, context):
    # CORS headers for all responses
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }

    # Handle OPTIONS preflight request
    if event.get('httpMethod') == 'OPTIONS' or event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        print("Handling OPTIONS preflight request")
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }

    try:
        print("===Calling Deepseek API start===")
        print(f"Received event: {json.dumps(event)}")

        # env
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        voyage_key = os.environ.get("VOYAGE_KEY")
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")

        print(f"Environment check - SUPABASE_URL: {'SET' if supabase_url else 'MISSING'}")
        print(f"Environment check - SUPABASE_KEY: {'SET' if supabase_key else 'MISSING'}")
        print(f"Environment check - VOYAGE_KEY: {'SET' if voyage_key else 'MISSING'}")
        print(f"Environment check - DEEPSEEK_API_KEY: {'SET' if deepseek_key else 'MISSING'}")

        if not all([supabase_url, supabase_key, voyage_key, deepseek_key]):
            print("ERROR: Missing environment variables")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing environment variables'})
            }

        # Initialize clients after parsing data
        try:
            print("Initializing VoyageAI client...")
            vo = voyageai.Client(api_key=voyage_key, timeout=30)
            print("VoyageAI client initialized successfully")

            print("Initializing Supabase client...")
            # Use the user's token for authentication to respect RLS policies
            access_token = event.get('access_token')
            refresh_token = event.get('refresh_token')
            supabase: Client = create_client(supabase_url, supabase_key)
            supabase.auth.set_session(access_token, refresh_token)
            print("Supabase client initialized successfully")

        except Exception as e:
            print(f"ERROR: Client initialization failed: {str(e)}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': f'Client initialization failed: {str(e)}'})
            }

        # turn the query into an embedding
        print("Generating embedding with VoyageAI...")
        user_query = event.get("query", "")
        print(f"User query received: '{user_query}'")

        try:
            result = vo.embed(texts=[user_query], input_type="query", model="voyage-3")
            combined_embedding = result.embeddings[0]

            print(f"Embedding generated successfully, dimension: {len(combined_embedding)}")
        except Exception as e:
            print(f"ERROR: Embedding generation failed: {str(e)}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': f'Embedding failed: {str(e)}'})
            }
        
        # do a similarity search in supabase
        try:
            print("Performing similarity search in Supabase...")
            similarity_response = supabase.rpc("match_boards", {
                "query_embedding": combined_embedding,
                "query_user_id": event.get("user_id"),
                "match_threshold": 0.0,  # No threshold for debugging
                "match_count": 20
            }).execute()

            relevant_boards = similarity_response.data
            print(f"Found {len(relevant_boards)} relevant boards")

            # Format boards as JSON object
            boards_dict = {
                f"board{i+1}": {
                    "date": board['date'],
                    "description": board['description'],
                    "tags": board['tags'] if board['tags'] else []
                }
                for i, board in enumerate(relevant_boards)
            }
            print(f"Boards JSON: {json.dumps(boards_dict)}")

            # Format board context for LLM
            board_context = "\n".join([
                f"Board {i+1}:\n- Description: {board['description']}\n- Date: {board['date']}\n- Tags: {', '.join(board['tags']) if board['tags'] else 'None'}"
                for i, board in enumerate(relevant_boards)
            ])
            print(f"Board context prepared: {board_context[:200]}...")

            # If mode is search_only, return boards directly
            if event.get("task") == "search_only":
                print("Returning search results without LLM generation")
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'boards': relevant_boards,
                        'count': len(relevant_boards)
                    })
                }

        except Exception as e:
            print(f"ERROR: Similarity search failed: {str(e)}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': f'similarity search failed: {str(e)}'})
            }

        # Prepare Deepseek request with board context
        deepseek_messages = user_query
        if board_context:
            # Add context to the system message or user message
            context_message = {
                "role": "system",
                "content": f"You are a helpful assistant. Here are the user's relevant boards:\n\n{board_context}\n\nUse this information to answer the user's questions about their boards."
            }
            if isinstance(deepseek_messages, list):
                deepseek_messages.insert(0, context_message)
            else:
                 deepseek_messages = [{"role": "user", "content": str(user_query)}]
                 deepseek_messages.insert(0, context_message)

        deepseek_request = {
            "model": event.get("model", "deepseek-chat"),
            "messages": deepseek_messages,
            "temperature": event.get("temperature", 0.7),
            "max_tokens": event.get("max_tokens", 1000)
        }

        # Call Deepseek API
        print("Calling Deepseek API with board context...")
        deepseek_response = requests.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {deepseek_key}',
                'Content-Type': 'application/json'
            },
            json=deepseek_request,
            timeout=20  # 20 second timeout
        )

        print(f"Deepseek responded with status: {deepseek_response.status_code}")

        if not deepseek_response.ok:
            error_text = deepseek_response.text
            raise Exception(f"Deepseek API error {deepseek_response.status_code}: {error_text}")

        completion = deepseek_response.json()
        print(f"Response: {completion['choices'][0]['message']['content']}")

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(completion)
        }

    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        return {
            'statusCode': 400,
            'headers': cors_headers,
            'body': json.dumps({
                'message': f'Invalid JSON in request body: {str(e)}'
            })
        }

    except Exception as error:
        print(f"Deepseek API error: {str(error)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'message': f'deepseek error has occurred: {str(error)}'
            })
        }
    
    