# coding=utf-8

import os
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

from . import __title__
from .notifiers import Notifier
from .secrets import SecretManager

logger = logging.getLogger(__title__)


CHRONOPOST_ID = "SelectedDeliveryModeId370008"
CHRONOPOST_EXP_ID = "SelectedDeliveryModeId370009"


class LdlcError(Exception):
    pass


class UrlNotAvailable(LdlcError):
    pass


class CartAddFailure(LdlcError):
    pass


class CallFailed(LdlcError):
    pass


class PayementRefused(LdlcError):
    pass


def stubborn_call(method):
    """Decorates a method to make it retry until it fails enough attempt. It
    extracts the folowing keyword arguments.

    :param max_attemps: number of attempts before giving up
    :param sleep_for: how much time slept between attempts
    """

    def decorated(self, *args, **kwargs):
        max_attemps = kwargs.pop("max_attemps", 5)
        sleep_for = kwargs.pop("sleep_for", 2)
        nb_attemps = 0
        while nb_attemps < max_attemps:
            nb_attemps = nb_attemps + 1
            try:
                return method(self, *args, **kwargs)
            except (UrlNotAvailable, CartAddFailure):
                raise
            except Exception as exc:
                if "maintenance" in self._driver.title:
                    logger.error(f"Cat page (attempt {nb_attemps})")
                else:
                    logger.error(
                        f"Attempt failed (attempt {nb_attemps}). Page title: {self._driver.title}"
                    )
                    logger.exception(exc)

            time.sleep(sleep_for)

        logger.error(f"Max stubborn_buy attempts reached ({max_attemps})")
        raise CallFailed()

    return decorated


