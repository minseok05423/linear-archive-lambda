import os
import json
import base64
import requests
from io import BytesIO
from PIL import Image
import voyageai
from supabase import create_client, Client

def lambda_handler(event, context):
    print("=== Lambda function started ===")
    print(f"Event: {json.dumps(event)}")

    # CORS headers for all responses
    cors_headers = {
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

    # env
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    voyage_key = os.environ.get("VOYAGE_KEY")

    print(f"Environment check - SUPABASE_URL: {'SET' if supabase_url else 'MISSING'}")
    print(f"Environment check - SUPABASE_KEY: {'SET' if supabase_key else 'MISSING'}")
    print(f"Environment check - VOYAGE_KEY: {'SET' if voyage_key else 'MISSING'}")

    if not all([supabase_url, supabase_key, voyage_key]):
        print("ERROR: Missing environment variables")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Missing environment variables'})
        }


    # Parse input
    print("Parsing request body...")

    # Check if data is directly in event
    if "user_id" in event or "description" in event:
        print("Data found directly in event object")
        data = event
    else:
        # Try to get from body
        body_raw = event.get("body")
        print(f"Raw event.get('body') type: {type(body_raw)}")
        print(f"Raw event.get('body') value: {repr(body_raw)[:200]}...")

        if body_raw is None or body_raw == "":
            print("ERROR: No body found in request")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No request body provided'})
            }
        elif isinstance(body_raw, dict):
            data = body_raw
            print("Body is already a dict")
        else:
            # Body is a string (JSON or base64)
            if event.get("isBase64Encoded"):
                print("Body is base64 encoded, decoding...")
                try:
                    body_raw = base64.b64decode(body_raw).decode("utf-8")
                except Exception as e:
                    print(f"ERROR: Base64 decode failed: {str(e)}")
                    return {
                        'statusCode': 400,
                        'headers': cors_headers,
                        'body': json.dumps({'error': 'Invalid base64 body'})
                    }
            try:
                data = json.loads(body_raw)
                print(f"Parsed data from JSON string")
            except json.JSONDecodeError as e:
                print(f"ERROR: JSON parse failed: {str(e)}")
                print(f"Failed to parse: {repr(body_raw)}")
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Invalid JSON'})
                }

    print(f"Parsed data keys: {list(data.keys())}")

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

    print("Validating required fields...")
    required_fields = ["description", "tags", "date", "board_id"]  
    for field in required_fields:
        if field not in data:
            print(f"ERROR: Missing required field: {field}")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': f'Missing required field: {field}'})
            }

    # Ensure tags is a list
    if isinstance(data.get("tags"), str):
        data["tags"] = [t.strip() for t in data["tags"].split(",") if t.strip()]

    print(f"Board ID: {data['board_id']}")
    print(f"Description: {data['description'][:50]}..." if len(data['description']) > 50 else f"Description: {data['description']}")
    print(f"Tags: {data['tags']}")
    print(f"Date: {data['date']}")

    # Download and open image (optional) 
    image_obj = None
    image_url = data.get("image")
    if image_url:
        print(f"Downloading image from: {image_url}")
        try:
            img_response = requests.get(image_url, timeout=10)
            img_response.raise_for_status()
            image_obj = Image.open(BytesIO(img_response.content))
            print(f"Image downloaded successfully, size: {image_obj.size}")
        except Exception as e:
            # Log — continue with text-only
            print(f"WARNING: Image load failed (proceeding with text-only): {str(e)}")
    else:
        print("No image URL provided, using text-only embedding")

    # Prepare text content
    text_content = f"Description: {data['description']}, Tags: {', '.join(data['tags'])}, Date: {data['date']}"
    print(f"Text content prepared: {text_content[:100]}...")

    # Generate embedding 
    print("Generating embedding with VoyageAI...")
    try:
        inputs = [[text_content, image_obj]] if image_obj is not None else [[text_content]]
        print(f"Input type: {'multimodal (text + image)' if image_obj else 'text-only'}")

        # Try multimodal first, fallback to text-only if it fails
        try:
            result = vo.multimodal_embed(inputs=inputs, model="voyage-multimodal-3")
        except Exception as multimodal_error:
            print(f"Multimodal embedding failed, trying text-only: {str(multimodal_error)}")
            if image_obj is not None:
                print("Falling back to text-only embedding (ignoring image)")
            result = vo.embed(texts=[text_content], model="voyage-3")
        combined_embedding = result.embeddings[0]

        print(f"Embedding generated successfully, dimension: {len(combined_embedding)}")
    except Exception as e:
        print(f"ERROR: Embedding generation failed: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': f'Embedding failed: {str(e)}'})
        }

    # Update Supabase using Python client 
    print(f"Updating Supabase board table for board_id: {data['board_id']}...")
    try:
        # Update the board with the embedding vector
        result = supabase.table("board").update({
            "vector": combined_embedding
        }).eq("board_id", data['board_id']).execute()

        print(f"Supabase update result: {result}")
        
        if result.data and len(result.data) > 0:
            print(f"Successfully updated {len(result.data)} row(s)")
        else:
            print(f"WARNING: No rows were updated. Board ID {data['board_id']} may not exist in database")

    except Exception as e:
        print(f"ERROR: Supabase update failed: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': f'Supabase update failed: {str(e)}'})
        }

    # Success
    print("=== Lambda function completed successfully ===")
    return {
        'statusCode': 200,
        'headers': cors_headers,
        'body': json.dumps({
            'message': 'Vectorized successfully',
            'embedding_dim': len(combined_embedding),
            'board_id': data['board_id']
        })
    }