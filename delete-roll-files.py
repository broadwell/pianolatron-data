#!/usr/bin/env python3

""" Delete all parsing files associated with the given DRUID """
""" NOTE that for now this does not delete the downloaded    """
""" MODS and IIIF metadata about the DRUID (these rarely     """
""" change and should be handled manually if so), nor the    """
""" binasc or report files for the DRUID, because these are  """
""" overwritten each time build-metadata.py is run.          """

import sys
from pathlib import Path

druids = [
    # "yt837kd6607"
    # "bj606rp8160",
    # "yx536mq2915",
    # "qz671pq0609",
    # "rj799hj0968",
    # "xx912rs1788",
    # "zf673fy4620",
    # "hk155fw7898",
    # "zw751nw0097",
    # "pr464zk8674",
    # "vs880hb3425",
    # "dw083wh0675",
    # "zf673fy4620",
    # "wn516xn5163",
]

# Providing a single DRUID on the cmd line overrides the list above
if len(sys.argv) > 1:
    druids = [sys.argv[1]]

for druid in druids:
    Path(f"txt/{druid}.txt").unlink(missing_ok=True)
    Path(f"json/{druid}.json").unlink(missing_ok=True)
    Path(f"midi/{druid}.mid").unlink(missing_ok=True)
    Path(f"midi/raw/{druid}_raw.mid").unlink(missing_ok=True)
    Path(f"midi/note/{druid}_note.mid").unlink(missing_ok=True)
    Path(f"midi/exp/{druid}_exp.mid").unlink(missing_ok=True)
