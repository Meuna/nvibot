# coding=utf-8
import os
import sys
import logging
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

import helpers

logger = logging.getLogger('autobuy')

TIMEOUT = os.environ.get('timeout', 5)

CHRONOPOST_ID = 'SelectedDeliveryModeId370008'
CHRONOPOST_EXP_ID = 'SelectedDeliveryModeId370009'


class UrlNotAvailable(Exception):
    pass


class CartAddFailure(Exception):
    pass


class CallFailed(Exception):
    pass


class PayementRefused(Exception):
    pass

# Decorator

def stubborn_call(f):
    def decorated(driver, *args, **kwargs):
        max_attemps = kwargs.pop('max_attemps', 5)
        sleep_for = kwargs.pop('sleep_for', 3)
        nb_attemps = 0
        while nb_attemps < max_attemps:
            nb_attemps = nb_attemps + 1
            try:
                return f(driver, *args, **kwargs)
            except (UrlNotAvailable, CartAddFailure):
                raise
            except Exception as exc:
                if 'maintenance' in driver.title:
                    logger.error(f"Cat page (attempt {nb_attemps})")
                else:
                    logger.error(f"Attempt failed (attempt {nb_attemps}). Page title: {driver.title}")
                    logger.exception(exc)

            time.sleep(sleep_for)

        logger.error(f"Max stubborn_buy attempts reached ({max_attemps})")
        raise CallFailed()

    return decorated


# API

@stubborn_call
def log_in_ldlc(driver, user, password):
    driver.get('https://www.ldlc.com')

    # Accept cookie if needed
    ldlc_cookies = [ck['name'] for ck in driver.get_cookies() if ck['domain'] == '.ldlc.com']
    if 'cookiespreferences' not in ldlc_cookies:
        logger.info(f"Accept cookie")
        cookie_accept_elt = WebDriverWait(driver, TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, 'cookieConsentAcceptButton'))
        )
        cookie_accept_elt.click()

    # Login
    logger.info(f"Loging in")
    account_elt = driver.find_element_by_id('compte')
    account_elt.click()
    stay_connectd_elt = driver.find_element_by_id('LongAuthenticationDuration')
    stay_connectd_elt.click()
    email_elt = driver.find_element_by_id('Email')
    email_elt.send_keys(user)
    ldlc_pw_elt = driver.find_element_by_id('Password')
    ldlc_pw_elt.send_keys(password)

    ldlc_pw_elt.send_keys(Keys.RETURN)

    # Wait until the login worked
    WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'a.logout'))
    )
    logger.info(f"Loging successful")

@stubborn_call
def buy_url(driver, url, cc, product_name='unspecified'):
    # helpers.push_msg_no_spam(f"Buying tentative: {product_name} ({url})")
    ensure_empty_basket(driver)
    get_and_ensure_url(driver, url)
    checkout(driver)
    ensure_home_delivery(driver)
    order(driver, cc)
    wait_3ds(driver)

    # Final small wait
    time.sleep(2)

# Helpers

def ensure_empty_basket(driver):
    driver.get('https://www.ldlc.com')
    basket_elt = driver.find_element_by_id('panier')
    try:
        basket_elt.find_element_by_css_selector('span.nb-pdt')
    except:
        pass
    else:
        logger.info(f"Basket is not empty")
        basket_elt.click()
        trash_icon_elt = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.icon-trash'))
        )
        trash_link_elt = trash_icon_elt.find_element_by_xpath('./..')
        trash_link_elt.click()
        trash_icon_elt = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.icon-trash'))
        )
        confirm_button_elt = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, 'OUI'))
        )
        confirm_button_elt.click()
        logger.info(f"Successfully emptied the basket")

def get_and_ensure_url(driver, url):
    logger.info(f"Get {url}")
    driver.get(url)

    url_ready = False
    try:
        driver.find_element_by_css_selector('div.p410')
    except:
        try:
            driver.find_element_by_css_selector('div.p404')
        except:
            url_ready = True

    if not url_ready:
        logger.error(f"{url} is not ready")
        helpers.push_msg_no_spam(f"{url} is not ready")
        raise UrlNotAvailable()

def checkout(driver):
    logger.info(f"Add product in cart")

    try:
        WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.add-to-cart-oneclic'))
        )
    except:
        we_left_the_page = cart_checkout(driver)
    else:
        we_left_the_page = one_click_checkout(driver)

    # Check if we are still on the page in which case we have most likely been
    # offered an extended waranty: we refuse
    if not we_left_the_page:
        logger.info(f"Still on the page: extended warranty refusal tentative")
        try:
            refuse_elt = WebDriverWait(driver, TIMEOUT).until(
                EC.element_to_be_clickable((By.LINK_TEXT, 'NON MERCI'))
            )
            refuse_elt.click()
            logger.info(f"Refused extended warranty")
        except:
            logger.info(f"Warranty refusal failed")

def one_click_checkout(driver):
    # Get reference of generic modals to react to
    default_modal_elt = driver.find_element_by_id('modal-default')
    generic_modal_elt = driver.find_element_by_id('error-generic-modal')

    buy_elt = driver.find_element_by_css_selector('button.add-to-cart-oneclic')
    buy_elt.click()
    logger.info(f"Instant checkout was available")

    # Check for cart add error. Also capture stale error to check if we left
    # the page or not
    try:
        if generic_modal_elt.is_displayed() or default_modal_elt.is_displayed():
            logger.error(f"Modal error: cart add failed")
            helpers.push_msg_no_spam(f"Modal error: cart add failed")
            raise CartAddFailure()
    except StaleElementReferenceException:
        we_left_the_page = True
    else:
        we_left_the_page = False

    return we_left_the_page

