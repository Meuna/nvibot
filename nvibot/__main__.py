# coding=utf-8

import sys
import argparse
import logging

from nvibot import nvibot

from . import __title__
from .notifiers import PushoverNotifier, DiscordNotifier
from .nvibot import Nvibot
from .ldlc_driver import LdlcDriver
from .nvidia_api import NvidiaApiScrapper
from . import secrets

logger = logging.getLogger(__title__)


def run_nvibot():
    gpu_choices = NvidiaApiScrapper.sku_name_map.values()
    parser = argparse.ArgumentParser(__title__)
    parser.add_argument("buyer")
    parser.add_argument("buy_priority", nargs="+", choices=gpu_choices)
    parser.add_argument("--buy-limit", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=2)
    parser.add_argument(
        "--notifier", choices=["discord", "pushover"], default="discord"
    )

    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr, format="%(asctime)s - %(levelname)s: %(message)s"
    )
    logger.setLevel(logging.DEBUG)

    secret_manager = secrets.get_manager(args.buyer)
    if args.notifier == "discord":
        notifier = DiscordNotifier(secret_manager)
    else:
        notifier = PushoverNotifier(secret_manager)

    notifier.push(f"{__title__} initializing")

    ldlc_driver = LdlcDriver(notifier, secret_manager, args.timeout)
    nvidia_scrapper = NvidiaApiScrapper(notifier, args.timeout)
    bot = Nvibot(
        ldlc_driver, nvidia_scrapper, notifier, args.buy_priority, args.buy_limit
    )
    try:
        bot.run()
    except Exception as exc:
        notifier.push(f"{__title__} exited with error: {exc}")
        raise


def test_ldlc_driver():

    logging.basicConfig(
        stream=sys.stderr, format="%(asctime)s - %(levelname)s: %(message)s"
    )
    logger.setLevel(logging.DEBUG)

    buyer = sys.argv[1]
    product_url = sys.argv[2]

    secret_manager = secrets.get_manager(buyer)
    notifier = DiscordNotifier(secret_manager)
    with LdlcDriver(notifier, secret_manager) as ldlc:
        ldlc.login()
        ldlc.buy(product_url)


if __name__ == "__main__":
    run_nvibot()
