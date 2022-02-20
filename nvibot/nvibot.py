# coding=utf-8

import time
import logging
from typing import List

from . import __title__
from .notifiers import Notifier
from .nvidia_api import NvidiaApiScrapper
from .ldlc_driver import LdlcDriver, LdlcError

logger = logging.getLogger(__title__)


class Nvibot:
    def __init__(
        self,
        ldlc_driver: LdlcDriver,
        nvidia_scrapper: NvidiaApiScrapper,
        notifier: Notifier,
        buy_priority: List[str],
        buy_limit: int,
    ):
        self._notifier = notifier
        self._ldlc_driver = ldlc_driver
        self._nvidia_scrapper = nvidia_scrapper

        self._buy_priority = buy_priority.copy()
        self._buy_limit = buy_limit

        self._bought = set()

        self._alive_log_decimation = 10
        self._error_stack_tolerance = 5

    @property
    def done(self) -> bool:
        return len(self._bought) >= self._buy_limit

    def run(self) -> None:
        with self._ldlc_driver:
            self._ldlc_driver.login()
            self._notifier.push("Nvidia scrapping started")
            self.lookup_and_buy()

        self._notifier.push("My job is done !")

    def lookup_and_buy(self) -> None:
        alive_count = 0
        successive_error_count = 0

        while not self.done:
            time.sleep(2)

            if alive_count == 0:
                logger.debug("I'm still alive !")
            alive_count = (alive_count + 1) % self._alive_log_decimation

            # Safe scrap
            try:
                urls_to_try = self._nvidia_scrapper.scrap()
                successive_error_count = 0
            except Exception as exc:
                urls_to_try = {}
                successive_error_count = successive_error_count + 1
                logger.error(f"Scrapping error: {exc}")
                if successive_error_count > self._error_stack_tolerance:
                    self._notifier.humble_push(f"Errors are stacking: {exc}")
                    successive_error_count = 0

            # Try to buy stuff
            for product in self._buy_priority:
                if not self.done and product in urls_to_try:
                    product_url = urls_to_try[product]
                    self._notifier.push(
                        f"Transaction attempt: {product} ({product_url})"
                    )
                    try:
                        self._ldlc_driver.buy(product_url)
                    except LdlcError:
                        pass
                    else:
                        self.consider_bought(product)

    def consider_bought(self, product: str) -> None:
        self._buy_priority.remove(product)
        self._bought.add(product)
        self._notifier.push(f"{product} considered bought !")
