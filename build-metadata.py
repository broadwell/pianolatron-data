#!/usr/bin/env python3

""" Build per-DRUID metadata .json files for consumption by the Pianolatron app. """

import logging
from pathlib import Path

import requests
from lxml import etree

DRUIDS = [
    "zb497jz4405",
    "yj598pj2879",
    "pz594dj8436",
    "dj406yq6980",
    "rx870zt5437",
    "wt621xq0875",
    "kr397bv2881",
]

PURL_BASE = "https://purl.stanford.edu/"
NS = {"x": "http://www.loc.gov/mods/v3"}

CACHE_MODS = True


def get_value_by_xpath(xml_tree, xpath):
    try:
        return xml_tree.xpath(
            xpath,
            namespaces=NS,
        )[0]
    except:
        return "unknown"


def get_metadata_for_druid(druid):
    logging.info(f"Processing {druid}...")

    metadata = {}

    mods_filepath = Path(f"mods/{druid}.mods")

    if mods_filepath.exists():
        xml_tree = etree.parse(mods_filepath.open())
    else:
        response = requests.get(f"{PURL_BASE}{druid}.mods")
        xml_tree = etree.fromstring(response.content)
        if CACHE_MODS:
            with mods_filepath.open("r") as _fh:
                _fh.write(
                    etree.tostring(xml_tree, encoding="unicode", pretty_print=True)
                )

    metadata.update(
        {
            "title": get_value_by_xpath(xml_tree, "(x:titleInfo/x:title)[1]/text()"),
            "composer": get_value_by_xpath(
                xml_tree,
                "x:name[descendant::x:roleTerm[text()='composer']]/x:namePart[not(@type='date')]/text()",
            ),
            "performer": get_value_by_xpath(
                xml_tree,
                "x:name[descendant::x:roleTerm[text()='instrumentalist']]/x:namePart[not(@type='date')]/text()",
            ),
            "label": get_value_by_xpath(
                xml_tree, "x:identifier[@type='issue number']/text()"
            ),
            "PURL": PURL_BASE + druid,
        }
    )


def main():
    """ Command-line entry-point. """

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    for druid in DRUIDS:
        get_metadata_for_druid(druid)


if __name__ == "__main__":
    main()
