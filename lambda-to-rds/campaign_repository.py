from constants.campaign_type import CAMPAIGN_TYPE_MAP

import pymysql
import os

def get_connection():
    return pymysql.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        db=os.environ['DB_NAME'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def insert_main_campaign(cursor, data):
    """메인 페이지에서 Lambda 크롤링 결과 넘어온 Case"""

    platform_fields = ['blog', 'clip', 'insta', 'reels', 'youtube', 'shorts', 'tiktok', 'etc']
    platforms = set(data.get('platforms', []))

    platform_values = [int(p in platforms) for p in platform_fields]

    sql = f"""
        INSERT INTO campaigns (
            title, detail_url, benefit, source_site,
            applicant_count, recruit_count, campaign_type,
            {', '.join(platform_fields)}
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, {', '.join(['%s'] * len(platform_fields))})
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            detail_url = VALUES(detail_url),
            benefit = VALUES(benefit),
            source_site = VALUES(source_site),
            applicant_count = VALUES(applicant_count),
            recruit_count = VALUES(recruit_count),
            campaign_type = VALUES(campaign_type),
            {', '.join([f"{p} = VALUES({p})" for p in platform_fields])}
    """

    values = [
        data.get('title'),
        data.get('detail_url'),
        data.get('benefit'),
        data.get('source_site'),
        data.get('applicant_count'),
        data.get('recruit_count'),
        CAMPAIGN_TYPE_MAP.get(data.get("campaign_type")),
        *platform_values
    ]

    cursor.execute(sql, values)

def insert_detail_campaign(cursor, data):
    """상세 페이지에서 Lambda 크롤링 결과 넘어온 Case"""
    # TODO: 개발 및 연동 필요
    pass

def insert_campaign(data):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            source = data.get('page_flag')
            if source == 'main':
                insert_main_campaign(cursor, data)
            elif source == 'detail':
                insert_detail_campaign(cursor, data)
            else:
                raise ValueError(f"Unknown page_flag: {source}")
        conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        conn.close()
