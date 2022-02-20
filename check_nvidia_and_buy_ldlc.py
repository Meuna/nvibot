# coding=utf-8
import os
import sys
import time
import logging
import json

import requests
from requests.exceptions import ReadTimeout
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException
import buy_ldlc
import helpers

logger = logging.getLogger('autobuy')

if os.name == 'nt':
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
else:
    user_agent = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0'

# RAW API1 URL: https://api.nvidia.partners/edge/product/search?page=1&limit=100&locale=fr-fr&category=GPU&gpu=RTX%203060,RTX%203060%20Ti,RTX%203070,RTX%203070%20Ti,RTX%203080,RTX%203080%20Ti,RTX%203090&manufacturer=NVIDIA
NVIDIA_WEB_API1_URL = 'https://api.nvidia.partners/edge/product/search'
NVIDIA_WEB_API1_PARAMS = {
    'page': '1',
    'limit': '100',
    'locale': 'fr-fr',
    'category': 'GPU',
    'gpu': 'RTX 3060,RTX 3060 Ti,RTX 3070,RTX 3070 Ti,RTX 3080,RTX 3080 Ti,RTX 3090',
    'manufacturer': 'NVIDIA'
}
NVIDIA_WEB_API1_HEADERS = {
    'user-agent': user_agent,
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.5',
    'accept-encoding': 'gzip, deflate, br',
    'origin': 'https://shop.nvidia.com',
    'referer': 'https://shop.nvidia.com/',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'te': 'trailers'
}

# RAW API2 URL: https://api.store.nvidia.com/partner/v1/feinventory?skus=FR~NVGFT070~NVGFT080~NVGFT090~NVLKR30S~NSHRMT01~NVGFT060T~187&locale=FR
NVIDIA_WEB_API2_URL = 'https://api.store.nvidia.com/partner/v1/feinventory'
NVIDIA_WEB_API2_PARAMS = {
    'skus': 'FR~NVGFT070~NVGFT080~NVGFT090~NVLKR30S~NSHRMT01~NVGFT060T~187',
    'locale': 'FR',
}
NVIDIA_WEB_API2_HEADERS = {
    'user-agent': user_agent,
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3',
    'accept-encoding': 'gzip, deflate, br',
    'host': 'api.store.nvidia.com',
    'origin': 'https://shop.nvidia.com',
    'referer': 'https://shop.nvidia.com/',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'te': 'trailers'
}

NVIDIA_WEBAPP_URL = 'https://www.nvidia.com/fr-fr/shop/geforce/gpu/?page=1&limit=100&locale=fr-fr&category=GPU&gpu=RTX%203060,RTX%203060%20Ti,RTX%203070,RTX%203070%20Ti,RTX%203080,RTX%203080%20Ti,RTX%203090&manufacturer=NVIDIA'
DEFAULT_BUY_PRIORITY = ['NVIDIA GEFORCE RTX 3060 Ti', 'NVIDIA GEFORCE RTX 3070', 'NVIDIA GEFORCE RTX 3080', 'NVIDIA GEFORCE RTX 3070 Ti']
BUY_PRIORITY = os.environ.get('BUY_PRIORITY', DEFAULT_BUY_PRIORITY)
BUY_LIMIT = os.environ.get('BUY_LIMIT', 2)

TIMEOUT = os.environ.get('timeout', 5)
NVIDA_INTERFACE = 'API1'

class AccessDenied(Exception):
    def __init__(self, page_title):
        self.page_title = page_title


class BadStatus(Exception):
    def __init__(self, code, text):
        self.code = code
        self.text = text


