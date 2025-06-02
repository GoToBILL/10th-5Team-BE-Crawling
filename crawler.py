import os
import importlib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


def handler(event=None, context=None):
    site_name = os.environ.get("SITE_NAME")
    print(f"Target site_name: {site_name}")
    if not site_name:
        return {
            "statusCode": 400,
            "message": "SITE_NAME 환경변수가 설정되지 않았습니다."
        }

    try:
        suc_cnt, err_cnt = crawler_target(site_name)
        return {
            "statusCode": 200,
            "suc_cnt": suc_cnt,
            "err_cnt": err_cnt
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "message": f"크롤러 실행 중 오류 발생: {str(e)}"
        }


def crawler_target(site_name):
    # Selenium 실행 옵션 설정 (Lambda 환경용)
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

    # Chrome 드라이버 설정
    service = Service(executable_path="/opt/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 동적 import로 사이트 별 모듈 로드
    try:
        module = importlib.import_module(f"{site_name}.{site_name}_main")
        suc_cnt, err_cnt = module.run(driver)
    except ModuleNotFoundError:
        raise Exception(f"'{site_name}'에 해당하는 모듈을 찾을 수 없습니다.")
    except AttributeError:
        raise Exception(f"'{site_name}' 모듈에 'run(driver)' 함수가 정의되어 있지 않습니다.")
    finally:
        driver.quit()

    return suc_cnt, err_cnt