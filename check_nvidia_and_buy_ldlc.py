# coding=utf-8
import os
import sys
import time
import logging
import json

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException

import buy_ldlc
import helpers

logger = logging.getLogger('autobuy')
DEFAULT_NVIDIA_URL = 'https://www.nvidia.com/fr-fr/shop/geforce/gpu/?page=1&limit=100&locale=fr-fr&category=GPU&gpu=RTX%203060,RTX%203060%20Ti,RTX%203070,RTX%203070%20Ti,RTX%203080,RTX%203080%20Ti,RTX%203090&manufacturer=NVIDIA'
NVIDIA_URL = os.environ.get('NVIDIA_URL', DEFAULT_NVIDIA_URL)
DEFAULT_BUY_PRIORITY = ['NVIDIA GEFORCE RTX 3060 Ti', 'NVIDIA GEFORCE RTX 3080', 'NVIDIA GEFORCE RTX 3070 Ti', 'NVIDIA GEFORCE RTX 3070']
BUY_PRIORITY = os.environ.get('BUY_PRIORITY', DEFAULT_BUY_PRIORITY)
BUY_LIMIT = os.environ.get('BUY_LIMIT', 2)

FE_URL_FILE = 'fe_urls.json'
TIMEOUT = os.environ.get('timeout', 5)


class AccessDenied(Exception):
    def __init__(self, page_title):
        self.page_title = page_title


def get_fe_urls(driver, previous_fe_urls):
    driver.get(NVIDIA_URL)
    time.sleep(1)

    if not driver.title or driver.title == 'Access Denied':
        raise AccessDenied(driver.title)

    products = driver.find_elements_by_css_selector('div.product-details-list-tile')
    products.append(driver.find_element_by_css_selector('div.product-container'))
    
    fe_urls = previous_fe_urls.copy()
    should_try = set()
    for product in products:
        product_name = product.find_element_by_css_selector('h2.name').text
        
        # Get product details
        buy_div_elt = product.find_element_by_css_selector('div.buy')
        details_div_elt = buy_div_elt.find_elements_by_tag_name('div')[0]
        details = json.loads(details_div_elt.get_attribute('innerHTML'))[0]
        product_url = details['purchaseLink']
        fe_urls[product_name] = product_url

        # Check if link is green
        try:
            buy_link_elt = product.find_element_by_css_selector('span.buy-link')
        except:
            pass
        else:
            logger.warning(f"{product_name} in stock !")
            helpers.push_msg_no_spam(f"{product_name} in stock !", with_sound=True)
            should_try.add(product_name)

        if previous_fe_urls and previous_fe_urls[product_name] != fe_urls[product_name]:
            logger.warning(f"URL change detected for {product_name} !")
            helpers.push_msg_no_spam(f"URL change detected for {product_name} !", with_sound=True)
            should_try.add(product_name)

    return fe_urls, should_try

def lookup_and_buy(driver, fe_price_init, cc):
    fe_urls = fe_price_init
    should_try = set()
    bought = set()
    quiet_log_count = 0
    successive_error_count = 0
    while len(bought) < BUY_LIMIT:
        time.sleep(2)
        if quiet_log_count == 0:
           logger.debug("Looping on NVIDIA page")
        quiet_log_count = (quiet_log_count + 1) % 10

        try:
            fe_urls, new_tries = get_fe_urls(driver, fe_urls)
        except NoSuchElementException as exc:
            successive_error_count = successive_error_count + 1
            logger.error("Scanning error")
            logger.exception(exc)
            if successive_error_count > 5:
                helpers.push_msg_no_spam(f"Errors stacking !", priority=2, with_sound=True)
                successive_error_count = 0
        else:
            should_try = should_try.union(new_tries)
            should_try = should_try.intersection(BUY_PRIORITY)

        for product_name in BUY_PRIORITY:
            if (len(bought) < BUY_LIMIT) and product_name in (should_try - bought):
                try:
                    buy_ldlc.buy_url(driver, fe_urls[product_name], cc)
                except buy_ldlc.UrlNotReady:
                    pass
                except buy_ldlc.CallFailed:
                    pass
                else:
                    logger.info(f'{product_name} considered bought')
                    bought.add(product_name)

def main():

    logging.basicConfig(stream=sys.stderr, format='%(levelname)s:%(message)s')
    logger.setLevel(logging.DEBUG)
    logger.info(f"Task started")

    ldlc_user, ldlc_password, cc = helpers.get_secrets()

    if os.path.isfile(FE_URL_FILE):
        logger.info(f"Init prices from file")
        with open(FE_URL_FILE) as fh:
            fe_price_init = json.load(fh)
    elif 'FE_PRICE_INIT' in os.environ:
        logger.info(f"Init prices from env")
        fe_price_init = json.loads(os.environ['FE_PRICE_INIT'])
    else:
        fe_price_init = {}

    options = Options()
    options.headless = True

    try_again = True
    while try_again:
        try:
            with webdriver.Firefox(options=options, service_log_path=os.path.devnull) as driver:
                logger.info(f"Web driver started")
                driver.set_page_load_timeout(2*TIMEOUT)
                buy_ldlc.log_in_ldlc(driver, ldlc_user, ldlc_password)
                lookup_and_buy(driver, fe_price_init, cc)
                try_again = False
        except AccessDenied as exc:
            logger.error(f"NVIDIA access denied (with title '{exc.page_title}')")

    logging.info("Task done !")


if __name__ == '__main__':
    main()