def  get_webapi1_fe_urls(session, previous_fe_urls):
    reply = session.get(NVIDIA_WEB_API1_URL,
                        params=NVIDIA_WEB_API1_PARAMS,
                        headers=NVIDIA_WEB_API1_HEADERS,
                        timeout=TIMEOUT)

    if reply.status_code != 200:
        raise BadStatus(reply.status_code, reply.text)

    raw_data = reply.json()

    try:
        products = raw_data['searchedProducts']['productDetails']
        products.append(raw_data['searchedProducts']['featuredProduct'])
    except:
        with open('api_error_raw.dump', 'at') as fh:
            json.dump(raw_data, fh)
            fh.write('\n')
        raise

    try:
        fe_urls = previous_fe_urls.copy()
        should_try = set()
        for product in products:    
            if product_name in BUY_PRIORITY:
                push_alert = helpers.push_msg_no_spam
            else:
                push_alert = helpers.push_msg_once

            product_name = product['productTitle']
            availability = product['prdStatus']
            fe_urls[product_name] = product['retailers'][0]['purchaseLink']

            if availability == 'buy_now':
                logger.warning(f"{product_name} in stock !")
                push_alert(f"{product_name} in stock !", with_sound=True)
                should_try.add(product_name)

            if previous_fe_urls and previous_fe_urls[product_name] != fe_urls[product_name]:
                logger.warning(f"URL change detected for {product_name} !")
                push_alert(f"URL change detected for {product_name} !", with_sound=True)
                should_try.add(product_name)
    except:
        with open('api_erro_products.dump', 'at') as fh:
            json.dump(products, fh)
            fh.write('\n')
        raise

    if should_try:
        with open('api_available_products.dump', 'at') as fh:
            json.dump(products, fh)
            fh.write('\n')

    return fe_urls, should_try

def  get_webapi1_fe_urls(session, previous_fe_urls):
    reply = session.get(NVIDIA_WEB_API_URL,
                        params=NVIDIA_WEB_API_PARAMS,
                        headers=NVIDIA_WEB_API_HEADERS,
                        timeout=TIMEOUT)

    if reply.status_code != 200:
        raise BadStatus(reply.status_code, reply.text)

    raw_data = reply.json()

    try:
        products = raw_data['searchedProducts']['productDetails']
        products.append(raw_data['searchedProducts']['featuredProduct'])
    except:
        with open('api_error_raw.dump', 'at') as fh:
            json.dump(raw_data, fh)
            fh.write('\n')
        raise

    try:
        fe_urls = previous_fe_urls.copy()
        should_try = set()
        for product in products:    
            if product_name in BUY_PRIORITY:
                push_alert = helpers.push_msg_no_spam
            else:
                push_alert = helpers.push_msg_once

            product_name = product['productTitle']
            availability = product['prdStatus']
            fe_urls[product_name] = product['retailers'][0]['purchaseLink']

            if availability == 'buy_now':
                logger.warning(f"{product_name} in stock !")
                push_alert(f"{product_name} in stock !", with_sound=True)
                should_try.add(product_name)

            if previous_fe_urls and previous_fe_urls[product_name] != fe_urls[product_name]:
                logger.warning(f"URL change detected for {product_name} !")
                push_alert(f"URL change detected for {product_name} !", with_sound=True)
                should_try.add(product_name)
    except:
        with open('api_erro_products.dump', 'at') as fh:
            json.dump(products, fh)
            fh.write('\n')
        raise

    if should_try:
        with open('api_available_products.dump', 'at') as fh:
            json.dump(products, fh)
            fh.write('\n')

    return fe_urls, should_try

