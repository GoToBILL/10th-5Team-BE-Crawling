import os
import importlib
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event=None, context=None):
    site_name = os.environ.get("SITE_NAME")
    page_source = os.environ.get("PAGE_SOURCE")
    
    logger.info(f"Target site_name: {site_name}, page_source: {page_source}")
    
    if not site_name:
        return {
            "statusCode": 400,
            "message": "SITE_NAME 환경변수가 설정되지 않았습니다."
        }
    
    if not page_source:
        return {
            "statusCode": 400,
            "message": "PAGE_SOURCE 환경변수가 설정되지 않았습니다."
        }

    try:
        # RDS 처리 추가
        if page_source == "rds":
            records = event.get('Records', [])
            
            if not records:
                logger.warning("SQS 메시지가 없습니다.")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'No SQS records found'})
                }
            
            success_count, error_count = process_rds_records(records)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'RDS 처리 완료 - 성공: {success_count}, 실패: {error_count}',
                    'success_count': success_count,
                    'error_count': error_count
                })
            }
        
        
        # detail 모드인 경우 SQS Records 처리
        if page_source == "detail":
            records = event.get('Records', [])
            
            if not records:
                logger.warning("SQS 메시지가 없습니다.")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'No SQS records found'})
                }
            
            success_count, error_count = crawler_target(site_name, page_source, records)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'처리 완료 - 성공: {success_count}, 실패: {error_count}',
                    'success_count': success_count,
                    'error_count': error_count
                })
            }
        
        # crawler 모드인 경우 일반 크롤링
        else:
            suc_cnt, err_cnt = crawler_target(site_name, page_source)
            return {
                "statusCode": 200,
                "suc_cnt": suc_cnt,
                "err_cnt": err_cnt
            }
            
    except Exception as e:
        logger.error(f"핸들러 실행 중 오류: {e}")
        return {
            "statusCode": 500,
            "message": f"크롤러 실행 중 오류 발생: {str(e)}"
        }


def get_chrome_driver():
    """Chrome 드라이버 설정 및 반환"""
    chrome_options = Options()
    chrome_options.binary_location = "/opt/chrome/chrome"
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("window-size=1392x1150")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"
    )

    service = Service(executable_path="/opt/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)


def process_rds_records(records):
    """RDS SQS Records 처리 로직"""
    try:
        # 실제 import 시도
        rds_module = importlib.import_module("campaign_repository_bj")
        
        # 나머지 로직...
        event = {'Records': records}
        result = rds_module.lambda_handler(event, None)
        
        if result.get('statusCode') == 200:
            body = json.loads(result.get('body', '{}'))
            return body.get('success_count', 0), body.get('error_count', 0)
        else:
            logger.error(f"RDS 처리 실패: {result}")
            return 0, len(records)
        
    except ModuleNotFoundError as e:
        logger.error(f"RDS 처리 모듈을 찾을 수 없습니다: {e}")
        return 0, len(records)
    except Exception as e:
        logger.error(f"RDS 처리 중 오류: {e}")
        return 0, len(records)

def process_sqs_records(module, driver, records):
    """SQS Records 처리 로직"""
    success_count = 0
    error_count = 0
    
    for record in records:
        try:
            # SQS 메시지 파싱
            message_body = record['body']
            campaign_data = json.loads(message_body)
            
            logger.info(f"SQS 메시지 수신: {campaign_data.get('title', 'Unknown')}")
            
            # 사이트별 세부 크롤링 실행
            if module.run(driver, campaign_data):
                success_count += 1
            else:
                error_count += 1
                
        except Exception as e:
            logger.error(f"레코드 처리 중 오류: {e}")
            error_count += 1
    
    return success_count, error_count


def crawler_target(site_name, page_source, records=None):
    """통합 크롤링 처리"""
    driver = get_chrome_driver()

    try:
        # 동적 import로 사이트별 모듈 로드
        module = importlib.import_module(f"{site_name}.{site_name}_{page_source}")
        if page_source == "detail":
            # detail 모드에서는 SQS records 처리
            if records:
                success_count, error_count = process_sqs_records(module, driver, records)
                return success_count, error_count
            else:
                logger.error("detail 모드에서는 SQS records가 필요합니다.")
                return 0, 1
        else:
            suc_cnt, err_cnt = module.run(driver)
            return suc_cnt, err_cnt
            
    except ModuleNotFoundError:
        raise Exception(f"'{site_name}'에 해당하는 모듈을 찾을 수 없습니다.")
    except AttributeError as e:
        if page_source == "detail":
            raise Exception(f"'{site_name}' 모듈에 'process_campaign(driver, data)' 함수가 정의되어 있지 않습니다.")
        else:
            raise Exception(f"'{site_name}' 모듈에 'run(driver)' 함수가 정의되어 있지 않습니다.")
    finally:
        driver.quit()