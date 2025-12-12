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

        if not DEEPSEEK_API_KEY:
            print("ERROR: Missing DEEPSEEK_API_KEY")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing DEEPSEEK_API_KEY'})
            }

        task = event.get("task", "analysis")

        if task == "query_parser":
            print("=== Performing Query Parsing ===")
            user_query = event.get("query", "")
            current_date = event.get("current_date", "")
            
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": f"""You are a precise query parser. Your job is to extract search filters from the user's natural language query (which may be in Korean or English).
Current Date: {current_date}

Return a JSON object with these fields:
{{
  "startDate": "YYYY-MM-DD" or null,
  "endDate": "YYYY-MM-DD" or null,
  "tags": ["tag1", "tag2"] (empty array if none),
  "keywords": ["word1", "word2"] (empty array if none),
  "daysOfWeek": [0, 1, ...] (integers 0=Sun to 6=Sat, empty if none),
  "hasImage": boolean or null (true/false if explicitly requested, else null),
  "sort": "newest" | "oldest" | "random" | null,
  "limit": integer or null
}}

Rules:
1. Handle date ranges: "1월 1일부터 2월 1일까지" -> startDate: "2024-01-01", endDate: "2024-02-01".
2. Handle relative dates: "지난주", "저번주" -> calculate range. "어제" -> specific date.
3. Handle tags: "운동 태그", "#운동" -> tags: ["운동"].
4. Handle specific text: "코딩 관련 보드" -> keywords: ["코딩"].
5. Days: "월요일에 뭐했지?" -> daysOfWeek: [1]. "주말" -> [0, 6].
6. Images: "사진 보여줘" -> hasImage: true.
7. Sort/Limit: "최근 5개" -> sort: "newest", limit: 5. "랜덤 2개" -> sort: "random", limit: 2.
8. If the user asks for "summary", "analysis", "요약", "분석" without specific constraints, return null for all fields.
9. Return format must be valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": user_query
                    }
                ],
                "model": "deepseek-chat",
                "response_format": {
                    "type": "json_object"
                },
                "temperature": 0.1
            }
            
        else:
            # Existing Analysis Mode
            boards = event.get("boards", [])
    
            if not boards:
                print("ERROR: No boards data provided")
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'No boards data provided'})
                }
    
            print(f"Received {len(boards)} boards for analysis")
    
        if task == "query_parser":
             # ... (existing query parsing logic) ...
             pass
        
        else:
            # === ANALYSIS TASK (Default) ===
            print("Mode: Analysis")
            
            # Extract History
            history = event.get("history", "")
            history_context = ""
            if history:
                 history_context = f"\n\n=== 사용자의 장기 기록 (참고용) ===\n{history}\n\n(이 기록은 장기적인 성장을 이해하는 데 참고하되, 아래의 새로운 활동 보드에 집중해서 피드백을 주세요.)"

            # Extract Metrics
            metrics = event.get("metrics", [])
            metrics_context = ""
            if metrics:
                metrics_list = "\n".join([f"- {m.get('label', 'Metric')}: {m.get('value', 'N/A')}" for m in metrics])
                metrics_context = f"\n\n=== 주요 하이라이트 (랜덤 선택됨) ===\n{metrics_list}\n\n(이 수치들을 자연스럽게 이야기에 녹여내어 데이터에 기반한 칭찬을 해주세요.)"

            # Prepare Deepseek API request for Analysis
            payload = {
                "messages": [
                    {
                        "content": f"""당신은 열정적인 퍼스널 라이프 코치이자 데이터 스토리텔러입니다.
    {history_context}
    {metrics_context}
    
    Respond with a JSON object containing a SINGLE field "analysis":
    {{
      "analysis": "사용자의 최근 활동을 요약하는 따뜻하고 격려가 담긴 3-5문장의 하나의 완성된 문단 (한국어)."
    }}
    
    Guidelines:
    - **반드시 한국어로 작성하세요.**
    - 사용자에게 직접 말하듯이 ("해요체" 사용, 예: "했어요", "좋네요") 친근하게 작성하세요.
    - 위에 제공된 **주요 하이라이트(Metrics)**를 자연스럽게 이야기에 포함시키세요. 단순히 나열하지 말고, 이것이 왜 멋진지 설명하세요.
    - 활동 보드에서 발견된 패턴을 요약하세요.
    - 열정적이고 전문적인 톤을 유지하세요.
    - "Fact 1", "Fact 2" 등으로 나누지 말고, 하나의 흐르는 문단으로 작성하세요.
    
    CRITICAL:
    - Return ONLY valid JSON.
    - The "analysis" field must contain the ENTIRE message string in Korean.
    - Do not hallucinate data not present in Boards or Highlights.""",
                        "role": "system"
                    },
                    {
                        "content": f"""최근 활동 보드 데이터입니다:
    
    {json.dumps(boards, indent=2)}
    
    데이터를 분석하고 격려의 메시지를 한국어로 작성해주세요.""",
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

        print(f"Calling Deepseek API for {task}...")
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
        content = completion['choices'][0]['message']['content']
        print(f"Content (raw): {content}")

        # Parse the JSON string to an object
        try:
            parsed_json = json.loads(content)
            print(f"Content (parsed): {json.dumps(parsed_json)}")
            
            # Return appropriate key based on task
            result_key = 'filters' if task == 'query_parser' else 'analysis'
            
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    result_key: parsed_json,
                    'raw_response': completion
                })
            }
            
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse JSON: {str(e)}")
            # Fallback for analysis, error for parser
            if task == 'query_parser':
                 return {
                    'statusCode': 422,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Failed to parse extracted filters'})
                }
            
            analysis_json = {
                "analysis": content
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
