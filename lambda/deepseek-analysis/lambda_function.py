import json
import os
import requests

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
        print("=== Deepseek Analysis Lambda started ===")
        print(f"Received event: {json.dumps(event)}")

        # Get environment variable
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

        if not DEEPSEEK_API_KEY:
            print("ERROR: Missing DEEPSEEK_API_KEY")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing DEEPSEEK_API_KEY'})
            }

        # Parse boards data from request body
        boards = event.get("boards", [])

        if not boards:
            print("ERROR: No boards data provided")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No boards data provided'})
            }

        print(f"Received {len(boards)} boards for analysis")

        # Prepare Deepseek API request
        payload = {
            "messages": [
                {
                    "content": """데이터 분석가 겸 상담사로서 활동 패턴(빈도/주제/시간)을 분석해 친근하게 인사이트를 주세요. 과장이나 유저 지칭 없이 구체적 수치/날짜에 기반한 아래 JSON을 한국어로 반환하세요.
{
  "fact1": "주요 패턴(수치/날짜)",
  "fact2": "추가 특징(수치/날짜)",
  "analysis": "친근한 분석(2-3문장)"
}""",
                    "role": "system"
                },
                {
                    "content": f"""다음 활동 데이터(태그, 시간 등)를 분석해 시각, 관심사, 빈도, 특이사항 위주로 인사이트를 주세요. 오직 유효한 JSON만 한국어로 반환하세요.
{json.dumps(boards, indent=2)}""",
                    "role": "user"
                }
            ],
            "model": "deepseek-chat",
            "response_format": {
                "type": "json_object"
            },
            "thinking": {
                "type": "disabled"
            },
            "max_tokens": 1024,
            "temperature": 1,
            "top_p": 1
        }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }

        print("Calling Deepseek API for analysis...")
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"Deepseek API responded with status: {response.status_code}")

        if not response.ok:
            error_text = response.text
            print(f"ERROR: Deepseek API error: {error_text}")
            raise Exception(f"Deepseek API error {response.status_code}: {error_text}")

        completion = response.json()
        print(f"Deepseek response: {json.dumps(completion)}")

        # Extract the analysis from the response
        analysis_content = completion['choices'][0]['message']['content']
        print(f"Analysis content (raw): {analysis_content}")

        # Parse the JSON string to an object
        try:
            analysis_json = json.loads(analysis_content)
            print(f"Analysis content (parsed): {json.dumps(analysis_json)}")
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse analysis JSON: {str(e)}")
            analysis_json = {
                "fact1": "Unable to parse analysis",
                "fact2": "Unable to parse analysis",
                "analysis": analysis_content
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'analysis': analysis_json,
                'raw_response': completion
            })
        }

    except Exception as error:
        print(f"Analysis error: {str(error)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'error': f'Analysis failed: {str(error)}'
            })
        }
