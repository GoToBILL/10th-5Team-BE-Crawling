from constants.campaign_type import CAMPAIGN_TYPE_MAP
import pymysql
import os
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_connection():
    return pymysql.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        db=os.environ['DB_NAME'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def get_platform_values(platforms):
    """플랫폼 데이터를 DB 컬럼 순서에 맞게 변환"""
    platform_fields = ['blog', 'clip', 'insta', 'reels', 'youtube', 'shorts', 'tiktok', 'etc']
    platforms_set = set(platforms or [])
    return [int(p in platforms_set) for p in platform_fields]

def insert_main_campaign(cursor, data):
    """메인 페이지에서 넘어온 데이터 처리 (마감 임박) - 신청자/모집 수만 업데이트"""
    title = data.get('title', 'Unknown')
    source_site = data.get('source_site', 'unknown')
    
    logger.info(f"메인 캠페인 처리 ({source_site}): {title}")
    
    platform_fields = ['blog', 'clip', 'insta', 'reels', 'youtube', 'shorts', 'tiktok', 'etc']
    platform_values = get_platform_values(data.get('platforms'))
    
    sql = f"""
        INSERT INTO campaigns (
            title, detail_url,benefit, source_site,
            applicant_count, recruit_count, competition_rate, campaign_type,
            {', '.join(platform_fields)}
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {', '.join(['%s'] * len(platform_fields))})
        ON DUPLICATE KEY UPDATE
            detail_url = VALUES(detail_url),
            applicant_count = VALUES(applicant_count),
            recruit_count = VALUES(recruit_count),
            competition_rate = VALUES(competition_rate),
            updated_at = CURRENT_TIMESTAMP
    """
    
    values = [
        data.get('title'),
        data.get('detail_url'),
        data.get('benefit'),
        data.get('source_site'),
        data.get('applicant_count'),
        data.get('recruit_count'),
        data.get('competition_rate'),
        CAMPAIGN_TYPE_MAP.get(data.get('campaign_type')),
        *platform_values
    ]
    
    cursor.execute(sql, values)
    logger.info(f"메인 캠페인 DB 처리 완료 ({source_site}): {title}")

def insert_detail_campaign(cursor, data):
    """상세 페이지에서 넘어온 데이터 처리 - 전체 정보 삽입/업데이트"""
    title = data.get('title', 'Unknown')
    source_site = data.get('source_site', 'unknown')
    
    logger.info(f"상세 캠페인 처리 ({source_site}): {title}")
    
    platform_fields = ['blog', 'clip', 'insta', 'reels', 'youtube', 'shorts', 'tiktok', 'etc']
    platform_values = get_platform_values(data.get('platforms'))
    
    # 모든 가능한 필드를 포함한 INSERT문
    sql = f"""
        INSERT INTO campaigns (
            title, detail_url, benefit,
            apply_start, apply_end, reviewer_announcement,
            content_submission_start, content_submission_end, result_announcement,
            applicant_count, recruit_count, source_site,
            is_active, campaign_type, address, competition_rate,
            {', '.join(platform_fields)}
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {', '.join(['%s'] * len(platform_fields))})
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            detail_url = VALUES(detail_url),
            benefit = VALUES(benefit),
            apply_start = VALUES(apply_start),
            apply_end = VALUES(apply_end),
            reviewer_announcement = VALUES(reviewer_announcement),
            content_submission_start = VALUES(content_submission_start),
            content_submission_end = VALUES(content_submission_end),
            result_announcement = VALUES(result_announcement),
            applicant_count = VALUES(applicant_count),
            recruit_count = VALUES(recruit_count),
            source_site = VALUES(source_site),
            is_active = VALUES(is_active),
            campaign_type = VALUES(campaign_type),
            address = VALUES(address),
            competition_rate = VALUES(competition_rate),
            {', '.join([f"{p} = VALUES({p})" for p in platform_fields])},
            updated_at = CURRENT_TIMESTAMP
    """
    
    values = [
        data.get('title'),
        data.get('detail_url'),
        data.get('benefit'),
        data.get('apply_startdate'),
        data.get('apply_enddate'),
        data.get('reviewer_announcement'),
        data.get('content_submission_start'),
        data.get('content_submission_end'),
        data.get('result_announcement'),
        data.get('applicant_count'),
        data.get('recruit_count'),
        data.get('source_site'),
        1,  # is_active
        CAMPAIGN_TYPE_MAP.get(data.get('campaign_type')),
        data.get('address'),
        data.get('competition_rate'),
        *platform_values
    ]
    
    cursor.execute(sql, values)
    logger.info(f"상세 캠페인 DB 처리 완료 ({source_site}): {title}")


def insert_campaign(data):
    """캠페인 데이터 DB 삽입 메인 함수"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            page_flag = data.get('page_flag')
            source_site = data.get('source_site', 'unknown')
            
            if page_flag == 'main':
                # 메인에서 온 데이터 (마감 임박) - 신청자/모집 수만 업데이트
                insert_main_campaign(cursor, data)
                
            elif page_flag == 'detail':
                # 디테일에서 온 데이터 - 전체 정보 삽입/업데이트
                insert_detail_campaign(cursor, data)
                
            else:
                logger.warning(f"Unknown page_flag: {page_flag}, source: {source_site}")
                # page_flag가 없거나 알 수 없는 경우 detail로 처리
                insert_detail_campaign(cursor, data)
                
        conn.commit()
        logger.info(f"DB 커밋 완료 ({source_site}): {data.get('title')}")
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"DB Error ({source_site}): {e}")
        logger.error(f"Error Data: {data}")
        return False
        
    finally:
        conn.close()

def validate_campaign_data(data):
    """캠페인 데이터 유효성 검사"""
    required_fields = ['title', 'detail_url', 'source_site']
    
    for field in required_fields:
        if not data.get(field):
            logger.error(f"필수 필드 누락: {field}")
            return False
    
    return True

def run(sqs_message_body):
    """SQS 메시지를 받아서 DB에 처리하는 메인 함수 (범용)"""
    try:
        # SQS 메시지 파싱
        if isinstance(sqs_message_body, str):
            data = json.loads(sqs_message_body)
        else:
            data = sqs_message_body
            
        source_site = data.get('source_site', 'unknown')
        title = data.get('title', 'Unknown')
        
        logger.info(f"RDS 처리 시작 ({source_site}): {title}")
        
        # 데이터 유효성 검사
        if not validate_campaign_data(data):
            logger.error(f"데이터 유효성 검사 실패 ({source_site}): {title}")
            return False
        
        # DB 삽입
        success = insert_campaign(data)
        
        if success:
            logger.info(f"RDS 처리 완료 ({source_site}): {title}")
        else:
            logger.error(f"RDS 처리 실패 ({source_site}): {title}")
            
        return success
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}")
        logger.error(f"원본 메시지: {sqs_message_body}")
        return False
        
    except Exception as e:
        logger.error(f"RDS 처리 중 오류: {e}")
        logger.error(f"메시지 내용: {sqs_message_body}")
        return False


def lambda_handler(event, context):
    """Lambda 핸들러 - 여러 사이트 공통 사용"""
    success_count = 0
    error_count = 0
    
    for record in event['Records']:
        try:
            message_body = record['body']
            
            if run(message_body):
                success_count += 1
            else:
                error_count += 1
                
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {e}")
            error_count += 1
    
    logger.info(f"배치 처리 완료 - 성공: {success_count}개, 실패: {error_count}개")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'success_count': success_count,
            'error_count': error_count
        })
    }