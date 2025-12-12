import json
import os
import requests
import logging
import traceback

# Configure logging for CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    # CORS headers
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }

    # Detect HTTP method
    method = event.get('httpMethod')
    if not method and 'requestContext' in event and 'http' in event['requestContext']:
        method = event['requestContext']['http']['method']

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers, 'body': ''}

    try:
        logger.info("=== Data Compression Lambda Started ===")
        logger.info(f"Event: {json.dumps(event)}")
        
        # 1. Environment Variables
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

        if not all([SUPABASE_URL, SUPABASE_KEY, DEEPSEEK_API_KEY]):
            missing = []
            if not SUPABASE_URL: missing.append("SUPABASE_URL")
            if not SUPABASE_KEY: missing.append("SUPABASE_KEY")
            if not DEEPSEEK_API_KEY: missing.append("DEEPSEEK_API_KEY")
            logger.error(f"Missing environment variables: {missing}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing environment variables', 'missing': missing})
            }

        # 2. Parse Input - API Gateway sends body as JSON string
        body_data = {}
        if "body" in event and isinstance(event["body"], str):
            body_data = json.loads(event["body"])
        elif isinstance(event, dict) and "body" not in event:
            # Direct invocation or Function URL (body is the event itself)
            body_data = event
        
        logger.info(f"Parsed body: {json.dumps(body_data, default=str)}")
        
        new_boards = body_data.get("boards")

        if not new_boards:
            logger.error(f"Missing required field - boards: {bool(new_boards)}")
            logger.error(f"Body data keys: {list(body_data.keys())}")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing boards data'})
            }

        # 3. Get user_id from API Gateway authorizer context
        # API Gateway Authorizer validates the Supabase token and passes user info
        user_id = None
        access_token = None
        
        # Try to extract access token from Authorization header
        if 'headers' in event:
            auth_header = event['headers'].get('Authorization') or event['headers'].get('authorization')
            if auth_header and auth_header.startswith('Bearer '):
                access_token = auth_header.replace('Bearer ', '')
                logger.info("Access token extracted from Authorization header")
        
        # Fallback to body
        if not access_token:
            access_token = body_data.get("access_token")

        if not access_token:
             logger.warning("No access_token found. Database operations might fail if RLS is active and Service Key is not used.")

        # Try to get user_id from authorizer context (API Gateway)
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            authorizer = event['requestContext']['authorizer']
            user_id = (
                authorizer.get('claims', {}).get('sub') or
                authorizer.get('principalId') or
                authorizer.get('user_id')
            )
            if user_id:
                logger.info(f"User ID from API Gateway authorizer: {user_id}")
        
        # Fallback: extract from body if provided (for testing/backward compatibility)
        if not user_id:
            user_id = body_data.get("user_id")
            if user_id:
                logger.info(f"User ID from request body: {user_id}")
        
        if not user_id:
            logger.error("No user_id found in authorizer context or request body")
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Unauthorized - no user_id found'})
            }

        logger.info(f"Processing compression for user: {user_id}")


        # 4. Fetch Previous Compressed Data via REST
        # Endpoint: GET /rest/v1/user_analysis?user_id=eq.{user_id}&select=compressed_data
        logger.info("Fetching previous summary via REST...")
        db_url = f"{SUPABASE_URL}/rest/v1/user_analysis"
        
        # ALWAYS use Service Key (SUPABASE_KEY) for DB calls to bypass RLS
        # Ensure SUPABASE_KEY env var is the 'service_role' key.
        # Strip whitespace just in case of copy-paste errors
        service_key = SUPABASE_KEY.strip() if SUPABASE_KEY else ""
        auth_token = service_key
        
        # Debug: Log the key prefix to verify provided key
        key_prefix = auth_token[:15] + "..." if len(auth_token) > 15 else "SHORT"
        logger.info(f"Using Auth Token Prefix: {key_prefix}")
        
        db_headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {auth_token}"
        }

        params = {
            "user_id": f"eq.{user_id}",
            "select": "compressed_data"
        }
        
        db_res = requests.get(db_url, headers=db_headers, params=params, timeout=10)
        
        prev_summary = ""
        
        if db_res.ok:
            rows = db_res.json()
            if rows and len(rows) > 0:
                prev_summary = rows[0].get("compressed_data", "")
                logger.info(f"Found previous summary (length: {len(prev_summary)})")
            else:
                logger.info("No previous summary found.")
        else:
            logger.warning(f"DB Fetch Error: {db_res.status_code} {db_res.text}")
            # Continue with empty summary

        # 5. Call DeepSeek
        logger.info("Calling DeepSeek LLM...")
        system_prompt = """당신은 꼼꼼한 전기 작가이자 데이터 기록관입니다.
당신의 임무는 사용자의 활동 보드를 기반으로 "압축된 인생 기록"을 유지하는 것입니다.

제공되는 데이터:
1. 현재의 압축 기록 (과거의 요약).
2. 새로운 활동 보드 묶음 (최근 사건들).

목표:
새로운 사건들을 기존 서사에 자연스럽게 통합하여 업데이트된 압축 기록을 작성하세요.

규칙:
- **반드시 한국어로 작성하세요.**
- 기존 기록의 중요한 장기적 사실을 보존하세요.
- 새로운 보드의 세부 정보를 서사에 요약하여 추가하세요.
- 시간 순서에 따른 흐름을 유지하세요.
- 전문적이지만 개인적인 어조를 유지하세요.
- 주요 이정표나 성과를 누락하지 마세요.
"""
        user_content = f"""
=== CURRENT COMPRESSED HISTORY ===
{prev_summary if prev_summary else "(Empty - This is the start of the archive)"}

=== NEW BATCH OF BOARDS ===
{json.dumps(new_boards, indent=2)}

=== INSTRUCTION ===
업데이트된 압축 기록을 지금 생성하세요. 오직 기록의 텍스트만 반환하세요.
"""
        llm_payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "model": "deepseek-chat",
            "max_tokens": 4000,
            "temperature": 0.5
        }
        
        llm_headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }

        llm_res = requests.post("https://api.deepseek.com/chat/completions", headers=llm_headers, json=llm_payload, timeout=60)
        
        if not llm_res.ok:
            logger.error(f"DeepSeek API Error: {llm_res.status_code} {llm_res.text}")
            raise Exception(f"DeepSeek API Error: {llm_res.status_code} - {llm_res.text}")

        llm_data = llm_res.json()
        new_summary = llm_data['choices'][0]['message']['content']
        logger.info(f"Compression successful. New summary length: {len(new_summary)}")


        # 6. Update/Insert into Supabase via REST
        logger.info("Updating user_analysis table via REST...")
        
        update_payload = {
            "compressed_data": new_summary,
            "boards_since_last_compression": 15  # Reset to 15 (keep latest 15 boards uncompressed)
        }
        
        update_headers = db_headers.copy()
        update_headers["Content-Type"] = "application/json"
        
        # Use PATCH to update existing row
        update_url = f"{db_url}?user_id=eq.{user_id}"
        update_res = requests.patch(update_url, headers=update_headers, json=update_payload, timeout=10)
        
        if not update_res.ok:
             logger.error(f"Update failed: {update_res.status_code} {update_res.text}")
             raise Exception(f"Database update failed: {update_res.status_code} - {update_res.text}")

        logger.info("Database updated successfully.")

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Compression successful',
                'new_summary_length': len(new_summary),
                'preview': new_summary[:100] + "..."
            })
        }

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"ERROR: {str(e)}")
        logger.error(f"Stack trace: {error_trace}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'error': str(e),
                'type': type(e).__name__,
                'auth_prefix': key_prefix if 'key_prefix' in locals() else "Unknown",
                'trace': error_trace.split('\n')[-3:-1]  # Last 2 lines of trace for context
            })
        }
