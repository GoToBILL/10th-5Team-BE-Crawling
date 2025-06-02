import os
import importlib
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda 핸들러 - SQS 메시지 처리"""
    site_name = os.environ.get("SITE_NAME")
    logger.info(f"Target site_name: {site_name}")
    
    if not site_name:
        return {
            "statusCode": 400,
            "message": "SITE_NAME 환경변수가 설정되지 않았습니다."
        }

    try:
        # SQS Records에서 메시지 처리
        records = event.get('Records', [])
        
        if not records:
            logger.warning("SQS 메시지가 없습니다.")
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'No SQS records found'})
            }
        
        success_count, error_count = process_sqs_records(site_name, records)
        
        # 결과 반환
        result = {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'처리 완료 - 성공: {success_count}, 실패: {error_count}',
                'success_count': success_count,
                'error_count': error_count
            })
        }
        
        logger.info(f"🎯 배치 처리 완료 - 성공: {success_count}, 실패: {error_count}")
        return result
        
    except Exception as e:
        logger.error(f"핸들러 실행 중 오류: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def process_sqs_records(site_name, records):
    """SQS 레코드들을 처리"""
    # Selenium 실행 옵션 설정 (Lambda 환경용)
    chrome_options = Options()
    chrome_options.binary_location = "/opt/chrome/chrome"
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
    )

    # Chrome 드라이버 설정
    service = Service(executable_path="/opt/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    success_count = 0
    error_count = 0

    try:
        # 동적 import로 사이트별 세부 크롤링 모듈 로드
        module = importlib.import_module(f"{site_name}.{site_name}_detail")
        
        for record in records:
            try:
                # SQS 메시지 파싱
                message_body = record['body']
                campaign_data = json.loads(message_body)
                
                logger.info(f"📨 SQS 메시지 수신: {campaign_data.get('title', 'Unknown')}")
                
                # 사이트별 세부 크롤링 실행
                if module.process_campaign(driver, campaign_data):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"레코드 처리 중 오류: {e}")
                error_count += 1
                
    except ModuleNotFoundError:
        logger.error(f"'{site_name}'에 해당하는 세부 크롤링 모듈을 찾을 수 없습니다.")
        error_count = len(records)
    except AttributeError:
        logger.error(f"'{site_name}' 모듈에 'process_campaign(driver, data)' 함수가 정의되어 있지 않습니다.")
        error_count = len(records)
    finally:
        driver.quit()

    return success_count, error_count