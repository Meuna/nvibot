# coding=utf-8

import os
import time
import logging
import json
from typing import Tuple, Dict

import requests

from . import __title__
from .notifiers import Notifier

logger = logging.getLogger(__title__)

if os.name == "nt":
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0"
    )
else:
    USER_AGENT = (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0"
    )


class NvidiaApiError(Exception):
    pass


# https://api.store.nvidia.com/partner/v1/feinventory?skus=FR~NVGFT070~NVGFT080~NVGFT090~NVLKR30S~NSHRMT01~NVGFT060T~187&locale=FR


class NvidiaApiScrapper:
    """Scrap the Nvidia API to retrieve the URL of available Nvidia GPUs.

    :param notifier: used to push notifications
    :param timeout:
    """

    api_url = "https://api.store.nvidia.com/partner/v1/feinventory"
    api_params = {
        "skus": "FR~NVGFT070~NVGFT080~NVGFT090~NVLKR30S~NSHRMT01~NVGFT060T~187",
        "locale": "FR",
    }
    api_headers = {
        "user-agent": USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "accept-language": "fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3",
        "accept-encoding": "gzip, deflate, br",
        "cache-control": "max-age=0",
        "host": "api.store.nvidia.com",
        "origin": "https://shop.nvidia.com",
        "referer": (
            "https://shop.nvidia.com/fr-fr/geforce/store/gpu/?page=1&limit=100&locale=fr-fr&category=GPU&"
            "gpu=RTX%203060%20Ti,RTX%203070,RTX%203070%20Ti,RTX%203080,RTX%203080%20Ti,RTX%203090&manufacturer=NVIDIA"
        ),
    }
    sku_name_map = {
        "NVGFT060T_FR": "3060Ti",
        "NVGFT070_FR": "3070",
        "NVGFT070T_FR": "3070Ti",
        "NVGFT080_FR": "3080",
        "NVGFT080T_FR": "3080Ti",
        "NVGFT090_FR": "3090",
    }

    def __init__(self, notifier: Notifier, timeout: int):
        self._notifier = notifier
        self._current_fe_urls = {}
        self._timeout = timeout

    def scrap(self) -> Dict[str, str]:
        """Return a dictionary of the available GPUs. Key are GPU name and
        values are store URL.
        """

        timestamp = round(time.time())
        params = self.api_params.copy()
        params["timestamp"] = str(timestamp)
        headers = self.api_headers.copy()
        headers["referer"] = headers["referer"] + f"&timestamp={timestamp}"
        reply = requests.get(
            self.api_url,
            params=params,
            headers=headers,
            timeout=self._timeout,
        )

        if reply.status_code != 200:
            logger.error(f"HTTP {reply.status_code} - {reply.text}")
            raise NvidiaApiError(f"HTTP {reply.status_code} - {reply.text}")

        raw_data = reply.json()
        return self.extract_available_gpu(raw_data)

    def extract_available_gpu(self, raw_data: dict) -> Dict[str, str]:
        try:
            products = raw_data["listMap"]
        except:
            logger.error("NVIDIA API scrapping error: " + json.dumps(raw_data))
            raise NvidiaApiError("raw data scrapping failed")

        urls_to_try = {}

        try:
            for product in products:
                fe_sku = product["fe_sku"]
                if fe_sku in self.sku_name_map:
                    gpu = self.sku_name_map[fe_sku]
                    product_url, should_try = self.check_product(product, gpu)
                    if should_try:
                        urls_to_try[gpu] = product_url

        except:
            logger.error("NVIDIA API scrapping error: " + json.dumps(products))
            raise NvidiaApiError("products scrapping failed")

        return urls_to_try

    def check_product(self, product: dict, gpu: str) -> Tuple[str, bool]:
        should_try = False
        availability = product["is_active"]
        product_url = product["product_url"]

        # Check if we observed an URL change
        previous_url = self._current_fe_urls.get(gpu, product_url)
        if product_url != previous_url:
            self._notifier.push_once(f"New URL for {gpu}: {product_url}")
            should_try = True

        # Check if the is_active field is true
        if availability.lower() == "true":
            self._notifier.push_once(f"{gpu} in stock at {product_url} !")
            should_try = True

        self._current_fe_urls[gpu] = product_url

        return product_url, should_try