def cart_checkout(driver):
    logger.info(f"Switching to manual cart checkout")
    add_cart_elt = WebDriverWait(driver, TIMEOUT).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.add-to-cart'))
    )
    add_cart_elt.click()

    see_cart_elt = WebDriverWait(driver, TIMEOUT).until(
        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, 'VOIR MON PANIER'))
    )
    see_cart_elt.click()

    order_div_elt = driver.find_element_by_id('order')
    checkout_elt = order_div_elt.find_element_by_css_selector('button.maxi')
    checkout_elt.click()

    # Test if the clicked element is stale, in which case we left the page
    try:
        checkout_elt.is_enabled()
    except StaleElementReferenceException:
        we_left_the_page = True
    else:
        we_left_the_page = False

    return we_left_the_page

def ensure_home_delivery(driver):
    logger.info(f"Ensuring home delivery")

    # First wait for the (hopefully) allways present regular chronopost option
    chronop_radio_elt = wait_staleness(driver, (By.ID, CHRONOPOST_ID))
    if chronop_radio_elt.get_attribute('selected') != 'true':
        logger.info(f'Switching to regular chronopost')
        chronop_div_elt = chronop_radio_elt.find_element_by_xpath('./..')
        chronop_div_elt.click()
        wait_staleness(driver, (By.ID, 'CardNumber'))
    else:
        logger.info(f"Chronopost already selected")

def try_express_delivery(driver):
    logger.info(f"Try express delivery")

    # First wait for the (hopefully) allways present regular chronopost option
    chronop_radio_elt = wait_staleness(driver, (By.ID, CHRONOPOST_ID))

    try:
        # Then tries to activate the express option
        chronop_radio_exp_elt = driver.find_element_by_id(CHRONOPOST_EXP_ID)
        if chronop_radio_exp_elt.get_attribute('selected') != 'true':
            logger.info(f"Switching to chronopost express")
            chronop_div_elt = chronop_radio_exp_elt.find_element_by_xpath('./..')
            chronop_div_elt.click()
            wait_staleness(driver, (By.ID, 'CardNumber'))
        else:
            logger.info(f"Chronopost express already selected")
    except:
        logger.info(f"Chronopost express unavailable")
        if chronop_radio_elt.get_attribute('selected') != 'true':
            logger.info(f'Switching to regular chronopost')
            chronop_div_elt = chronop_radio_elt.find_element_by_xpath('./..')
            chronop_div_elt.click()
            wait_staleness(driver, (By.ID, 'CardNumber'))
        else:
            logger.info(f"Chronopost already selected")

def order(driver, cc):
    logger.info(f'Placing order')

    # Processing credit card informations
    logger.info(f"Filling payement informations")
    card_nb_elt = driver.find_element_by_id('CardNumber')
    card_nb_elt.send_keys(cc['number'])
    exp_date_elt = driver.find_element_by_id('ExpirationDate')
    exp_date_elt.send_keys(cc['exp_date'])
    owner_elt = driver.find_element_by_id('OwnerName')
    owner_elt.send_keys(cc['owner'])
    cpt_elt = driver.find_element_by_id('Cryptogram')
    cpt_elt.send_keys(cc['cpt'])

    logger.info(f"Submiting payement")
    payment_div_elt = driver.find_element_by_id('payment-form')
    pay_elt = payment_div_elt.find_element_by_css_selector('button.maxi')
    pay_elt.click()

    try:
        error_elt = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span.field-validation-error'))
        )
    except:
        logger.error(f"Payement accepted")
    else:
        logger.error(f"Payement error: {error_elt.text}")
        helpers.push_msg(f"Payement error: {error_elt.text}")
        raise PayementRefused()

def wait_3ds(driver):
    logger.warning(f"Waiting for 3DS approval")
    helpers.push_msg(f"Waiting for 3DS approval")
    time.sleep(2)
    while 'ldlc.com' not in urlparse(driver.current_url).netloc:
        time.sleep(1)

    helpers.push_msg(f"Back to LDLC in page '{driver.title}'")
    logger.info(f"Back to LDLC in page '{driver.title}'")

def wait_staleness(driver, locator):
    logger.info(f"Waiting for DOM stabilization on {locator}")

    # Here we wait for some strange DOM movements to happen
    elt = WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located(locator)
    )
    try:
        WebDriverWait(driver, 2).until(
            EC.staleness_of(elt)
        )
    except:
        logger.debug(f"DOM stabilization not needed")
    elt = WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located(locator)
    )
    return elt


def main():

    logging.basicConfig(stream=sys.stderr, format='%(levelname)s:%(message)s')
    logger.setLevel(logging.DEBUG)
    logger.info(f"Task started")

    product_url = sys.argv[1]

    ldlc_user, ldlc_password, cc = helpers.get_secrets()

    options = Options()
    options.headless = True

    with webdriver.Firefox(options=options, service_log_path=os.path.devnull) as driver:
        driver.set_page_load_timeout(2*TIMEOUT)

        log_in_ldlc(driver, ldlc_user, ldlc_password)
        buy_url(driver, product_url, cc)

    logger.info("Task done !")


if __name__ == '__main__':
    main()
