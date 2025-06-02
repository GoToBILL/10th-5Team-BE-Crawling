from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


def handler(event=None, context=None):
    suc_cnt, err_cnt = crawler_target()
    return {
        "statusCode": 200,
        "suc_cnt": suc_cnt,
        "err_cnt": err_cnt
    }


def crawler_target():
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

    # Lambda 전용 크롬 드라이버 경로 설정
    service = Service(executable_path="/opt/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    suc_cnt = 0
    err_cnt = 0

    # TODO: 여기에 크롤링 로직을 구현하세요.
    
    driver.quit()
    return suc_cnt, err_cnt