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
                    "content": """당신은 활동 보드를 분석하는 데이터 분석가입니다. 사용자의 활동 패턴을 객관적으로 분석하고 통찰력 있는 인사이트를 제공하세요.

다음 형식의 JSON 객체로 응답하세요:
{
  "fact1": "활동 데이터에서 발견된 주요 패턴 또는 트렌드 (구체적인 숫자와 날짜 포함)",
  "fact2": "또 다른 의미 있는 패턴이나 특징 (구체적인 숫자와 날짜 포함)",
  "analysis": "전체 활동에 대한 객관적이고 통찰력 있는 분석 (2-3문장)"
}

가이드라인:
- 데이터 기반의 객관적인 분석을 제공하세요
- 구체적인 숫자, 날짜, 태그를 활용하여 패턴을 설명하세요
- 활동의 빈도, 주제, 시간적 분포 등을 분석하세요
- 과장되거나 감정적인 표현을 피하고 중립적인 톤을 유지하세요
- 실제 데이터에 근거한 인사이트만 제공하세요
- 모든 응답은 한국어로 작성하세요""",
                    "role": "system"
                },
                {
                    "content": f"""다음 활동 보드 데이터를 분석하여 의미 있는 패턴과 인사이트를 제공하세요:

{json.dumps(boards, indent=2)}

분석 초점:
- 활동의 시간적 패턴 (언제 가장 활발한가)
- 주요 관심사나 작업 영역 (태그, 설명 기반)
- 활동 빈도와 일관성
- 특이사항이나 변화 추이

객관적이고 데이터 기반의 분석을 제공하세요.
오직 유효한 JSON만 반환하고, 마크다운이나 추가 텍스트는 포함하지 마세요.
모든 응답은 한국어로 작성하세요.""",
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