def get_webapp_fe_urls(driver, previous_fe_urls):
    driver.get(NVIDIA_WEBAPP_URL)
    time.sleep(1)

    if not driver.title or driver.title == 'Access Denied':
        raise AccessDenied(driver.title)

    products = driver.find_elements_by_css_selector('div.product-details-list-tile')
    products.append(driver.find_element_by_css_selector('div.product-container'))
    
    fe_urls = previous_fe_urls.copy()
    should_try = set()
    for product in products:
        product_name = product.find_element_by_css_selector('h2.name').text
        
        if product_name in BUY_PRIORITY:
            push_alert = helpers.push_msg_no_spam
        else:
            push_alert = helpers.push_msg_once

        # Get product details
        buy_div_elt = product.find_element_by_css_selector('div.buy')
        details_div_elt = buy_div_elt.find_elements_by_tag_name('div')[0]
        details = json.loads(details_div_elt.get_attribute('innerHTML'))[0]
        product_url = details['purchaseLink']
        fe_urls[product_name] = product_url

        # Check if link is green
        try:
            buy_div_elt.find_element_by_css_selector('span.buy-link')
        except:
            pass
        else:
            logger.warning(f"{product_name} in stock !")
            push_alert(f"{product_name} in stock !", with_sound=True)
            should_try.add(product_name)

        if previous_fe_urls and previous_fe_urls[product_name] != fe_urls[product_name]:
            logger.warning(f"URL change detected for {product_name} !")
            push_alert(f"URL change detected for {product_name} !", with_sound=True)
            should_try.add(product_name)

    return fe_urls, should_try

def lookup_and_buy(driver, session, cc):
    should_try = set()
    bought = set()
    quiet_log_count = 0
    successive_error_count = 0
    fe_urls = {}
    while len(bought) < BUY_LIMIT:
        time.sleep(2)
        if quiet_log_count == 0:
           logger.debug("Still looping on NVIDIA page")
        quiet_log_count = (quiet_log_count + 1) % 10

        try:
            if NVIDA_INTERFACE == 'API1':
                fe_urls, new_tries =  get_webapi1_fe_urls(session, fe_urls)
            elif NVIDA_INTERFACE == 'API2':
                fe_urls, new_tries =  get_webapi2_fe_urls(session, fe_urls)
            else:
                fe_urls, new_tries = get_webapp_fe_urls(driver, fe_urls)
        except (BadStatus, KeyError, IndexError, NoSuchElementException) as exc:
            successive_error_count = successive_error_count + 1
            logger.error(f"Scanning error: {exc}")
            if successive_error_count > 5:
                helpers.push_msg_no_spam(f"Errors stacking: {exc}", with_sound=True)
                successive_error_count = 0
        else:
            should_try = should_try.union(new_tries)
            should_try = should_try.intersection(BUY_PRIORITY)

        for product_name in BUY_PRIORITY:
            if (len(bought) < BUY_LIMIT) and product_name in (should_try - bought):
                try:
                    buy_ldlc.buy_url(driver, fe_urls[product_name], cc, product_name=product_name)
                except buy_ldlc.UrlNotAvailable:
                    pass
                except buy_ldlc.CartAddFailure:
                    pass
                except buy_ldlc.CallFailed:
                    pass
                else:
                    logger.info(f'{product_name} considered bought !')
                    helpers.push_msg_no_spam(f'{product_name} considered bought !')
                    bought.add(product_name)

def main():

    logging.basicConfig(stream=sys.stderr, format='%(levelname)s:%(message)s')
    logger.setLevel(logging.DEBUG)
    logger.info(f"Task started")

    ldlc_user, ldlc_password, cc = helpers.get_secrets()

    options = Options()
    options.headless = True

    try_again = True
    while try_again:
        try:
            with webdriver.Firefox(options=options, service_log_path=os.path.devnull) as driver:
                logger.info(f"Web driver started")
                driver.set_page_load_timeout(2*TIMEOUT)
                buy_ldlc.log_in_ldlc(driver, ldlc_user, ldlc_password)
                while try_again:
                    try:
                        with requests.Session() as session:
                            lookup_and_buy(driver, session, cc)
                            try_again = False
                    except ReadTimeout:
                        logger.error(f"NVIDIA API timed out")
        except AccessDenied as exc:
            logger.error(f"NVIDIA access denied (with title '{exc.page_title}')")
        except exc:
            helpers.push_msg_no_spam("Something went wrong")
            helpers.push_msg_no_spam("{exc}")
            logger.exception(exc)

    logging.info("Task done !")


if __name__ == '__main__':
    main()