class LdlcDriver:
    """An LDLC buying driver, over a Selenium Firefox driver. It should be used
    inside as a contect manager.

    :param notifier: used to push the driver notifications
    :param secret_manager: used to retrieve credentials and credit cards
        informations
    :param timeout: used to wait various event by the driver

    Example:

        >>> with LdlcDriver(notifier, secret_manager) as ldlc:
                ldlc.login()
                ldlc.buy(url)
    """

    url = "https://www.ldlc.com"

    def __init__(
        self, notifier: Notifier, secret_manager: SecretManager, timeout: int = 2
    ):
        credentials = secret_manager.get("ldlc", json=True)
        self._ldlc_user = credentials["user"]
        self._ldlc_password = credentials["password"]
        self._cc = secret_manager.get("cc", json=True)

        self._driver = None
        self._notifier = notifier
        self._timeout = timeout
        self._extended_timeout = timeout * 3

    def __enter__(self):
        options = Options()
        options.headless = True
        self._driver = webdriver.Firefox(
            options=options, service_log_path=os.path.devnull
        )
        self._driver.set_page_load_timeout(self._timeout)

        self.accept_cookies()

        return self

    def __exit__(self, *args, **kwargs):
        return self._driver.__exit__(*args, **kwargs)

    def accept_cookies(self) -> None:
        self._driver.get("https://www.ldlc.com")

        # Accept cookie if needed
        ldlc_cookies = [
            ck["name"]
            for ck in self._driver.get_cookies()
            if ck["domain"] == ".ldlc.com"
        ]
        if "cookiespreferences" not in ldlc_cookies:
            logger.info(f"Accept cookie")
            cookie_accept_elt = WebDriverWait(
                self._driver, self._extended_timeout
            ).until(EC.element_to_be_clickable((By.ID, "cookieConsentAcceptButton")))
            cookie_accept_elt.click()

    @stubborn_call
    def login(self) -> None:
        self._driver.get("https://www.ldlc.com")

        # Small wait 'cause we often yield a cat page on login
        time.sleep(1)

        # Login
        logger.info(f"Loging in")
        account_elt = self._driver.find_element(By.ID, "compte")
        account_elt.click()
        stay_connectd_elt = self._driver.find_element(
            By.ID, "LongAuthenticationDuration"
        )
        stay_connectd_elt.click()
        email_elt = self._driver.find_element(By.ID, "Email")
        email_elt.send_keys(self._ldlc_user)
        ldlc_pw_elt = self._driver.find_element(By.ID, "Password")
        ldlc_pw_elt.send_keys(self._ldlc_password)

        ldlc_pw_elt.send_keys(Keys.RETURN)

        # Wait until the login worked
        WebDriverWait(self._driver, self._timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.logout"))
        )
        self._notifier.push(f"Loging successful")

    @stubborn_call
    def buy(self, url: str) -> None:
        self.ensure_empty_basket()
        self.get_and_ensure_url(url)
        self.checkout()
        self.ensure_home_delivery()
        self.order()
        self.wait_3ds()

        # Final small wait
        time.sleep(2)

    def ensure_empty_basket(self) -> None:
        self._driver.get("https://www.ldlc.com")
        basket_elt = self._driver.find_element(By.ID, "panier")
        try:
            basket_elt.find_element(By.CSS_SELECTOR, "span.nb-pdt")
        except:
            pass
        else:
            logger.info(f"Basket is not empty")
            basket_elt.click()
            trash_icon_elt = WebDriverWait(self._driver, self._timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span.icon-trash"))
            )
            trash_link_elt = trash_icon_elt.find_element(By.XPATH, "./..")
            trash_link_elt.click()
            trash_icon_elt = WebDriverWait(self._driver, self._timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span.icon-trash"))
            )
            confirm_button_elt = WebDriverWait(self._driver, self._timeout).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "OUI"))
            )
            confirm_button_elt.click()
            logger.info(f"Successfully emptied the basket")

    def get_and_ensure_url(self, url: str) -> None:
        logger.info(f"Get {url}")
        self._driver.get(url)

        url_ready = False
        try:
            self._driver.find_element(By.CSS_SELECTOR, "div.p410")
        except:
            try:
                self._driver.find_element(By.CSS_SELECTOR, "div.p404")
            except:
                url_ready = True

        if not url_ready:
            self._notifier.humble_push(f"{url} is not ready")
            raise UrlNotAvailable()

    def checkout(self) -> None:
        logger.info(f"Add product in cart")

        try:
            WebDriverWait(self._driver, self._timeout).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button.add-to-cart-oneclic")
                )
            )
        except:
            we_left_the_page = self.cart_checkout()
        else:
            we_left_the_page = self.one_click_checkout()

        # Check if we are still on the page in which case we have most likely been
        # offered an extended waranty: we refuse
        if not we_left_the_page:
            logger.info(f"Still on the page: extended warranty refusal tentative")
            try:
                refuse_elt = WebDriverWait(self._driver, self._extended_timeout).until(
                    EC.element_to_be_clickable((By.LINK_TEXT, "NON MERCI"))
                )
                refuse_elt.click()
                logger.info(f"Refused extended warranty")
            except:
                logger.info(f"Warranty refusal failed")

    def one_click_checkout(self) -> None:
        # Get reference of generic modals to react to
        default_modal_elt = self._driver.find_element(By.ID, "modal-default")
        generic_modal_elt = self._driver.find_element(By.ID, "error-generic-modal")

        buy_elt = self._driver.find_element(
            By.CSS_SELECTOR, "button.add-to-cart-oneclic"
        )
        buy_elt.click()
        logger.info(f"Instant checkout was available")

        # Check for cart add error. Also capture stale error to check if we left
        # the page or not
        try:
            if generic_modal_elt.is_displayed() or default_modal_elt.is_displayed():
                self._notifier.humble_push(f"Modal error: cart add failed")
                raise CartAddFailure()
        except StaleElementReferenceException:
            we_left_the_page = True
        else:
            we_left_the_page = False

        return we_left_the_page

    def cart_checkout(self) -> None:
        logger.info(f"Switching to manual cart checkout")
        add_cart_elt = WebDriverWait(self._driver, self._extended_timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.add-to-cart"))
        )
        add_cart_elt.click()

        see_cart_elt = WebDriverWait(self._driver, self._extended_timeout).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "VOIR MON PANIER"))
        )
        see_cart_elt.click()

        order_div_elt = self._driver.find_element(By.ID, "order")
        checkout_elt = order_div_elt.find_element(By.CSS_SELECTOR, "button.maxi")
        checkout_elt.click()

        # Test if the clicked element is stale, in which case we left the page
        try:
            checkout_elt.is_enabled()
        except StaleElementReferenceException:
            we_left_the_page = True
        else:
            we_left_the_page = False

        return we_left_the_page

    def ensure_home_delivery(self) -> None:
        logger.info(f"Ensuring home delivery")

        # First wait for the (hopefully) allways present regular chronopost option
        chronop_radio_elt = self.wait_staleness((By.ID, CHRONOPOST_ID))
        if chronop_radio_elt.get_attribute("selected") != "true":
            logger.info(f"Switching to regular chronopost")
            chronop_div_elt = chronop_radio_elt.find_element(By.XPATH, "./..")
            chronop_div_elt.click()
            self.wait_staleness((By.ID, "CardNumber"))
        else:
            logger.info(f"Chronopost already selected")

    def try_express_delivery(self) -> None:
        logger.info(f"Try express delivery")

        # First wait for the (hopefully) allways present regular chronopost option
        chronop_radio_elt = self.wait_staleness((By.ID, CHRONOPOST_ID))

        try:
            # Then tries to activate the express option
            chronop_radio_exp_elt = self._driver.find_element(By.ID, CHRONOPOST_EXP_ID)
            if chronop_radio_exp_elt.get_attribute("selected") != "true":
                logger.info(f"Switching to chronopost express")
                chronop_div_elt = chronop_radio_exp_elt.find_element(By.XPATH, "./..")
                chronop_div_elt.click()
                self.wait_staleness((By.ID, "CardNumber"))
            else:
                logger.info(f"Chronopost express already selected")
        except:
            logger.info(f"Chronopost express unavailable")
            if chronop_radio_elt.get_attribute("selected") != "true":
                logger.info(f"Switching to regular chronopost")
                chronop_div_elt = chronop_radio_elt.find_element(By.XPATH, "./..")
                chronop_div_elt.click()
                self.wait_staleness((By.ID, "CardNumber"))
            else:
                logger.info(f"Chronopost already selected")

    def order(self) -> None:
        logger.info(f"Placing order")

        # Processing credit card informations
        logger.info(f"Filling payement informations")
        card_nb_elt = self._driver.find_element(By.ID, "CardNumber")
        card_nb_elt.send_keys(self._cc["number"])
        exp_date_elt = self._driver.find_element(By.ID, "ExpirationDate")
        exp_date_elt.send_keys(self._cc["exp_date"])
        owner_elt = self._driver.find_element(By.ID, "OwnerName")
        owner_elt.send_keys(self._cc["owner"])
        cpt_elt = self._driver.find_element(By.ID, "Cryptogram")
        cpt_elt.send_keys(self._cc["cpt"])

        logger.info(f"Submiting payement")
        payment_div_elt = self._driver.find_element(By.ID, "payment-form")
        pay_elt = payment_div_elt.find_element(By.CSS_SELECTOR, "button.maxi")
        pay_elt.click()

        try:
            error_elt = WebDriverWait(self._driver, self._extended_timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.field-validation-error")
                )
            )
        except:
            logger.info(f"Payement accepted")
        else:
            self._notifier.push(f"Payement error: {error_elt.text}")
            raise PayementRefused()

    def wait_3ds(self) -> None:
        self._notifier.push(f"Waiting for 3DS approval")
        time.sleep(2)
        while "ldlc.com" not in urlparse(self._driver.current_url).netloc:
            time.sleep(1)

        self._notifier.push(f"Back to LDLC in page '{self._driver.title}'")
        logger.info(f"Back to LDLC in page '{self._driver.title}'")

    def wait_staleness(self, locator):
        logger.info(f"Waiting for DOM stabilization on {locator}")

        # Here we wait for some strange DOM movements to happen
        elt = WebDriverWait(self._driver, self._timeout).until(
            EC.presence_of_element_located(locator)
        )
        try:
            WebDriverWait(self._driver, self._timeout).until(EC.staleness_of(elt))
        except:
            logger.debug(f"DOM stabilization not needed")
        elt = WebDriverWait(self._driver, self._timeout).until(
            EC.presence_of_element_located(locator)
        )
        return elt
